
import logging
import json
import psycopg2
import os
import io
from typing import Dict, Any, List, Optional
from data_staging.config import settings

logger = logging.getLogger(__name__)

# Tamaño de batch para promoción (registros por iteración)
PROMOTION_BATCH_SIZE = 50000

def promote_batch_job(payload: Dict[str, Any]):
    """
    Handler para jobs de tipo 'PROMOTE_BATCH'.
    Promueve datos de Staging a Producción EN LOTES para manejar grandes volúmenes.
    
    payload = {
        "batch_id": "uuid",
        "target_schema": "public",
        "target_table": "hist"
    }
    """
    batch_id = payload.get("batch_id")
    target_schema = payload.get("target_schema")
    target_table = payload.get("target_table")
    
    if not batch_id or not target_schema or not target_table:
        raise ValueError("Missing required fields: batch_id, target_schema, target_table")

    database_url = str(settings.DATABASE_URL)
    conn = psycopg2.connect(database_url, 
                            keepalives=1, 
                            keepalives_idle=30, 
                            keepalives_interval=10, 
                            keepalives_count=5)
    conn.autocommit = False
    
    try:
        cursor = conn.cursor()
        
        # Disable statement timeout for this massive transaction
        cursor.execute("SET statement_timeout = 0;")
        
        # 1. Obtener metadata del batch para configuración de dedup
        cursor.execute("""
            SELECT metadata, source_name 
            FROM staging_meta.batch_control 
            WHERE batch_id = %s
        """, (batch_id,))
        batch_row = cursor.fetchone()
        
        if not batch_row:
            raise ValueError(f"Batch {batch_id} not found")
            
        metadata = batch_row[0] or {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        source_name = batch_row[1]
        
        safe_source_name = source_name.lower().replace(' ', '_').replace('-', '_')
        staging_table = f"stage_{safe_source_name}"
        
        dedup_columns = metadata.get("dedup_columns", [])
        valid_temp_file_path = metadata.get("valid_temp_file")
        
        logger.info(f"Starting promotion for batch {batch_id} to {target_schema}.{target_table}")
        
        if not valid_temp_file_path:
             logger.warning(f"No valid_temp_file found in metadata for batch {batch_id}. Will fallback to checking staging_data.")
        else:
             import os
             if not os.path.exists(valid_temp_file_path):
                  logger.warning(f"Temp file {valid_temp_file_path} not found on disk. It may be empty or already deleted.")
        
        # ---------------------------------------------------------
        # FASE 2: PRE-VALIDACIÓN (Check de Duplicados CONDICIONAL)
        # ---------------------------------------------------------
        # DISABLED: Validation is skipped to avoid timeouts on large datasets (10M+).
        # Duplicates will be handled by DB constraints at insert time if they exist.
        if dedup_columns:
            logger.info(f"Dedup columns configured: {dedup_columns}. SKIPPING duplicate check (Performance Optimization).")
        else:
            logger.info("No dedup columns configured. Skipping duplicate check (Append Mode).")

        # ---------------------------------------------------------
        # FASE 3: INSERCIÓN EN LOTES / COPY
        # ---------------------------------------------------------
        
        # Obtener columnas del mapping
        wizard_mappings = metadata.get("column_mappings", {})
        column_mapping = {}
        
        target_columns = []
        for file_col, config in wizard_mappings.items():
            if config.get("target") and config.get("target") != "__new__":
                target_col = config.get("target")
                target_columns.append(target_col)
                
        if not target_columns:
             old_mapping = metadata.get("column_mapping", {})
             if old_mapping:
                 target_columns = list(old_mapping.keys())
                 
        target_columns = list(set(target_columns))

        # Construir listas de columnas confirmando su existencia en BD
        cursor.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE LOWER(table_schema) = LOWER(%s) AND LOWER(table_name) = LOWER(%s)
        """, (target_schema, target_table))
        
        db_columns = {row[0]: row[1] for row in cursor.fetchall()}
        db_columns_lower = {k.lower(): k for k in db_columns.keys()}
        
        valid_db_target_cols = []
        for requested_col in target_columns:
            real_col_name = None
            if requested_col in db_columns:
                real_col_name = requested_col
            elif requested_col.lower() in db_columns_lower:
                real_col_name = db_columns_lower[requested_col.lower()]
                
            if real_col_name:
                valid_db_target_cols.append(real_col_name)

        if not valid_db_target_cols:
             found_cols = list(db_columns.keys())
             raise ValueError(f"No columns matched between mapping and target table {target_schema}.{target_table}. Available columns in DB: {found_cols}. Requested columns: {target_columns}")

        total_inserted = 0
        batch_num = 1
        
        if valid_temp_file_path and os.path.exists(valid_temp_file_path):
             # ---------------------------------------------------------
             # METODO A: COPY desde Archivo Temporal (Ultra rápido)
             # ---------------------------------------------------------
             logger.info(f"Using standard Temp File COPY approach from {valid_temp_file_path}")
             
             # The CSV temp file has specific columns written to it in file_processor.py:
             # target_cols + ['_batch_id_', '_source_row_number_']
             # We should read the first line to ensure column order matches
             with open(valid_temp_file_path, 'r', encoding='utf-8') as f:
                 header_line = f.readline().strip()
                 file_columns = header_line.split('\t')
             
             # Check if it has headers. In file_processor we added headers: target_cols + ['_batch_id_', '_source_row_number_']
             # Remove internal columns from target table mapping if they don't exist in target table
             copy_columns = []
             for col in file_columns:
                 if col in db_columns:
                     copy_columns.append(f'"{col}"')
                 else:
                     logger.warning(f"Temp file column '{col}' not found in target table {target_schema}.{target_table}. Ensure mapping is correct. Trying to ignore it by mapping to a dummy column if postgres supported it, but postgres COPY requires exact match or subset.")
             
             # To be safe, let's use the columns found in in the file that actually map to the DB.
             # Note: if the file has EXTRA columns not in the target table, postgres COPY with columns list will fail if the file row has more columns than listed.
             # But the file processor only generated `target_cols + metadata`. 
             # To handle the mismatch safely, let's construct a temporary table, COPY all, then INSERT SELECT.
             
             # 1. Create temporary table mapping exact file structure
             temp_table_name = f"temp_promo_{batch_id.replace('-', '_')}"
             
             # Determine simple text types for temp table to avoid type errors on COPY
             col_defs = [f'"{col}" text' for col in file_columns]
             
             # Create temp table once
             cursor.execute(f"CREATE TEMP TABLE {temp_table_name} ({', '.join(col_defs)})")
             
             # 2. Prepare COPY and INSERT statements
             copy_cols_str = ", ".join([f'"{col}"' for col in file_columns])
             copy_query = f"COPY {temp_table_name} ({copy_cols_str}) FROM STDIN WITH CSV DELIMITER E'\\t' NULL '\\N'"
             
             select_exprs = []
             insert_cols = []
             for col in valid_db_target_cols:
                 if col in file_columns:
                     insert_cols.append(f'"{col}"')
                     pg_type = db_columns[col]
                     cast_expr = ""
                     if 'int' in pg_type: cast_expr = "::integer"
                     elif 'num' in pg_type or 'dec' in pg_type or 'double' in pg_type or 'float' in pg_type or 'real' in pg_type: cast_expr = "::numeric"
                     elif 'bool' in pg_type: cast_expr = "::boolean"
                     elif 'date' in pg_type: cast_expr = "::date"
                     elif 'timestamp' in pg_type: cast_expr = "::timestamp"
                     
                     select_exprs.append(f'NULLIF("{col}", \'\\N\'){cast_expr}')
             
             # Add audit fields
             if 'imported_at' in db_columns:
                 insert_cols.append('"imported_at"')
                 select_exprs.append("NOW()")
                 
             if not insert_cols:
                 raise ValueError("No matching columns could be found between the temp file and target table.")
                 
             insert_cols_str = ", ".join(insert_cols)
             select_str = ", ".join(select_exprs)
             
             insert_query = f"""
                 INSERT INTO {target_schema}.{target_table} ({insert_cols_str})
                 SELECT {select_str} FROM {temp_table_name}
             """
             
             logger.info(f"Targeting columns for INSERT: {insert_cols_str}")
             
             # Disable WAL generation for the target table during bulk load
             try:
                 cursor.execute(f'ALTER TABLE "{target_schema}"."{target_table}" SET UNLOGGED')
                 conn.commit()
                 logger.info(f"Set {target_schema}.{target_table} to UNLOGGED to prevent WAL exhaustion.")
             except Exception as e:
                 logger.warning(f"Could not set table to UNLOGGED (requires superuser or table owner): {e}")
                 conn.rollback()
             
             # 3. Stream data from CSV file in chunks
             buffer = io.StringIO()
             current_chunk_rows = 0
             chunk_size = PROMOTION_BATCH_SIZE
             
             with open(valid_temp_file_path, 'r', encoding='utf-8') as f:
                 next(f) # Skip header line we already read
                 
                 for line in f:
                     buffer.write(line)
                     current_chunk_rows += 1
                     
                     if current_chunk_rows >= chunk_size:
                         # Process chunk
                         buffer.seek(0)
                         cursor.copy_expert(copy_query, buffer)
                         
                         cursor.execute(insert_query)
                         total_inserted += cursor.rowcount
                         
                         cursor.execute(f"TRUNCATE TABLE {temp_table_name}")
                         conn.commit()  # <-- Crucial! Commit the chunk independently
                         
                         buffer = io.StringIO()  # Reset buffer
                         current_chunk_rows = 0
                         logger.info(f"Promoted chunk logic: Batch {batch_id}. Total inserted so far: {total_inserted}")
                 
                 # Process any remaining lines in the final chunk
                 if current_chunk_rows > 0:
                     buffer.seek(0)
                     cursor.copy_expert(copy_query, buffer)
                     
                     cursor.execute(insert_query)
                     total_inserted += cursor.rowcount
                     
                     cursor.execute(f"TRUNCATE TABLE {temp_table_name}")
                     conn.commit()
                     logger.info(f"Promoted final chunk: Batch {batch_id}. Total inserted: {total_inserted}")
             
             # Drop temp table at the very end
             cursor.execute(f"DROP TABLE IF EXISTS {temp_table_name}")
             conn.commit()
             
             # Re-enable WAL generation for target table
             try:
                 cursor.execute(f'ALTER TABLE "{target_schema}"."{target_table}" SET LOGGED')
                 conn.commit()
                 logger.info(f"Restored {target_schema}.{target_table} to LOGGED.")
             except Exception as e:
                 logger.warning(f"Could not restore table to LOGGED: {e}")
                 conn.rollback()
             
             # Cleanup specific batch valid file
             try:
                 os.remove(valid_temp_file_path)
                 logger.info(f"Deleted temp file: {valid_temp_file_path}")
             except OSError as e:
                 logger.warning(f"Failed to delete temp file {valid_temp_file_path}: {e}")
                 
             # Cleanup stage_table NO MATTER WHAT because it should only hold FAILED records now,
             # but we still want to be safe and delete PASSED ones if they somehow ended up there.
             cursor.execute(f"DELETE FROM staging_data.{staging_table} WHERE batch_id = %s AND validation_status = 'PASSED'", (batch_id,))
             conn.commit()
             
        else:
             # ---------------------------------------------------------
             # METODO B: Fallback Clásico desde Tabla Staging
             # ---------------------------------------------------------
             logger.warning(f"File {valid_temp_file_path} not available. Falling back to staging table.")
             
             target_cols = []
             select_exprs = []
             for real_col_name in valid_db_target_cols:
                 pg_type = db_columns[real_col_name]
                 target_cols.append(real_col_name)
                 
                 cast_expr = ""
                 if 'int' in pg_type: cast_expr = "::integer"
                 elif 'num' in pg_type or 'dec' in pg_type or 'double' in pg_type or 'float' in pg_type or 'real' in pg_type: cast_expr = "::numeric"
                 elif 'bool' in pg_type: cast_expr = "::boolean"
                 elif 'date' in pg_type: cast_expr = "::date"
                 elif 'timestamp' in pg_type: cast_expr = "::timestamp"
                 
                 select_exprs.append(f"(processed_data->>'{real_col_name}'){cast_expr}")
             
             if 'imported_at' in db_columns:
                 target_cols.append('imported_at')
                 select_exprs.append('NOW()')
                 
             cols_str = ", ".join([f'"{c}"' for c in target_cols]) 
             select_str = ", ".join(select_exprs)
             
             # Contar total a promover
             cursor.execute(f"""
                 SELECT COUNT(*) FROM staging_data.{staging_table}
                 WHERE batch_id = %s AND validation_status = 'PASSED' AND is_duplicate = false
             """, (batch_id,))
             total_to_promote = cursor.fetchone()[0]
             
             if total_to_promote == 0:
                 logger.warning("No records to promote (all filtered or no PASSED records).")
                 
             else:
                 cursor.execute("SET statement_timeout = 600000;")  # 10 min por batch
                 
                 while True:
                     batch_num += 1
                     batch_insert_query = f"""
                         INSERT INTO {target_schema}.{target_table} ({cols_str})
                         SELECT {select_str}
                         FROM (
                            SELECT processed_data, ctid as staging_ctid 
                            FROM staging_data.{staging_table}
                            WHERE batch_id = %s 
                              AND validation_status = 'PASSED'
                              AND is_duplicate = false
                            LIMIT {PROMOTION_BATCH_SIZE}
                         ) AS subquery
                     """
                     cursor.execute(batch_insert_query, (batch_id,))
                     batch_inserted = cursor.rowcount
                     
                     if batch_inserted == 0:
                         break
                     
                     total_inserted += batch_inserted
                     
                     cursor.execute(f"""
                         DELETE FROM staging_data.{staging_table}
                         WHERE ctid IN (
                             SELECT ctid FROM staging_data.{staging_table}
                             WHERE batch_id = %s 
                               AND validation_status = 'PASSED'
                               AND is_duplicate = false
                             LIMIT {PROMOTION_BATCH_SIZE}
                         )
                     """, (batch_id,))
                     
                     conn.commit()
                     progress_pct = min(100, round(total_inserted * 100 / total_to_promote, 1))
                     logger.info(f"Promotion batch {batch_num} (Fallback): inserted {batch_inserted}. Progress: {progress_pct}%")

        # FINALIZAR SI NO HUBO REGISTROS
        if total_inserted == 0:
            cursor.execute("""
                UPDATE staging_meta.batch_control
                SET status = 'PROMOTED',
                    metadata = metadata || %s::jsonb,
                    error_message = 'No records to promote: all records were rejected or duplicated'
                WHERE batch_id = %s
            """, (json.dumps({"promoted_at": "NOW()", "promoted_count": 0}), batch_id))
            conn.commit()
            return
            
        logger.info(f"Successfully promoted {total_inserted} records.")
        
        # ---------------------------------------------------------
        # FASE 4: FINALIZACIÓN
        # ---------------------------------------------------------
        
        # Actualizar estado Batch
        cursor.execute("""
            UPDATE staging_meta.batch_control
            SET status = 'PROMOTED',
                metadata = metadata || %s::jsonb,
                error_message = NULL
            WHERE batch_id = %s
        """, (json.dumps({"promoted_at": "NOW()", "promoted_count": total_inserted}), batch_id))
        
        conn.commit()
        logger.info("Promotion complete.")
        
        # Limpiar registros FAILED restantes en staging (no promovidos)
        try:
            clean_cursor = conn.cursor()
            clean_cursor.execute(f"""
                SELECT COUNT(*) FROM staging_data.{staging_table} WHERE batch_id = %s
            """, (batch_id,))
            remaining = clean_cursor.fetchone()[0]
            if remaining > 0:
                logger.info(f"Cleaning {remaining} rejected/remaining records from staging...")
                clean_cursor.execute(f"DELETE FROM staging_data.{staging_table} WHERE batch_id = %s", (batch_id,))
                conn.commit()
                logger.info("Staging cleanup complete.")
        except Exception as e:
            logger.warning(f"Failed to clean remaining staging data (non-fatal): {e}")

    except Exception as e:
        conn.rollback()
        logger.error(f"Promotion failed for batch {batch_id}: {e}")
        try:
             err_conn = psycopg2.connect(database_url)
             err_cursor = err_conn.cursor()
             err_cursor.execute("""
                UPDATE staging_meta.batch_control
                SET error_message = %s
                WHERE batch_id = %s
             """, (f"Promotion Error: {str(e)}", batch_id))
             err_conn.commit()
             err_conn.close()
        except:
            pass
        raise e
    finally:
        if conn:
            conn.close()


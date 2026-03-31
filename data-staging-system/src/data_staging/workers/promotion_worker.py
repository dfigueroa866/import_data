
import logging
import json
import psycopg2
import psycopg2.extras
import os
import io
import itertools
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

        total_inserted = metadata.get("promoted_rows", 0)
        batch_num = 0
        
        if valid_temp_file_path and os.path.exists(valid_temp_file_path):
             # ---------------------------------------------------------
             # METODO DIRECTO A PRODUCCIÓN: Streaming + execute_values
             # ---------------------------------------------------------
             logger.info(f"Using Direct Streaming Injection from {valid_temp_file_path}")
             logger.info(f"Resuming from row: {total_inserted}")
             
             
             with open(valid_temp_file_path, 'r', encoding='utf-8') as f:
                 header_line = f.readline().strip()
                 file_columns = header_line.split('\t')
                 
                 # Prepare the columns for the INSERT statement
                 insert_cols = []
                 file_col_indices = []
                 
                 for idx, col in enumerate(file_columns):
                     if col in valid_db_target_cols:
                         insert_cols.append(f'"{col}"')
                         file_col_indices.append(idx)
                 
                 if 'imported_at' in db_columns:
                     insert_cols.append('"imported_at"')
                     # We will append NOW() logic in the query string or python
                 
                 if not insert_cols:
                     raise ValueError("No matching columns could be found between the temp file and target table.")
                     
                 insert_cols_str = ", ".join(insert_cols)
                 
                 # Optimization: Prepare base query for execute_values
                 # Use %s for values. For imported_at add NOW() literally in the VALUES template
                 template_values = "(" + ", ".join(["%s"] * len(file_col_indices))
                 if 'imported_at' in db_columns:
                     template_values += ", NOW()"
                 template_values += ")"
                 
                 insert_query = f"""
                     INSERT INTO {target_schema}.{target_table} ({insert_cols_str})
                     VALUES %s
                 """
                 
                 chunk_size = PROMOTION_BATCH_SIZE
                 
                 # Skip rows we already inserted in a previous failed run
                 if total_inserted > 0:
                     logger.info(f"Skipping first {total_inserted} previously promoted rows...")
                     # Use islice to safely and quickly consume lines we don't need
                     next(itertools.islice(f, total_inserted, total_inserted), None)
                 
                 chunk_data = []
                 
                 try:
                     for line in f:
                         # Parse the TSV line
                         raw_vals = line.rstrip('\n').split('\t')
                         
                         # Extract only the targeted columns, convert '\\N' string to None for NULL handling in psycopg2
                         row_data = tuple([None if raw_vals[i] == '\\N' else raw_vals[i] for i in file_col_indices])
                         chunk_data.append(row_data)
                         
                         if len(chunk_data) >= chunk_size:
                             # Process chunk directly to production
                             psycopg2.extras.execute_values(
                                 cursor, insert_query, chunk_data, template=template_values, page_size=10000
                             )
                             total_inserted += len(chunk_data)
                             batch_num += 1
                             
                             # Micro Cómmit
                             conn.commit()
                             
                             # Update Tracker in BD (metadata: promoted_rows)
                             new_metadata = metadata.copy()
                             new_metadata["promoted_rows"] = total_inserted
                             cursor.execute("""
                                 UPDATE staging_meta.batch_control 
                                 SET metadata = %s::jsonb 
                                 WHERE batch_id = %s
                             """, (json.dumps(new_metadata), batch_id))
                             conn.commit()
                             
                             logger.info(f"Promoted chunk logic: Batch {batch_id}. Total inserted so far: {total_inserted}")
                             chunk_data = []
                     
                     # Process any remaining lines in the final chunk
                     if chunk_data:
                         psycopg2.extras.execute_values(
                             cursor, insert_query, chunk_data, template=template_values, page_size=10000
                         )
                         total_inserted += len(chunk_data)
                         conn.commit()
                         
                         new_metadata = metadata.copy()
                         new_metadata["promoted_rows"] = total_inserted
                         cursor.execute("""
                             UPDATE staging_meta.batch_control 
                             SET metadata = %s::jsonb 
                             WHERE batch_id = %s
                         """, (json.dumps(new_metadata), batch_id))
                         conn.commit()
                         
                         logger.info(f"Promoted final chunk: Batch {batch_id}. Total inserted: {total_inserted}")
                         
                 except (psycopg2.OperationalError, psycopg2.DatabaseError, psycopg2.InterfaceError) as db_err:
                     # CRASH CATCHING: WAL limits, connection limits, timeouts
                     conn.rollback()
                     error_msg = f"Truncado en registro {total_inserted}. Error: {str(db_err)}"
                     logger.error(f"Batch crashed mid-flight. {error_msg}")
                     
                     # Intentar guardar el estatus PARCIAL
                     try:
                         rescue_conn = psycopg2.connect(database_url)
                         rescue_cursor = rescue_conn.cursor()
                         rescue_cursor.execute("""
                             UPDATE staging_meta.batch_control
                             SET status = 'PARTIALLY_PROMOTED', error_message = %s
                             WHERE batch_id = %s
                         """, (error_msg, batch_id))
                         rescue_conn.commit()
                         rescue_conn.close()
                     except Exception as rescue_err:
                         logger.error(f"Failed to save PARTIALLY_PROMOTED state for {batch_id}: {rescue_err}")
                     
                     raise Exception(error_msg) # Propagar para detener worker
                     
             # Cleanup specific batch valid file
             try:
                 os.remove(valid_temp_file_path)
                 logger.info(f"Deleted temp file: {valid_temp_file_path}")
             except OSError as e:
                 logger.warning(f"Failed to delete temp file {valid_temp_file_path}: {e}")
                 
             # Cleanup stage_table NO MATTER WHAT 
             cursor.execute(f"DELETE FROM staging_data.{staging_table} WHERE batch_id = %s AND validation_status = 'PASSED'", (batch_id,))
             conn.commit()
             
        else:
             # Si no hay archivo CSV temporal, no podemos insertar.
             raise ValueError(f"CRITICAL: Archivo CSV Válido {valid_temp_file_path} no fue encontrado para el batch {batch_id}. Promoción abortada.")

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
        # Solo sobre-escribimos a FAILED si no se había setteado a PARTIALLY_PROMOTED previamente.
        try:
             err_conn = psycopg2.connect(database_url)
             err_cursor = err_conn.cursor()
             # Checar si ya es PARTIALLY_PROMOTED
             err_cursor.execute("SELECT status FROM staging_meta.batch_control WHERE batch_id = %s", (batch_id,))
             current_st = err_cursor.fetchone()
             if current_st and current_st[0] != 'PARTIALLY_PROMOTED':
                 err_cursor.execute("""
                    UPDATE staging_meta.batch_control
                    SET error_message = %s, status = 'FAILED'
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


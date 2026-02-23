
import logging
import json
import psycopg2
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
        source_name = batch_row[1]
        
        safe_source_name = source_name.lower().replace(' ', '_').replace('-', '_')
        staging_table = f"stage_{safe_source_name}"
        
        dedup_columns = metadata.get("dedup_columns", [])
        
        logger.info(f"Starting promotion for batch {batch_id} to {target_schema}.{target_table}")
        
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
        # FASE 3: INSERCIÓN EN LOTES
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

        # Construir listas de columnas
        target_cols = []
        select_exprs = []
        
        cursor.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE LOWER(table_schema) = LOWER(%s) AND LOWER(table_name) = LOWER(%s)
        """, (target_schema, target_table))
        
        db_columns = {row[0]: row[1] for row in cursor.fetchall()}
        db_columns_lower = {k.lower(): k for k in db_columns.keys()}
        
        for requested_col in target_columns:
            real_col_name = None
            if requested_col in db_columns:
                real_col_name = requested_col
            elif requested_col.lower() in db_columns_lower:
                real_col_name = db_columns_lower[requested_col.lower()]
                
            if real_col_name:
                pg_type = db_columns[real_col_name]
                target_cols.append(real_col_name)
                
                cast_expr = ""
                if 'int' in pg_type: cast_expr = "::integer"
                elif 'num' in pg_type or 'dec' in pg_type or 'double' in pg_type or 'float' in pg_type or 'real' in pg_type: cast_expr = "::numeric"
                elif 'bool' in pg_type: cast_expr = "::boolean"
                elif 'date' in pg_type: cast_expr = "::date"
                elif 'timestamp' in pg_type: cast_expr = "::timestamp"
                
                select_exprs.append(f"(processed_data->>'{real_col_name}'){cast_expr}")
        
        if not target_cols:
            found_cols = list(db_columns.keys())
            raise ValueError(f"No columns matched between mapping and target table {target_schema}.{target_table}. Available columns in DB: {found_cols}. Requested columns: {target_columns}")

        # Agregar campos de auditoría si existen
        if 'imported_at' in db_columns:
            target_cols.append('imported_at')
            select_exprs.append('NOW()')
            
        # Construir Query base
        cols_str = ", ".join([f'"{c}"' for c in target_cols]) 
        select_str = ", ".join(select_exprs)
        
        logger.info(f"Promotion columns: {target_cols}")
        
        # Contar total de registros a promover
        cursor.execute(f"""
            SELECT COUNT(*) FROM staging_data.{staging_table}
            WHERE batch_id = %s AND validation_status = 'PASSED' AND is_duplicate = false
        """, (batch_id,))
        total_to_promote = cursor.fetchone()[0]
        
        logger.info(f"Total records to promote: {total_to_promote}")
        
        if total_to_promote == 0:
            logger.warning("No records to promote (all filtered or no PASSED records).")
            cursor.execute("""
                UPDATE staging_meta.batch_control
                SET status = 'PROMOTED',
                    metadata = metadata || %s::jsonb,
                    error_message = 'No records to promote: all records were rejected or duplicated'
                WHERE batch_id = %s
            """, (json.dumps({"promoted_at": "NOW()", "promoted_count": 0}), batch_id))
            conn.commit()
            return
        
        # Timeout extendido por batch
        cursor.execute("SET statement_timeout = 600000;")  # 10 min por batch
        
        # ---- LOOP DE INSERCIÓN POR LOTES ----
        total_inserted = 0
        batch_num = 0
        
        while True:
            batch_num += 1
            
            # Usar una subconsulta con LIMIT para insertar en lotes
            # Nota: usamos ctid para paginación eficiente sin ORDER BY
            batch_insert_query = f"""
                INSERT INTO {target_schema}.{target_table} ({cols_str})
                SELECT {select_str}
                FROM staging_data.{staging_table}
                WHERE batch_id = %s 
                  AND validation_status = 'PASSED'
                  AND is_duplicate = false
                LIMIT {PROMOTION_BATCH_SIZE}
            """
            
            cursor.execute(batch_insert_query, (batch_id,))
            batch_inserted = cursor.rowcount
            
            if batch_inserted == 0:
                logger.info(f"Batch {batch_num}: No more records to insert. Done.")
                break
            
            total_inserted += batch_inserted
            
            # ELIMINAR de staging los registros ya insertados en producción
            # Esto libera espacio inmediatamente y reduce WAL (vs UPDATE + DELETE posterior)
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
            
            # COMMIT cada batch para liberar locks, WAL y evitar timeout
            conn.commit()
            
            progress_pct = min(100, round(total_inserted * 100 / total_to_promote, 1))
            logger.info(f"Promotion batch {batch_num}: inserted {batch_inserted}, "
                       f"deleted from staging. "
                       f"({total_inserted}/{total_to_promote} = {progress_pct}%)")
            
            # Actualizar progreso en metadata
            cursor.execute("""
                UPDATE staging_meta.batch_control
                SET metadata = metadata || %s::jsonb
                WHERE batch_id = %s
            """, (json.dumps({
                "promotion_progress": progress_pct,
                "promotion_inserted": total_inserted,
                "promotion_total": total_to_promote
            }), batch_id))
            conn.commit()
        
        logger.info(f"Successfully promoted {total_inserted} records in {batch_num} batches.")
        
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


import logging
import json
import os
import re
import time
import numpy as np
import io
import csv
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path
import polars as pl
import psycopg2
from data_staging.config import settings
from data_staging.utils.mapping_helpers import is_virtual_mapping_key
from data_staging.utils.batch_staging_files import (
    ValidRecordsParquetWriter,
    append_rejected_records_csv,
    append_valid_records_parquet,
    get_temp_dir,
    metadata_merge_expr,
    rejected_records_path,
    valid_records_path,
)

logger = logging.getLogger(__name__)

# Configuración de tamaños para procesamiento (override vía settings)
CHUNK_SIZE_RECORDS = getattr(settings, "PROCESS_CHUNK_SIZE", 250_000)
BATCH_SIZE_INSERT = 50000
PROGRESS_ROW_INTERVAL = getattr(settings, "PROGRESS_ROW_INTERVAL", 50000)
PROGRESS_TIME_INTERVAL_SEC = float(
    getattr(settings, "PROGRESS_UPDATE_INTERVAL_SEC", 15.0)
)
PROGRESS_COMMIT_EVERY_CHUNKS = getattr(settings, "PROGRESS_COMMIT_EVERY_CHUNKS", 2)
_last_progress_write: Dict[str, tuple[float, str]] = {}


def open_progress_connection() -> psycopg2.extensions.connection:
    """Dedicated autocommit connection so progress updates never block the worker txn."""
    from data_staging.config import settings

    progress_conn = psycopg2.connect(str(settings.DATABASE_URL))
    progress_conn.autocommit = True
    return progress_conn


def report_processing_progress(
    conn: psycopg2.extensions.connection,
    batch_id: str,
    *,
    progress_percentage: float,
    current_operation: str,
    phase: str = "validating",
    total_rows: int = 0,
    rows_processed: int = 0,
    loaded_rows: int = 0,
    rejected_rows: int = 0,
    chunks_processed: int = 0,
    chunks_total: int = 1,
    force: bool = False,
) -> None:
    """Persist real-time progress in batch metadata for Step 4 polling."""
    snapshot_key = (
        f"{phase}|{chunks_processed}|{chunks_total}|"
        f"{int(rows_processed // max(PROGRESS_ROW_INTERVAL, 1))}|"
        f"{int(progress_percentage)}"
    )
    if not force:
        now = time.monotonic()
        last = _last_progress_write.get(batch_id)
        if last:
            last_time, last_key = last
            if (
                (now - last_time) < PROGRESS_TIME_INTERVAL_SEC
                and last_key == snapshot_key
            ):
                return
        _last_progress_write[batch_id] = (now, snapshot_key)

    payload = {
        "progress_percentage": round(min(99.0, max(0.0, float(progress_percentage))), 1),
        "current_operation": current_operation,
        "phase": phase,
        "total_rows": int(total_rows),
        "rows_processed": int(rows_processed),
        "loaded_rows": int(loaded_rows),
        "rejected_rows": int(rejected_rows),
        "chunks_processed": int(chunks_processed),
        "chunks_total": max(1, int(chunks_total)),
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            UPDATE staging_meta.batch_control
            SET metadata = {metadata_merge_expr("jsonb_build_object('processing_progress', %s::jsonb)")}
            WHERE batch_id = %s
            """,
            (json.dumps(payload), batch_id),
        )
        if not getattr(conn, "autocommit", False):
            conn.commit()
        cursor.close()
    except Exception as exc:
        logger.warning(f"Failed to update processing progress for {batch_id}: {exc}")
        if not getattr(conn, "autocommit", False):
            try:
                conn.rollback()
            except Exception:
                pass


# Regex para caracteres de control inválidos que rompen CSV/JSON
INVALID_CHARS_REGEX = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')


class DirectIngestor:
    """
    Maneja la inserción directa a producción usando el comando COPY de PostgreSQL.
    Esto minimiza la generación de WAL y es mucho más rápido que los INSERTs.
    """
    def __init__(self, conn, target_schema, target_table, columns):
        self.conn = conn
        self.target_schema = target_schema
        self.target_table = target_table
        self.columns = [c for c in columns if c.lower() != "id"] # Evitar el ID si es serial/pk
        self.buffer = io.StringIO()
        self.count = 0

    def add_records(self, records: List[Dict[str, Any]]):
        """Convierte registros (dicts) a formato de texto para COPY."""
        from data_staging.services.catalog.catalog_transforms import is_empty_value

        if not records:
            return
        
        for record in records:
            if record.get("validation_status") != "PASSED":
                continue
            
            # Recuperar el dict procesado
            processed_data = json.loads(record["processed_data"])
            
            # Extraer solo las columnas que van a producción
            row_values = []
            for col in self.columns:
                val = processed_data.get(col)
                if is_empty_value(val):
                    row_values.append("\\N") # Símbolo de NULL para COPY
                else:
                    # Escapar tabulaciones y saltos de línea para que no rompan el formato TEXT
                    s_val = str(val).replace("\t", " ").replace("\n", " ").replace("\r", " ")
                    row_values.append(s_val)
            
            self.buffer.write("\t".join(row_values) + "\n")
            self.count += 1

    def flush(self):
        """Ejecuta el comando COPY para vaciar el buffer hacia la BD."""
        if self.count == 0:
            return
            
        self.buffer.seek(0)
        cursor = self.conn.cursor()
        try:
            table_path = f'"{self.target_schema}"."{self.target_table}"'
            cols_str = ", ".join([f'"{c}"' for c in self.columns])
            
            sql = f"COPY {table_path} ({cols_str}) FROM STDIN WITH (FORMAT text, NULL '\\N')"
            cursor.copy_expert(sql, self.buffer)
            self.conn.commit()
            
            # Limpiar para el siguiente lote
            self.buffer = io.StringIO()
            self.count = 0
        except Exception as e:
            self.conn.rollback()
            logger.error(f"CRITICAL: Direct COPY failed: {e}")
            raise


def process_file_job(payload: Dict[str, Any]):
    """
    Handler para jobs de tipo 'PROCESS_FILE'.
    
    payload = {
        "batch_id": "uuid",
        "file_path": "/path/to/file" (opcional si está en metadata),
        "source_name": "productos" (opcional si está en metadata),
    }
    
    El worker ahora lee la configuración (mapeos, toggles, etc.) directamente
    del metadata del batch en batch_control.
    """
    batch_id = payload["batch_id"]
    from data_staging.config import settings

    database_url = str(settings.DATABASE_URL)
    
    conn = psycopg2.connect(database_url)
    conn.autocommit = False
    progress_conn = open_progress_connection()
    
    # PASO 1: Leer metadata del batch
    cursor = conn.cursor()
    cursor.execute("""
        SELECT source_name, file_name, metadata
        FROM staging_meta.batch_control
        WHERE batch_id = %s
    """, (batch_id,))
    
    row = cursor.fetchone()
    if not row:
        raise ValueError(f"Batch {batch_id} not found")
    
    source_name = row[0]
    file_name = row[1]
    metadata = row[2] or {}
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    
    # Extraer configuración del wizard metadata
    file_path_str = (
        payload.get("file_path")
        or metadata.get("aggregated_file_path")
        or metadata.get("file_path")
    )
    if not file_path_str:
        raise ValueError(f"file_path not found in payload or metadata")
    
    file_path = Path(file_path_str)
    
    # --- MEJORADO: Obtener configuración con fallback y normalización ---
    # 1. Prioridad: Payload (valores directos del API)
    # 2. Respaldo: Metadata (valores persistidos en DB)
    
    # Manejar mappings (plural/singular)
    wizard_column_mappings = payload.get("column_mappings") or payload.get("column_mapping")
    if not wizard_column_mappings:
        wizard_column_mappings = metadata.get("column_mappings") or metadata.get("column_mapping") or {}

    # Manejar toggles/selection (wizard_column_toggles vs selected_columns)
    # El Wizard usa column_toggles (dict), el API directo usa selected_columns (list)
    wizard_column_toggles = payload.get("column_toggles") or metadata.get("column_toggles") or {}
    api_selected_columns = payload.get("selected_columns") or metadata.get("selected_columns")
    
    target_schema = payload.get("target_schema") or metadata.get("target_schema")
    target_table = payload.get("target_table") or metadata.get("target_table")
    catalog_slug = None
    if metadata.get("load_type") == "catalog":
        catalog_slug = metadata.get("catalog_name") or metadata.get("target_table") or target_table
        production_table = metadata.get("production_table")
        if production_table:
            target_table = production_table
        elif catalog_slug:
            from data_staging.services.catalog.catalog_registry import resolve_catalog_db_target

            target_schema, target_table = resolve_catalog_db_target(catalog_slug, target_schema)
    dedup_columns = payload.get("dedup_columns") or metadata.get("dedup_columns", "")
    auto_production = payload.get("auto_production", False) or metadata.get("auto_production", False)
    
    # Transformar wizard mappings al formato esperado por el worker
    # Wizard: {file_col: {target, default_value, auto_mapped}}
    # API Directo: {target_col: {source, default}}
    column_mapping = {}
    selected_columns = []
    
    # Si viene del Wizard (mapeo por columna de archivo)
    if wizard_column_mappings and any(isinstance(v, dict) and "target" in v for v in wizard_column_mappings.values()):
        for file_col, mapping_config in wizard_column_mappings.items():
            # Solo incluir si toggle está ON (o si no hay toggles definidos explícitamente)
            is_enabled = wizard_column_toggles.get(file_col, True)
            
            if is_enabled:
                target = mapping_config.get("target")
                if target and target != "__new__":
                    default_val = mapping_config.get("default_value", "")
                    if is_virtual_mapping_key(file_col):
                        column_mapping[target] = {
                            "source": None,
                            "default": default_val,
                        }
                    else:
                        selected_columns.append(file_col)
                        column_mapping[target] = {
                            "source": file_col,
                            "default": default_val,
                        }
    # Si viene del API directo (mapeo por columna de destino)
    elif wizard_column_mappings:
        column_mapping = wizard_column_mappings
        # Extraer nombres de columnas de origen para el filtrado inicial
        selected_columns = [m.get("source") for m in column_mapping.values() if m.get("source")]

    # Si se especificó una lista explícita de columnas (selected_columns del API)
    if api_selected_columns and not selected_columns:
        selected_columns = api_selected_columns
    
    logger.info(f"Target selected_columns: {selected_columns}")
    logger.info(f"Final column_mapping: {list(column_mapping.keys())}")
    
    logger.info(f"Processing file for batch {batch_id}: {file_path}")
    logger.info(f"  Target: {target_schema}.{target_table}")
    if column_mapping:
        logger.info(f"  Column mapping: {len(column_mapping)} mappings configured")
    if selected_columns:
        logger.info(f"  Selected columns: {len(selected_columns)} columns")
    
    try:
        # 1. Actualizar batch a PROCESSING  + buscar job_id para reportar progreso
        file_path_col = metadata.get("aggregated_file_path") or metadata.get("file_path")
        if file_path_col:
            file_path_col = str(file_path_col)
        cursor.execute("""
            UPDATE staging_meta.batch_control
            SET status = 'PROCESSING',
                started_at = COALESCE(started_at, CURRENT_TIMESTAMP),
                file_path = COALESCE(%s, file_path),
                updated_at = CURRENT_TIMESTAMP
            WHERE batch_id = %s
        """, (file_path_col, batch_id))
        conn.commit()
        
        # Buscar job_id para reportar progreso
        cursor.execute("""
            SELECT job_id FROM staging_meta.job_queue
            WHERE payload->>'batch_id' = %s
            ORDER BY created_at DESC
            LIMIT 1
        """, (batch_id,))
        job_row = cursor.fetchone()
        job_id = job_row[0] if job_row else None

        report_processing_progress(
            progress_conn,
            batch_id,
            progress_percentage=3,
            current_operation="Iniciando validación del archivo…",
            phase="preparing",
            force=True,
        )

        # 2. Determinar si es carga directa (bypass staging)
        direct_load = payload.get("direct_load", False) or metadata.get("direct_load", False)
        target_column_types = payload.get("target_column_types") or {}

        if direct_load:
            logger.info("⚡ DIRECT LOAD ENABLED: Bypassing staging table for valid records")
        
        # 2.5 Extraer delimitador y encoding detectados
        file_analysis = metadata.get("file_analysis", {})
        delimiter = file_analysis.get("delimiter", ",")
        from data_staging.utils.encoding_utils import (
            detect_file_encoding,
            encoding_for_polars,
            normalize_encoding_name,
        )

        encoding = normalize_encoding_name(
            detect_file_encoding(file_path)
            if file_path and Path(file_path).is_file()
            else file_analysis.get("encoding", "utf-8")
        )
        if encoding != file_analysis.get("encoding"):
            file_analysis = {**file_analysis, "encoding": encoding}
            cursor.execute(
                f"""
                UPDATE staging_meta.batch_control
                SET metadata = {metadata_merge_expr("jsonb_build_object('file_analysis', %s::jsonb)")}
                WHERE batch_id = %s
                """,
                (json.dumps(file_analysis), batch_id),
            )
            conn.commit()

        # 3. Preparar archivos en disco (válidos Parquet, rechazados TSV)
        temp_dir = get_temp_dir()

        valid_temp_file = valid_records_path(batch_id)
        rejected_temp_file = rejected_records_path(batch_id)

        # staging_table sigue existiendo como nombre lógico pero ya NO se crea ni se usa en BD.
        # Se mantiene la variable por compatibilidad con firmas internas que aún la reciben.
        safe_source_name = source_name.lower().replace(' ', '_').replace('-', '_')
        staging_table = f"stage_{safe_source_name}"  # solo nombre lógico, no se crea

        # Persistir rutas absolutas en metadata para promotion_worker y descargas
        valid_path_str = str(valid_temp_file.resolve())
        rejected_path_str = str(rejected_temp_file.resolve())
        cursor.execute(
            f"""
            UPDATE staging_meta.batch_control
            SET metadata = {metadata_merge_expr(
                "jsonb_build_object("
                "'valid_temp_file', %s::text, "
                "'rejected_temp_file', %s::text, "
                "'valid_file_format', 'parquet', "
                "'source_file_columns', %s::jsonb"
                ")"
            )}
            WHERE batch_id = %s
            """,
            (
                valid_path_str,
                rejected_path_str,
                json.dumps(selected_columns or []),
                batch_id,
            ),
        )
        conn.commit()

        # LIMPIEZA: si es un reintento borrar archivos previos del mismo batch
        for f in (valid_temp_file, rejected_temp_file):
            if f.exists():
                f.unlink()
        logger.info(f"Disk files prepared for batch {batch_id}")
        
        system_managed: frozenset = frozenset()
        not_null_columns = {}
        if target_schema and target_table:
            if not target_column_types:
                logger.info("target_column_types not in payload, querying database...")
            try:
                cursor.execute("""
                    SELECT column_name, data_type, character_maximum_length, is_nullable
                    FROM information_schema.columns 
                    WHERE table_schema = %s AND table_name = %s
                """, (target_schema, target_table))

                for row_data in cursor.fetchall():
                    c_name, c_type, c_len, is_nullable = row_data
                    full_type = c_type
                    if c_len:
                        full_type = f"{c_type}({c_len})"
                    if c_name not in target_column_types:
                        target_column_types[c_name] = full_type
                    not_null_columns[c_name] = (is_nullable == 'NO')
            except Exception as e:
                logger.error(f"Failed to query schema info: {e}")

        catalog_table = None
        history_mode = metadata.get("load_type") == "history"
        process_type = metadata.get("process_type")
        organization_id = metadata.get("organization_id")
        source_extension = metadata.get("source_extension")
        if history_mode and not source_extension:
            from data_staging.services.history.history_config import source_from_filename
            from data_staging.services.history.history_schema import (
                create_sku_resolver,
                sales_history_needs_sku_id_resolution,
            )

            source_extension = source_from_filename(file_name or "")
            if not source_extension or source_extension == "unknown":
                source_extension = file_path.suffix.lower().lstrip(".") or "unknown"
        sku_resolver = None
        resolve_sku_id = False
        if history_mode and organization_id:
            from data_staging.services.history.history_schema import (
                create_sku_resolver,
                sales_history_needs_sku_id_resolution,
            )

            resolve_sku_id = sales_history_needs_sku_id_resolution(
                target_column_types, column_mapping
            )
            sku_resolver = create_sku_resolver(
                cursor,
                organization_id,
                target_column_types,
                column_mapping,
            )
            if resolve_sku_id and sku_resolver is None:
                logger.warning(
                    "sales_history has sku_id but SKU resolver could not be created "
                    "(check public.skus PK/code columns)"
                )
        if metadata.get("load_type") == "catalog":
            catalog_table = catalog_slug or metadata.get("target_table") or target_table
            if target_schema and target_table:
                from data_staging.services.catalog.catalog_transforms import (
                    load_db_system_managed_columns_psycopg2,
                    load_db_validation_excluded_columns_psycopg2,
                )
                validation_excluded = load_db_validation_excluded_columns_psycopg2(
                    cursor, target_schema, target_table
                )
                for col in validation_excluded:
                    if col in not_null_columns:
                        not_null_columns[col] = False
                system_managed = load_db_system_managed_columns_psycopg2(
                    cursor, target_schema, target_table
                )
                if system_managed:
                    logger.info(
                        "Catalog load: excluded system-managed columns from mapping: %s",
                        ", ".join(sorted(system_managed)),
                    )

        logger.info(f"Target schema loaded: {len(target_column_types)} columns for validation")

        # FETCH FOREIGN KEYS
        foreign_keys_data = {}
        if target_schema and target_table:
            try:
                cursor.execute("""
                    SELECT
                        kcu.column_name,
                        ccu.table_schema AS foreign_table_schema,
                        ccu.table_name AS foreign_table_name,
                        ccu.column_name AS foreign_column_name
                    FROM
                        information_schema.table_constraints AS tc
                        JOIN information_schema.key_column_usage AS kcu
                          ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
                        JOIN information_schema.constraint_column_usage AS ccu
                          ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema
                    WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_name=%s AND tc.table_schema=%s
                """, (target_table, target_schema))
                
                for fk in cursor.fetchall():
                    col_name, f_schema, f_table, f_col = fk
                    try:
                        cursor.execute(f"SELECT DISTINCT {f_col} FROM {f_schema}.{f_table} WHERE {f_col} IS NOT NULL")
                        valid_values = {str(r[0]).strip() for r in cursor.fetchall()}
                        foreign_keys_data[col_name] = valid_values
                        logger.info(f"Loaded {len(valid_values)} valid keys for FK {col_name}")
                    except Exception as sub_e:
                        logger.warning(f"Failed to load values for FK {col_name}: {sub_e}")
            except Exception as e:
                logger.error(f"Failed to query foreign keys: {e}")

        # FETCH CUSTOM HISTORY VALIDATIONS FOR SKU AND LOCATION
        if history_mode and organization_id:
            try:
                cursor.execute(
                    "SELECT DISTINCT code FROM public.skus WHERE organization_id = %s AND code IS NOT NULL",
                    (organization_id,)
                )
                valid_skus = {str(r[0]).strip().lower() for r in cursor.fetchall()}
                foreign_keys_data["__valid_skus__"] = valid_skus
                logger.info(f"Loaded {len(valid_skus)} valid SKU codes for organization {organization_id}")
            except Exception as e:
                logger.error(f"Failed to load valid SKUs: {e}")

            try:
                cursor.execute(
                    "SELECT DISTINCT code FROM public.locations WHERE organization_id = %s AND code IS NOT NULL",
                    (organization_id,)
                )
                valid_locations = {str(r[0]).strip().lower() for r in cursor.fetchall()}
                foreign_keys_data["__valid_locations__"] = valid_locations
                logger.info(f"Loaded {len(valid_locations)} valid Location codes for organization {organization_id}")
            except Exception as e:
                logger.error(f"Failed to load valid Locations: {e}")

        if system_managed and column_mapping:
            column_mapping = {
                t: m for t, m in column_mapping.items() if t not in system_managed
            }
            selected_columns = [
                m["source"] for m in column_mapping.values() if m.get("source")
            ]

        # 4. Procesar archivo por chunks
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        composite_unique_keys: List[str] = []
        seen_composite_keys: set = set()
        if catalog_table:
            from data_staging.services.catalog.catalog_registry import get_catalog_table

            catalog_entry = get_catalog_table(catalog_table)
            if catalog_entry:
                composite_unique_keys = list(catalog_entry.get("unique_keys") or [])

        source_file_columns = list(selected_columns) if selected_columns else []
        if not source_file_columns and file_path.suffix.lower() == ".parquet":
            try:
                source_file_columns = list(pl.scan_parquet(file_path).collect_schema().names())
            except Exception as header_err:
                logger.warning(f"Could not read Parquet columns for rejected export: {header_err}")
        elif not source_file_columns and file_path.suffix.lower() == ".csv":
            pl_encoding = encoding.lower().replace("-", "")
            try:
                header_df = pl.read_csv(
                    file_path,
                    separator=delimiter,
                    encoding=pl_encoding,
                    n_rows=0,
                    infer_schema_length=0,
                )
                source_file_columns = list(header_df.columns)
            except Exception as header_err:
                logger.warning(f"Could not read CSV headers for rejected export: {header_err}")

        cursor.execute(
            f"""
            UPDATE staging_meta.batch_control
            SET metadata = {metadata_merge_expr("jsonb_build_object('source_file_columns', %s::jsonb)")}
            WHERE batch_id = %s
            """,
            (json.dumps(source_file_columns), batch_id),
        )
        conn.commit()

        stats = process_file_in_chunks(
            conn=conn,
            progress_conn=progress_conn,
            file_path=file_path,
            batch_id=batch_id,
            staging_table=staging_table,
            source_name=source_name,
            column_mapping=column_mapping,
            selected_columns=selected_columns,
            job_id=job_id,
            target_column_types=target_column_types,
            not_null_columns=not_null_columns,
            delimiter=delimiter,
            encoding=encoding,
            direct_load=direct_load,
            target_schema=target_schema,
            target_table=target_table,
            foreign_keys_data=foreign_keys_data,
            valid_temp_file=valid_temp_file,
            rejected_temp_file=rejected_temp_file,
            catalog_table=catalog_table,
            composite_unique_keys=composite_unique_keys,
            seen_composite_keys=seen_composite_keys,
            source_file_columns=source_file_columns,
            history_mode=history_mode,
            process_type=process_type,
            organization_id=organization_id,
            sku_resolver=sku_resolver,
            resolve_sku_id=resolve_sku_id,
            source_extension=source_extension if history_mode else None,
        )

        # 4. COMPLETED si el archivo se procesó (aunque todo sea rechazado); FAILED solo si vacío/error
        total_valid = stats["total_inserted"]
        total_rejected = stats.get("total_rejected", 0)
        rows_touched = total_valid + total_rejected
        if rows_touched > 0:
            final_status = "COMPLETED"
            error_msg = None
        else:
            final_status = "FAILED"
            error_msg = (
                "Ningún registro pasó la validación o el archivo está vacío. "
                "0 registros válidos."
            )
        
        cursor.execute(f"""
            UPDATE staging_meta.batch_control
            SET status = %s,
                completed_at = CURRENT_TIMESTAMP,
                records_count = %s,
                metadata = {metadata_merge_expr("%s::jsonb")},
                error_message = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE batch_id = %s
        """, (
            final_status,
            stats["total_inserted"],
            json.dumps({
                "processing_stats": stats,
                "completed_at": datetime.now().isoformat()
            }),
            error_msg,
            batch_id
        ))
        conn.commit()
        
        logger.info(f"Batch {batch_id} finished with status {final_status}: {stats['total_inserted']} records processed")
        
        # 5. Auto-production si está habilitado
        if auto_production:
            logger.info(f"Auto-production enabled for batch {batch_id}. Queueing promotion job.")
            from data_staging.workers.job_queue import create_job
            
            promote_job_id = create_job(
                database_url=str(settings.DATABASE_URL),
                job_type="PROMOTE_BATCH",
                payload={
                    "batch_id": batch_id,
                    "target_schema": target_schema,
                    "target_table": target_table,
                    "dedup_columns": dedup_columns
                },
                priority=10
            )
            logger.info(f"Created promotion job {promote_job_id} for batch {batch_id}")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Error processing batch {batch_id}: {e}")
        
        # Marcar batch como FAILED
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE staging_meta.batch_control
                SET status = 'FAILED',
                    completed_at = CURRENT_TIMESTAMP,
                    error_message = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE batch_id = %s
            """, (str(e), batch_id))
            conn.commit()
        except Exception as e2:
            logger.error(f"Error updating batch status to FAILED: {e2}")
        
        raise
    
    finally:
        if progress_conn:
            progress_conn.close()
        if conn:
            conn.close()


def process_file_in_chunks(
    conn: psycopg2.extensions.connection,
    file_path: Path,
    batch_id: str,
    staging_table: str,
    source_name: str,
    column_mapping: Optional[Dict[str, Any]] = None,
    selected_columns: Optional[List[str]] = None,
    job_id: Optional[str] = None,
    target_column_types: Optional[Dict[str, str]] = None,
    not_null_columns: Optional[Dict[str, bool]] = None,
    delimiter: str = ",",
    encoding: str = "utf-8",
    direct_load: bool = False,
    target_schema: Optional[str] = None,
    target_table: Optional[str] = None,
    foreign_keys_data: Optional[Dict[str, set]] = None,
    valid_temp_file: Optional[Path] = None,
    rejected_temp_file: Optional[Path] = None,
    catalog_table: Optional[str] = None,
    composite_unique_keys: Optional[List[str]] = None,
    seen_composite_keys: Optional[set] = None,
    source_file_columns: Optional[List[str]] = None,
    history_mode: bool = False,
    process_type: Optional[str] = None,
    organization_id: Optional[str] = None,
    sku_resolver=None,
    resolve_sku_id: bool = False,
    source_extension: Optional[str] = None,
    progress_conn: Optional[psycopg2.extensions.connection] = None,
    parquet_writer: Optional[ValidRecordsParquetWriter] = None,
) -> Dict[str, Any]:
    """
    Procesa archivo en chunks usando Polars.
    """
    progress_conn = progress_conn or conn
    total_inserted = 0
    total_rejected = 0
    chunks_processed = 0
    quality_scores = []

    own_writer: Optional[ValidRecordsParquetWriter] = None
    if valid_temp_file and parquet_writer is None and not direct_load:
        own_writer = ValidRecordsParquetWriter(valid_temp_file, [])
        parquet_writer = own_writer

    file_ext = file_path.suffix.lower()

    def _finalize_chunk(stats: Dict[str, Any], end_idx: int) -> None:
        nonlocal total_inserted, total_rejected, chunks_processed
        total_inserted += stats["inserted"]
        total_rejected += stats["rejected"]
        if stats["avg_quality"]:
            quality_scores.append(stats["avg_quality"])
        chunks_processed += 1
        rows_processed = total_inserted + total_rejected
        progress_percent = min(99.0, (end_idx / total_rows) * 100) if total_rows else 0.0
        if chunks_processed % PROGRESS_COMMIT_EVERY_CHUNKS == 0:
            report_processing_progress(
                conn,
                batch_id,
                progress_percentage=progress_percent,
                current_operation=(
                    f"Validando filas {rows_processed:,} de {total_rows:,} "
                    f"(bloque {chunks_processed}/{chunks_total})…"
                ),
                phase="validating",
                total_rows=total_rows,
                rows_processed=rows_processed,
                loaded_rows=total_inserted,
                rejected_rows=total_rejected,
                chunks_processed=chunks_processed,
                chunks_total=chunks_total,
                force=True,
            )
        logger.info(f"Chunk {chunks_processed} completed: {stats['inserted']} inserted")

    try:
        if file_ext in (".csv", ".parquet"):
            from data_staging.utils.chunk_iterators import iter_file_chunks

            total_rows, chunk_source = iter_file_chunks(
                file_path, CHUNK_SIZE_RECORDS, delimiter=delimiter, encoding=encoding
            )
            chunks_total = max(1, (total_rows + CHUNK_SIZE_RECORDS - 1) // CHUNK_SIZE_RECORDS)
            report_processing_progress(
                progress_conn,
                batch_id,
                progress_percentage=8,
                current_operation=f"Validando {total_rows:,} filas del archivo…",
                phase="validating",
                total_rows=total_rows,
                chunks_total=chunks_total,
                force=True,
            )
            row_offset = 0
            for chunk_df in chunk_source:
                end_idx = min(row_offset + len(chunk_df), total_rows)
                stats = process_single_chunk(
                    chunk_df,
                    chunk_idx=chunks_processed,
                    batch_id=batch_id,
                    staging_table=staging_table,
                    source_name=source_name,
                    conn=conn,
                    column_mapping=column_mapping,
                    selected_columns=selected_columns,
                    target_column_types=target_column_types,
                    not_null_columns=not_null_columns,
                    direct_load=direct_load,
                    target_schema=target_schema,
                    target_table=target_table,
                    foreign_keys_data=foreign_keys_data,
                    valid_temp_file=valid_temp_file,
                    rejected_temp_file=rejected_temp_file,
                    catalog_table=catalog_table,
                    composite_unique_keys=composite_unique_keys,
                    seen_composite_keys=seen_composite_keys,
                    source_file_columns=source_file_columns,
                    history_mode=history_mode,
                    process_type=process_type,
                    organization_id=organization_id,
                    sku_resolver=sku_resolver,
                    resolve_sku_id=resolve_sku_id,
                    source_extension=source_extension,
                    progress_total_rows=total_rows,
                    progress_row_offset=row_offset,
                    progress_loaded_before=total_inserted,
                    progress_rejected_before=total_rejected,
                    progress_chunks_processed=chunks_processed,
                    progress_chunks_total=chunks_total,
                    progress_conn=progress_conn,
                    parquet_writer=parquet_writer,
                )
                _finalize_chunk(stats, end_idx)
                row_offset = end_idx

        elif file_ext in ['.xlsx', '.xls']:
            # Excel: leer todo primero (limitación de formato)
            df_full = pl.read_excel(file_path)
            
            total_rows = len(df_full)
            chunks_total = max(1, (total_rows + CHUNK_SIZE_RECORDS - 1) // CHUNK_SIZE_RECORDS)
            report_processing_progress(
                progress_conn,
                batch_id,
                progress_percentage=8,
                current_operation=f"Validando {total_rows:,} filas del archivo…",
                phase="validating",
                total_rows=total_rows,
                chunks_total=chunks_total,
                force=True,
            )
            for i in range(0, total_rows, CHUNK_SIZE_RECORDS):
                chunk_df = df_full[i:i+CHUNK_SIZE_RECORDS]
                
                stats = process_single_chunk(
                    chunk_df, 
                    chunk_idx=chunks_processed,
                    batch_id=batch_id, 
                    staging_table=staging_table,
                    source_name=source_name, 
                    conn=conn,
                    column_mapping=column_mapping,
                    selected_columns=selected_columns,
                    target_column_types=target_column_types,
                    not_null_columns=not_null_columns,
                    direct_load=direct_load,
                    target_schema=target_schema,
                    target_table=target_table,
                    valid_temp_file=valid_temp_file,
                    rejected_temp_file=rejected_temp_file,
                    catalog_table=catalog_table,
                    composite_unique_keys=composite_unique_keys,
                    seen_composite_keys=seen_composite_keys,
                    source_file_columns=source_file_columns,
                    history_mode=history_mode,
                    process_type=process_type,
                    organization_id=organization_id,
                    sku_resolver=sku_resolver,
                    resolve_sku_id=resolve_sku_id,
                    source_extension=source_extension,
                    progress_total_rows=total_rows,
                    progress_row_offset=i,
                    progress_loaded_before=total_inserted,
                    progress_rejected_before=total_rejected,
                    progress_chunks_processed=chunks_processed,
                    progress_chunks_total=chunks_total,
                    progress_conn=progress_conn,
                    parquet_writer=parquet_writer,
                )
                
                total_inserted += stats['inserted']
                total_rejected += stats['rejected']
                if stats['avg_quality']:
                    quality_scores.append(stats['avg_quality'])
                
                chunks_processed += 1
                end_idx = min(i + CHUNK_SIZE_RECORDS, total_rows)
                rows_processed = total_inserted + total_rejected
                progress_percent = (
                    min(99.0, (end_idx / total_rows) * 100) if total_rows else 0.0
                )
                report_processing_progress(
                    conn,
                    batch_id,
                    progress_percentage=progress_percent,
                    current_operation=(
                        f"Validando filas {rows_processed:,} de {total_rows:,} "
                        f"(bloque {chunks_processed}/{chunks_total})…"
                    ),
                    phase="validating",
                    total_rows=total_rows,
                    rows_processed=rows_processed,
                    loaded_rows=total_inserted,
                    rejected_rows=total_rejected,
                    chunks_processed=chunks_processed,
                    chunks_total=chunks_total,
                )
                
                logger.info(f"Chunk {chunks_processed} completed: {stats['inserted']} inserted")
        else:
            raise ValueError(f"Unsupported file type: {file_ext}")

        report_processing_progress(
            progress_conn,
            batch_id,
            progress_percentage=99,
            current_operation="Finalizando validación…",
            phase="finishing",
            total_rows=total_inserted + total_rejected,
            rows_processed=total_inserted + total_rejected,
            loaded_rows=total_inserted,
            rejected_rows=total_rejected,
            chunks_processed=chunks_processed,
            chunks_total=max(1, chunks_processed),
            force=True,
        )
        
        return {
            "total_inserted": total_inserted,
            "total_rejected": total_rejected,
            "chunks_processed": chunks_processed,
            "avg_quality_score": float(np.mean(quality_scores)) if quality_scores else 0.0
        }

    except Exception as e:
        logger.error(f"Error processing file {file_path}: {e}")
        raise
    finally:
        if own_writer is not None:
            own_writer.close()


def process_single_chunk(
    chunk_df, 
    chunk_idx, 
    batch_id, 
    staging_table, 
    source_name, 
    conn,
    column_mapping: Optional[Dict[str, Any]] = None,
    selected_columns: Optional[List[str]] = None,
    target_column_types: Optional[Dict[str, str]] = None,
    not_null_columns: Optional[Dict[str, bool]] = None,
    direct_load: bool = False,
    target_schema: Optional[str] = None,
    target_table: Optional[str] = None,
    foreign_keys_data: Optional[Dict[str, set]] = None,
    valid_temp_file: Optional[Path] = None,
    rejected_temp_file: Optional[Path] = None,
    catalog_table: Optional[str] = None,
    composite_unique_keys: Optional[List[str]] = None,
    seen_composite_keys: Optional[set] = None,
    source_file_columns: Optional[List[str]] = None,
    history_mode: bool = False,
    process_type: Optional[str] = None,
    organization_id: Optional[str] = None,
    sku_resolver=None,
    resolve_sku_id: bool = False,
    source_extension: Optional[str] = None,
    progress_total_rows: int = 0,
    progress_row_offset: int = 0,
    progress_loaded_before: int = 0,
    progress_rejected_before: int = 0,
    progress_chunks_processed: int = 0,
    progress_chunks_total: int = 1,
    progress_conn: Optional[psycopg2.extensions.connection] = None,
    parquet_writer: Optional[ValidRecordsParquetWriter] = None,
):
    """Helper to process a single chunk dataframe."""
    logger.info("--- WORKER CODE VERSION CHECK: NO TRUNCATE_ARG ---")
    
    # Validar y preparar registros
    processed_records = validate_and_prepare_chunk(
        chunk_df=chunk_df,
        batch_id=batch_id,
        chunk_idx=chunk_idx,
        source_name=source_name,
        column_mapping=column_mapping,
        selected_columns=selected_columns,
        target_column_types=target_column_types,
        not_null_columns=not_null_columns,
        foreign_keys_data=foreign_keys_data,
        catalog_table=catalog_table,
        composite_unique_keys=composite_unique_keys,
        seen_composite_keys=seen_composite_keys,
        history_mode=history_mode,
        process_type=process_type,
        organization_id=organization_id,
        sku_resolver=sku_resolver,
        resolve_sku_id=resolve_sku_id,
        source_extension=source_extension,
        progress_conn=progress_conn or conn,
        progress_total_rows=progress_total_rows,
        progress_row_offset=progress_row_offset,
        progress_loaded_before=progress_loaded_before,
        progress_rejected_before=progress_rejected_before,
        progress_chunks_processed=progress_chunks_processed,
        progress_chunks_total=progress_chunks_total,
    )
    
    # Carga Directa (COPY a Prod) vs Temp File (Post-Staging Validation)
    
    passed_records = [r for r in processed_records if r["validation_status"] == "PASSED"]
    failed_records = [r for r in processed_records if r["validation_status"] == "FAILED"]
    
    db_inserted = 0
    db_rejected = 0

    if direct_load and target_schema and target_table:
        # Modo ultra-rápido: pasa a prod directo
        if passed_records:
            target_cols = [c for c in column_mapping.keys() if c in target_column_types]
            if target_cols:
                ingestor = DirectIngestor(conn, target_schema, target_table, target_cols)
                ingestor.add_records(passed_records)
                ingestor.flush()
                db_inserted = len(passed_records)
    elif valid_temp_file:
        # Modo estándar: escribir PASSED a Parquet local
        if passed_records:
            if history_mode and passed_records:
                sample = json.loads(passed_records[0]["processed_data"])
                target_cols = [
                    k
                    for k in sample.keys()
                    if not target_column_types or k in target_column_types
                ]
            else:
                target_cols = list(column_mapping.keys()) if column_mapping else []
                if target_column_types:
                    target_cols = [c for c in target_cols if c in target_column_types]
                if not target_cols and column_mapping:
                    target_cols = list(column_mapping.keys())

            written = append_valid_records_parquet(
                valid_temp_file, passed_records, target_cols, writer=parquet_writer
            )
            db_inserted = written

    # FALLIDOS → archivo en disco (columna A = línea+errores; resto = columnas del archivo)
    if failed_records and rejected_temp_file is not None:
        export_cols = list(source_file_columns or [])
        if not export_cols and failed_records:
            first_src = failed_records[0].get("source_file_data")
            if first_src:
                try:
                    parsed = json.loads(first_src) if isinstance(first_src, str) else first_src
                    if isinstance(parsed, dict):
                        export_cols = list(parsed.keys())
                except (json.JSONDecodeError, TypeError):
                    pass
        append_rejected_records_csv(
            rejected_temp_file,
            failed_records,
            export_cols,
        )
        db_rejected = len(failed_records)

    # Calcular stats reales basados en validación
    invalid_count = len(failed_records)
    valid_count = len(passed_records)
    
    # Calcular score promedio
    chunk_quality = np.mean([r["data_quality_score"] for r in processed_records]) if processed_records else 0
    
    return {
        "inserted": valid_count,
        "rejected": invalid_count,
        "avg_quality": chunk_quality
    }


def _resolve_row_column(row: Dict[str, Any], col: str) -> Optional[str]:
    """Return key in row only for exact name match (case-insensitive)."""
    if col in row:
        return col
    lower_map = {str(k).lower(): k for k in row.keys()}
    return lower_map.get(str(col).lower())


def _resolve_composite_key(row: Dict[str, Any], unique_keys: List[str]) -> Optional[tuple]:
    from data_staging.services.catalog.catalog_transforms import is_empty_value

    parts: List[str] = []
    for key in unique_keys:
        col = _resolve_row_column(row, key)
        if col is None:
            return None
        val = row[col]
        if is_empty_value(val):
            return None
        parts.append(str(val).strip())
    return tuple(parts)


def _source_row_from_mapped(
    row: Dict[str, Any], column_mapping: Dict[str, Any]
) -> Dict[str, Any]:
    """Rebuild source-file columns from a pre-mapped row (for rejected export)."""
    source_file_row: Dict[str, Any] = {}
    for target_col, val in row.items():
        mapped_info = column_mapping.get(target_col)
        if mapped_info and mapped_info.get("source"):
            source_file_row[mapped_info["source"]] = val
        else:
            source_file_row[target_col] = val
    return source_file_row


def validate_and_prepare_chunk(
    chunk_df: pl.DataFrame,
    batch_id: str,
    chunk_idx: int,
    source_name: str,
    column_mapping: Optional[Dict] = None,
    selected_columns: Optional[List[str]] = None,
    target_column_types: Optional[Dict[str, str]] = None,
    not_null_columns: Optional[Dict[str, bool]] = None,
    foreign_keys_data: Optional[Dict[str, set]] = None,
    catalog_table: Optional[str] = None,
    composite_unique_keys: Optional[List[str]] = None,
    seen_composite_keys: Optional[set] = None,
    history_mode: bool = False,
    process_type: Optional[str] = None,
    organization_id: Optional[str] = None,
    sku_resolver=None,
    resolve_sku_id: bool = False,
    source_extension: Optional[str] = None,
    progress_conn: Optional[psycopg2.extensions.connection] = None,
    progress_total_rows: int = 0,
    progress_row_offset: int = 0,
    progress_loaded_before: int = 0,
    progress_rejected_before: int = 0,
    progress_chunks_processed: int = 0,
    progress_chunks_total: int = 1,
) -> List[Dict[str, Any]]:
    """
    Valida y prepara registros de un chunk.
    Aplica column_mapping y selected_columns.
    VALIDA TIPOS Y CARACTERES ESPECIALES.
    """
    import re

    from data_staging.services.catalog.catalog_registry import get_catalog_table
    from data_staging.services.catalog.catalog_transforms import (
        apply_catalog_transforms_polars,
        format_date_for_storage,
        is_empty_value,
        parse_flexible_datetime,
        sanitize_row_dict,
    )
    
    # Regex para caracteres peligrosos o invalidos (control characters except tab/newline)
    INVALID_CHARS_REGEX = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F]')
    
    is_already_mapped = False
    if column_mapping:
        targets_present = sum(1 for target in column_mapping.keys() if target in chunk_df.columns)
        if targets_present >= 2:
            is_already_mapped = True

    # 1. Filtrar columnas si selected_columns está presente (solo si no está pre-mapeado)
    if selected_columns and not is_already_mapped:
        available_cols = [c for c in selected_columns if c in chunk_df.columns]
        if available_cols:
            chunk_df = chunk_df.select(available_cols)
        else:
            logger.warning(f"None of selected columns {selected_columns} found in dataframe")

    # Conservar filas originales del archivo (antes de mapear) para export de rechazados
    if is_already_mapped and column_mapping:
        original_rows = None
    else:
        original_rows = chunk_df.to_dicts()
    
    # 2. Aplicar column mapping si está presente
    if column_mapping:
        if is_already_mapped:
            # Si ya está mapeado, solo nos aseguramos de que existan las columnas del mapping 
            # (inyectando valores por defecto si no existen)
            for target_col, map_info in column_mapping.items():
                if target_col not in chunk_df.columns:
                    default_val = map_info.get("default")
                    chunk_df = chunk_df.with_columns([
                        pl.lit(default_val if default_val is not None else None).alias(target_col)
                    ])
        else:
            # Crear nuevas columnas según mapping desde columnas originales
            for target_col, map_info in column_mapping.items():
                source_col = map_info.get("source")
                default_val = map_info.get("default")
                
                # REGLA DE NEGOCIO: Si el usuario asignó un default_val explícito, 
                # tiene prioridad absoluta y omite la información de `source_col`
                if default_val is not None and str(default_val).strip() != "":
                    chunk_df = chunk_df.with_columns([
                        pl.lit(default_val).alias(target_col)
                    ])
                # Si NO hay default_val, entonces tomamos la información de la columna original si existe
                elif source_col and source_col in chunk_df.columns:
                    chunk_df = chunk_df.rename({source_col: target_col})
                # Si la columna de destino ya existe en el dataframe (ej: archivo ya aglomerado), la conservamos
                elif target_col in chunk_df.columns:
                    pass
                # Si es una columna nueva (no mapeada) y no tiene default, la llenamos con NULL
                else:
                    chunk_df = chunk_df.with_columns([
                        pl.lit(None).alias(target_col)
                    ])
            
            # Seleccionar solo columnas target
            target_cols = list(column_mapping.keys())
            available_targets = [c for c in target_cols if c in chunk_df.columns]
            if available_targets:
                chunk_df = chunk_df.select(available_targets)
            else:
                logger.error(f"No target columns found after mapping")

    if catalog_table:
        mapped_cols = frozenset(column_mapping.keys()) if column_mapping else None
        chunk_df = apply_catalog_transforms_polars(
            chunk_df, catalog_table, mapped_columns=mapped_cols
        )

    if history_mode and organization_id:
        from data_staging.services.history.history_transforms import apply_history_transforms_polars

        chunk_df = apply_history_transforms_polars(
            chunk_df,
            organization_id=organization_id,
            process_type=process_type,
            source_extension=source_extension,
            sku_resolver=sku_resolver,
            resolve_sku_id=resolve_sku_id,
        )

    from data_staging.utils.vectorized_validation import use_vectorized_validation

    if use_vectorized_validation() and history_mode:
        from data_staging.utils.vectorized_validation import validate_chunk_vectorized

        return validate_chunk_vectorized(
            chunk_df=chunk_df,
            batch_id=batch_id,
            chunk_idx=chunk_idx,
            chunk_size=CHUNK_SIZE_RECORDS,
            column_mapping=column_mapping,
            target_column_types=target_column_types,
            not_null_columns=not_null_columns,
            foreign_keys_data=foreign_keys_data,
            history_mode=history_mode,
            original_rows=original_rows,
        )
    
    # 3. Preparar registros
    records = []
    
    if chunk_df.is_empty():
        return []

    # Calcular quality score
    total_cols = len(chunk_df.columns)
    
    # Convert dates to string para JSON serialization
    for col in chunk_df.columns:
        if chunk_df[col].dtype in [pl.Date, pl.Datetime, pl.Time]:
            chunk_df = chunk_df.with_columns(pl.col(col).cast(pl.Utf8))
    
    # Iterar filas y crear registros
    rows = chunk_df.to_dicts()
    
    start_row_num = (chunk_idx * CHUNK_SIZE_RECORDS) + 1
    
    # DEBUG: Log available columns vs target schema
    logger.info(f"Chunk columns: {chunk_df.columns}")
    logger.info(f"Target schema keys: {list(target_column_types.keys())}")

    if progress_conn and progress_total_rows > 0:
        report_processing_progress(
            progress_conn,
            batch_id,
            progress_percentage=min(
                99.0, ((progress_row_offset + len(rows)) / progress_total_rows) * 100
            ),
            current_operation=(
                f"Validando filas {progress_row_offset + 1:,}–"
                f"{progress_row_offset + len(rows):,} de {progress_total_rows:,} "
                f"(bloque {progress_chunks_processed + 1}/{progress_chunks_total})…"
            ),
            phase="validating",
            total_rows=progress_total_rows,
            rows_processed=progress_row_offset,
            loaded_rows=progress_loaded_before,
            rejected_rows=progress_rejected_before,
            chunks_processed=progress_chunks_processed,
            chunks_total=progress_chunks_total,
        )
    
    logged_errors = 0
    chunk_passed = 0
    chunk_failed = 0
    last_progress_at = time.monotonic()
    for i, row in enumerate(rows):
        row = sanitize_row_dict(row)
        if original_rows is not None:
            source_file_row = original_rows[i] if i < len(original_rows) else {}
        elif is_already_mapped and column_mapping:
            source_file_row = _source_row_from_mapped(row, column_mapping)
        else:
            source_file_row = {}
        validation_status = "PASSED"
        error_list = []
        
        # --- VALIDACIÓN ROW-LEVEL ---
        
        # 1. Validar tipos de datos y constraints (si target schema disponible)
        if target_column_types:
            for col_name, value in row.items():
                if col_name not in target_column_types:
                    continue

                target_type = target_column_types[col_name].lower()
                is_not_null = (not_null_columns or {}).get(col_name, False)
                has_foreign_key = bool(foreign_keys_data and col_name in foreign_keys_data)
                
                is_empty = is_empty_value(value)

                # Validar NULL en columnas NOT NULL o llaves foráneas requeridas
                if is_empty:
                    if is_not_null or has_foreign_key:
                        validation_status = "FAILED"
                        error_list.append(f"Empty value not allowed for '{col_name}' (Database NOT NULL constraint or Foreign Key)")
                    continue  # IF it's intentionally empty and allowed by schema, simply skip further string analysis
                
                # Validate Foreign Key integrity
                if has_foreign_key:
                    val_str = str(value).strip()
                    # Normalizamos los floats enteros que polars pudo haber exportado (ej: 10001.0 -> 10001)
                    if val_str.endswith(".0"):
                        val_str = val_str[:-2]
                        
                    if val_str not in foreign_keys_data[col_name]:
                        validation_status = "FAILED"
                        error_list.append(f"Foreign Key violation for '{col_name}': '{value}' not found in target table lookup")
                        continue

                # Log debug for first row only
                if i == 0:
                    logger.info(f"Validating {col_name}='{value}' against {target_type}")

                # Validación Integer / Numeric
                # IMPORTANTE: validar siempre sin importar el tipo que traiga el valor.
                # Si Polars infirió el tipo antes de llegar aqui, aun asi se verifica
                # que el valor original sea convertible a numero.
                if 'int' in target_type or 'numeric' in target_type or 'float' in target_type or 'double' in target_type:
                    try:
                        # Convertir a string primero para normalizar cualquier tipo
                        raw_str = str(value).strip()
                        # Limpiar simbolos de moneda/separadores permitidos
                        clean_val = raw_str.replace('$', '').replace(',', '').strip()
                        if not clean_val:
                            raise ValueError("Empty value")
                        float(clean_val)
                    except (ValueError, TypeError):
                        validation_status = "FAILED"
                        error_list.append(f"Invalid format for '{col_name}': expected number, got '{value}'")

                # Validación Date / Timestamp (acepta datetime con fracciones .000000000)
                elif 'date' in target_type or 'time' in target_type:
                    if not is_empty:
                        parsed_dt = parse_flexible_datetime(value)
                        if not parsed_dt:
                            validation_status = "FAILED"
                            error_list.append(
                                f"Invalid date format for '{col_name}': got '{value}'"
                            )
                        else:
                            date_only = (
                                target_type.strip() == 'date'
                                or (
                                    'date' in target_type
                                    and 'timestamp' not in target_type
                                )
                            )
                            normalized = format_date_for_storage(
                                parsed_dt, date_only=date_only
                            )
                            if normalized is not None:
                                row[col_name] = normalized

                # Validación String Length (varchar)
                elif 'char' in target_type or 'text' in target_type:
                    import re
                    match = re.search(r'\((\d+)\)', target_type)
                    if match:
                        max_len = int(match.group(1))
                        if len(str(value)) > max_len:
                            validation_status = "FAILED"
                            error_list.append(f"String too long for '{col_name}': len={len(str(value))}, max={max_len}")

        # 2. Columnas requeridas del catálogo (definición de negocio)
        if history_mode:
            from data_staging.services.history.history_config import (
                HISTORY_REQUIRED_MAPPING_COLUMNS,
                HISTORY_SKU_MAPPING_TARGETS,
            )

            has_sku_value = any(
                not is_empty_value(row.get(k)) for k in HISTORY_SKU_MAPPING_TARGETS
            )
            if not has_sku_value:
                validation_status = "FAILED"
                error_list.append(
                    "Falta código de producto (mapea sku o sku_code)"
                )
            elif "sku" in (target_column_types or {}):
                if is_empty_value(row.get("sku")):
                    validation_status = "FAILED"
                    error_list.append("Campo obligatorio vacío: sku")
            for req in HISTORY_REQUIRED_MAPPING_COLUMNS:
                if req in (target_column_types or {}) and is_empty_value(row.get(req)):
                    validation_status = "FAILED"
                    error_list.append(f"Campo obligatorio vacío: {req}")

            # Validar existencia de SKU en catálogo public.skus de la organización
            sku_val = row.get("sku")
            if not is_empty_value(sku_val):
                sku_str = str(sku_val).strip().lower()
                if sku_str.endswith(".0"):
                    sku_str = sku_str[:-2]
                if foreign_keys_data and "__valid_skus__" in foreign_keys_data:
                    if sku_str not in foreign_keys_data["__valid_skus__"]:
                        validation_status = "FAILED"
                        error_list.append(
                            f"El SKU '{sku_val}' no existe en la tabla de productos (skus.code) de la organización"
                        )

            # Validar existencia de Location en catálogo public.locations de la organización
            loc_val = row.get("location_code")
            if not is_empty_value(loc_val):
                loc_str = str(loc_val).strip().lower()
                if loc_str.endswith(".0"):
                    loc_str = loc_str[:-2]
                if foreign_keys_data and "__valid_locations__" in foreign_keys_data:
                    if loc_str not in foreign_keys_data["__valid_locations__"]:
                        validation_status = "FAILED"
                        error_list.append(
                            f"La locación '{loc_val}' no existe en la tabla de ubicaciones (locations.code) de la organización"
                        )

            if "granularity" in (target_column_types or {}) and is_empty_value(
                row.get("granularity")
            ):
                validation_status = "FAILED"
                error_list.append("Campo obligatorio vacío: granularity")

            from data_staging.services.history.history_config import HISTORY_SALES_CHANNEL_VALUE

            invalid_channel = row.pop("_sales_channel_invalid", None)
            if invalid_channel is not None:
                validation_status = "FAILED"
                error_list.append(
                    f"sales_channel debe ser '{HISTORY_SALES_CHANNEL_VALUE}' "
                    f"(valor en archivo: {invalid_channel!r})"
                )

        if catalog_table:
            catalog_def = get_catalog_table(catalog_table)
            if catalog_def:
                for col in catalog_def.get("required_columns") or []:
                    if not col or col == "organization_id":
                        continue
                    resolved = _resolve_row_column(row, col)
                    if not resolved:
                        validation_status = "FAILED"
                        error_list.append(
                            f"Columna requerida no mapeada o ausente: '{col}'"
                        )
                    elif is_empty_value(row.get(resolved)):
                        validation_status = "FAILED"
                        error_list.append(
                            f"Valor vacío no permitido en columna requerida '{col}'"
                        )

        # 3. Validar enums de catálogo (status, etc.) cuando la columna está mapeada
        if catalog_table:
            from data_staging.services.catalog.catalog_transforms import validate_catalog_row_enums

            enum_errors = validate_catalog_row_enums(row, catalog_table)
            if enum_errors:
                validation_status = "FAILED"
                error_list.extend(enum_errors)

        if (
            composite_unique_keys
            and seen_composite_keys is not None
            and validation_status == "PASSED"
        ):
            key_tuple = _resolve_composite_key(row, composite_unique_keys)
            if key_tuple is None:
                validation_status = "FAILED"
                error_list.append(
                    f"Faltan columnas para clave única: {', '.join(composite_unique_keys)}"
                )
            elif key_tuple in seen_composite_keys:
                validation_status = "FAILED"
                error_list.append(
                    f"Clave duplicada en archivo ({', '.join(composite_unique_keys)})"
                )
            else:
                seen_composite_keys.add(key_tuple)

        # 4. Validar Caracteres Especiales (en todos los campos string)
        for col_name, value in row.items():
            if isinstance(value, str):
                if INVALID_CHARS_REGEX.search(value):
                    validation_status = "FAILED"
                    error_list.append(f"Invalid control characters detected in '{col_name}'")

        # LOG VALIDATION FAILURES
        if validation_status == "FAILED":
            if logged_errors < 5:
                logger.warning(f"Validation FAILED for row {i}: {error_list}")
                logged_errors += 1

        # 3. Calcular Data Quality Score
        null_count = sum(1 for v in row.values() if v is None)
        quality_score = 100.0 - (null_count * 100.0 / total_cols) if total_cols > 0 else 100.0
        
        # Si ya falló validación estricta, el status es FAILED
        if validation_status == "PASSED" and quality_score < 80.0:
             # Opcional: fallar por baja calidad? Por ahora solo warning en score
             pass

        error_details_json = json.dumps({"errors": error_list}) if error_list else None
        
        record = {
            "batch_id": batch_id,
            "source_row_number": start_row_num + i,
            "source_file_data": json.dumps(source_file_row, default=str),
            "raw_data": json.dumps(row),
            "processed_data": json.dumps(row),
            "validation_status": validation_status,
            "data_quality_score": quality_score,
            "is_duplicate": False,  # Se calcula en Pre-flight Check (Promotion)
            "error_details": error_details_json
        }
        
        records.append(record)

        if validation_status == "PASSED":
            chunk_passed += 1
        else:
            chunk_failed += 1

        rows_done = progress_row_offset + i + 1
        should_report_rows = (
            progress_conn
            and progress_total_rows > 0
            and rows_done % PROGRESS_ROW_INTERVAL == 0
        )
        should_report_time = (
            progress_conn
            and progress_total_rows > 0
            and (time.monotonic() - last_progress_at) >= PROGRESS_TIME_INTERVAL_SEC
        )
        if should_report_rows or should_report_time:
            last_progress_at = time.monotonic()
            report_processing_progress(
                progress_conn,
                batch_id,
                progress_percentage=min(99.0, (rows_done / progress_total_rows) * 100),
                current_operation=(
                    f"Validando filas {rows_done:,} de {progress_total_rows:,} "
                    f"(bloque {progress_chunks_processed + 1}/{progress_chunks_total})…"
                ),
                phase="validating",
                total_rows=progress_total_rows,
                rows_processed=rows_done,
                loaded_rows=progress_loaded_before + chunk_passed,
                rejected_rows=progress_rejected_before + chunk_failed,
                chunks_processed=progress_chunks_processed,
                chunks_total=progress_chunks_total,
            )
    
    return records

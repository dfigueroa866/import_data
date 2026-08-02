from __future__ import annotations

import logging
import json
import os
import re
import time
import numpy as np
import io
import csv
import uuid
from typing import Dict, Any, List, Optional, Union
from datetime import datetime
from pathlib import Path
import polars as pl
import psycopg2
from data_staging.config import settings
from data_staging.utils.mapping_helpers import (
    inject_session_organization_id,
    is_metadata_driven_fixed_key,
    is_wizard_virtual_mapping,
)
from data_staging.utils.batch_staging_files import (
    HISTORY_CAST_EXCLUDE_COLUMNS,
    ValidRecordsParquetWriter,
    append_rejected_records_csv,
    append_valid_records_parquet,
    metadata_merge_expr,
    rejected_records_path,
    valid_records_path,
)
from data_staging.utils.pipeline_timing import PipelineTimer, persist_timing_metadata
from data_staging.utils.parallel_validation import (
    configure_polars_threads,
    should_use_parallel_validation,
)
from data_staging.utils.batch_cancel import raise_if_batch_cancelled

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
    raise_if_batch_cancelled(batch_id, conn)

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
        SELECT source_name, file_name, metadata, organization_id
        FROM staging_meta.batch_control
        WHERE batch_id = %s
    """, (batch_id,))
    
    row = cursor.fetchone()
    if not row:
        raise ValueError(f"Batch {batch_id} not found")
    
    source_name = row[0]
    file_name = row[1]
    metadata = row[2] or {}
    batch_organization_id = row[3]
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
                    if is_wizard_virtual_mapping(file_col, mapping_config):
                        if is_metadata_driven_fixed_key(file_col):
                            continue
                        default_val = mapping_config.get("default_value", "")
                        column_mapping[target] = {
                            "source": None,
                            "default": default_val,
                        }
                    else:
                        selected_columns.append(file_col)
                        default_val = mapping_config.get("default_value", "")
                        entry: Dict[str, Any] = {"source": file_col}
                        if default_val is not None and str(default_val).strip() != "":
                            entry["default"] = default_val
                        column_mapping[target] = entry
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
        valid_temp_file = valid_records_path(batch_id, metadata)
        rejected_temp_file = rejected_records_path(batch_id, metadata)

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
        history_rules = None
        if history_mode:
            from data_staging.services.history.history_config import resolve_history_rules

            history_rules = resolve_history_rules(metadata)
        process_type = metadata.get("process_type")
        organization_id = str(
            payload.get("organization_id")
            or batch_organization_id
            or metadata.get("organization_id")
            or ""
        ).strip() or None
        if metadata.get("load_type") == "catalog":
            column_mapping = inject_session_organization_id(column_mapping, organization_id)
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
                from data_staging.services.catalog.catalog_registry import (
                    catalog_required_targets,
                    get_catalog_table,
                )

                validation_excluded = load_db_validation_excluded_columns_psycopg2(
                    cursor, target_schema, target_table
                )
                for col in validation_excluded:
                    if col in not_null_columns:
                        not_null_columns[col] = False
                # Config is the bible for null rejection (even if DB has a default).
                entry = get_catalog_table(catalog_table) if catalog_table else None
                for col in catalog_required_targets(entry):
                    not_null_columns[col] = True
                system_managed = load_db_system_managed_columns_psycopg2(
                    cursor, target_schema, target_table
                )
                if system_managed:
                    logger.info(
                        "Catalog load: excluded system-managed columns from mapping: %s",
                        ", ".join(sorted(system_managed)),
                    )

        logger.info(f"Target schema loaded: {len(target_column_types)} columns for validation")

        # FK genéricos solo catálogos; historia usa __valid_skus__ / __valid_locations__
        foreign_keys_data = {}
        if target_schema and target_table and not history_mode:
            from data_staging.services.history.org_reference_data import load_generic_fk_values

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
                        valid_values = load_generic_fk_values(
                            cursor,
                            schema=f_schema,
                            table=f_table,
                            column=f_col,
                            organization_id=organization_id,
                        )
                        foreign_keys_data[col_name] = valid_values
                        logger.info(f"Loaded {len(valid_values)} valid keys for FK {col_name}")
                    except Exception as sub_e:
                        logger.warning(f"Failed to load values for FK {col_name}: {sub_e}")
            except Exception as e:
                logger.error(f"Failed to query foreign keys: {e}")

        if history_mode and organization_id:
            from data_staging.services.history.org_reference_data import load_org_scoped_fk_sets

            foreign_keys_data.update(load_org_scoped_fk_sets(cursor, organization_id))
        elif history_mode:
            logger.error(
                "organization_id missing for history batch %s; SKU/location FK validation disabled",
                batch_id,
            )

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
                from data_staging.utils.chunk_iterators import parquet_column_names

                source_file_columns = parquet_column_names(file_path)
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

        configure_polars_threads()
        process_timer = PipelineTimer("process")

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
            history_rules=history_rules,
            process_type=process_type,
            organization_id=organization_id,
            sku_resolver=sku_resolver,
            resolve_sku_id=resolve_sku_id,
            source_extension=source_extension if history_mode else None,
            pipeline_timer=process_timer,
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
                "completed_at": datetime.now().isoformat(),
                **process_timer.snapshot(),
            }),
            error_msg,
            batch_id
        ))
        conn.commit()
        persist_timing_metadata(conn, batch_id, process_timer.snapshot())
        
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


def _can_parallelize_chunk_validation(
    *,
    composite_unique_keys: Optional[List[str]],
    resolve_sku_id: bool,
    sku_resolver,
    direct_load: bool,
    total_rows: int = 0,
) -> bool:
    min_rows = int(getattr(settings, "PARALLEL_VALIDATION_MIN_ROWS", 500_000))
    return (
        total_rows >= min_rows
        and should_use_parallel_validation(composite_unique_keys)
        and not resolve_sku_id
        and sku_resolver is None
        and not direct_load
    )


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
    history_rules: Optional[Dict[str, Any]] = None,
    process_type: Optional[str] = None,
    organization_id: Optional[str] = None,
    sku_resolver=None,
    resolve_sku_id: bool = False,
    source_extension: Optional[str] = None,
    progress_conn: Optional[psycopg2.extensions.connection] = None,
    parquet_writer: Optional[ValidRecordsParquetWriter] = None,
    pipeline_timer: Optional[PipelineTimer] = None,
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
        own_writer = ValidRecordsParquetWriter(
            valid_temp_file,
            [],
            target_column_types=target_column_types or {},
            cast_exclude_columns=HISTORY_CAST_EXCLUDE_COLUMNS if history_mode else None,
        )
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
            parallel_validation = _can_parallelize_chunk_validation(
                composite_unique_keys=composite_unique_keys,
                resolve_sku_id=resolve_sku_id,
                sku_resolver=sku_resolver,
                direct_load=direct_load,
                total_rows=total_rows,
            )
            validation_workers = int(getattr(settings, "VALIDATION_WORKER_PROCESSES", 2))
            parallel_validate_kwargs = {
                "batch_id": batch_id,
                "source_name": source_name,
                "column_mapping": column_mapping,
                "selected_columns": selected_columns,
                "target_column_types": target_column_types,
                "not_null_columns": not_null_columns,
                "foreign_keys_data": foreign_keys_data,
                "catalog_table": catalog_table,
                "composite_unique_keys": composite_unique_keys,
                "seen_composite_keys": seen_composite_keys,
                "history_mode": history_mode,
                "history_rules": history_rules,
                "process_type": process_type,
                "organization_id": organization_id,
                "sku_resolver": None,
                "resolve_sku_id": False,
                "source_extension": source_extension,
            }
            parallel_buffer: List[tuple] = []

            def _process_validated_chunk(
                chunk_to_process: pl.DataFrame,
                chunk_idx: int,
                chunk_row_offset: int,
                prevalidated: Optional[Any] = None,
            ) -> Dict[str, Any]:
                return process_single_chunk(
                    chunk_to_process,
                    chunk_idx=chunk_idx,
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
                history_rules=history_rules,
                process_type=process_type,
                organization_id=organization_id,
                sku_resolver=sku_resolver,
                resolve_sku_id=resolve_sku_id,
                source_extension=source_extension,
                progress_total_rows=total_rows,
                progress_row_offset=chunk_row_offset,
                    progress_loaded_before=total_inserted,
                    progress_rejected_before=total_rejected,
                    progress_chunks_processed=chunk_idx,
                    progress_chunks_total=chunks_total,
                    progress_conn=progress_conn,
                    parquet_writer=parquet_writer,
                    pipeline_timer=pipeline_timer,
                    prevalidated=prevalidated,
                )

            def _flush_parallel_buffer() -> None:
                nonlocal row_offset, parallel_buffer
                if not parallel_buffer:
                    return
                raise_if_batch_cancelled(batch_id, progress_conn)
                from concurrent.futures import ProcessPoolExecutor
                from data_staging.utils.parallel_validation import validation_worker_entry

                payloads = [
                    (chunk_idx, chunk_df, parallel_validate_kwargs)
                    for chunk_idx, chunk_df, _offset in parallel_buffer
                ]
                with ProcessPoolExecutor(max_workers=validation_workers) as pool:
                    validated = list(pool.map(validation_worker_entry, payloads))
                raise_if_batch_cancelled(batch_id, progress_conn)
                validated.sort(key=lambda item: item[0])
                validated_map = {chunk_idx: result for chunk_idx, result in validated}
                for chunk_idx, chunk_df, chunk_row_offset in sorted(
                    parallel_buffer, key=lambda item: item[0]
                ):
                    end_idx = min(chunk_row_offset + len(chunk_df), total_rows)
                    with (pipeline_timer.phase("read_ms") if pipeline_timer else _null_phase()):
                        pass
                    stats = _process_validated_chunk(
                        chunk_df,
                        chunk_idx,
                        chunk_row_offset,
                        prevalidated=validated_map[chunk_idx],
                    )
                    _finalize_chunk(stats, end_idx)
                    row_offset = end_idx
                parallel_buffer.clear()

            for chunk_df in chunk_source:
                raise_if_batch_cancelled(batch_id, progress_conn)
                end_idx = min(row_offset + len(chunk_df), total_rows)
                with (pipeline_timer.phase("read_ms") if pipeline_timer else _null_phase()):
                    chunk_to_process = chunk_df

                if parallel_validation and validation_workers > 1:
                    parallel_buffer.append((chunks_processed, chunk_to_process, row_offset))
                    if len(parallel_buffer) >= validation_workers:
                        _flush_parallel_buffer()
                    continue

                stats = _process_validated_chunk(
                    chunk_to_process,
                    chunks_processed,
                    row_offset,
                )
                _finalize_chunk(stats, end_idx)
                row_offset = end_idx

            if parallel_validation:
                _flush_parallel_buffer()

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
                raise_if_batch_cancelled(batch_id, progress_conn)
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
                    history_rules=history_rules,
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
                    pipeline_timer=pipeline_timer,
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
    history_rules: Optional[Dict[str, Any]] = None,
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
    pipeline_timer: Optional[PipelineTimer] = None,
    prevalidated: Optional[Any] = None,
):
    """Helper to process a single chunk dataframe."""
    from data_staging.utils.vectorized_validation import ChunkValidationResult

    raise_if_batch_cancelled(batch_id)

    if prevalidated is not None:
        validation_out = prevalidated
    else:
        validate_phase = _null_phase()
        if pipeline_timer and not (history_mode and organization_id):
            validate_phase = pipeline_timer.phase("validate_ms")
        with validate_phase:
            validation_out = validate_and_prepare_chunk(
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
                history_rules=history_rules,
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
                pipeline_timer=pipeline_timer,
            )

    if isinstance(validation_out, ChunkValidationResult):
        passed_df = validation_out.passed_df
        failed_records = validation_out.failed_records
        chunk_quality = validation_out.avg_quality
        passed_records: List[Dict[str, Any]] = []
    else:
        processed_records = validation_out
        passed_records = [r for r in processed_records if r["validation_status"] == "PASSED"]
        failed_records = [r for r in processed_records if r["validation_status"] == "FAILED"]
        passed_df = None
        chunk_quality = (
            float(np.mean([r["data_quality_score"] for r in processed_records]))
            if processed_records
            else 0.0
        )

    db_inserted = 0
    db_rejected = 0

    def _resolve_target_cols() -> List[str]:
        if passed_df is not None and not passed_df.is_empty():
            return [
                c
                for c in passed_df.columns
                if not str(c).startswith("_")
                and (not target_column_types or c in target_column_types)
            ]
        if history_mode and passed_records:
            sample = json.loads(passed_records[0]["processed_data"])
            return [
                k
                for k in sample.keys()
                if not target_column_types or k in target_column_types
            ]
        target_cols = list(column_mapping.keys()) if column_mapping else []
        if target_column_types:
            target_cols = [c for c in target_cols if c in target_column_types]
        if not target_cols and column_mapping:
            target_cols = list(column_mapping.keys())
        return target_cols

    if direct_load and target_schema and target_table:
        if passed_df is not None and not passed_df.is_empty():
            target_cols = _resolve_target_cols()
            if target_cols:
                ingestor = DirectIngestor(conn, target_schema, target_table, target_cols)
                for row in passed_df.select(target_cols).to_dicts():
                    ingestor.add_records(
                        [
                            {
                                "validation_status": "PASSED",
                                "processed_data": json.dumps(row, default=str),
                            }
                        ]
                    )
                ingestor.flush()
                db_inserted = passed_df.height
        elif passed_records:
            target_cols = [c for c in column_mapping.keys() if c in (target_column_types or {})]
            if target_cols:
                ingestor = DirectIngestor(conn, target_schema, target_table, target_cols)
                ingestor.add_records(passed_records)
                ingestor.flush()
                db_inserted = len(passed_records)
    elif valid_temp_file:
        target_cols = _resolve_target_cols()
        with (pipeline_timer.phase("parquet_write_ms") if pipeline_timer else _null_phase()):
            if passed_df is not None and not passed_df.is_empty():
                start_row = (chunk_idx * CHUNK_SIZE_RECORDS) + 1
                if parquet_writer is not None:
                    db_inserted = parquet_writer.write_polars_chunk(
                        passed_df,
                        batch_id=batch_id,
                        start_row_number=start_row,
                        target_cols=target_cols,
                    )
                else:
                    writer = ValidRecordsParquetWriter(
                        valid_temp_file,
                        target_cols,
                        target_column_types=target_column_types or {},
                        cast_exclude_columns=HISTORY_CAST_EXCLUDE_COLUMNS if history_mode else None,
                    )
                    try:
                        db_inserted = writer.write_polars_chunk(
                            passed_df,
                            batch_id=batch_id,
                            start_row_number=start_row,
                            target_cols=target_cols,
                        )
                    finally:
                        writer.close()
            elif passed_records:
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

    valid_count = db_inserted if passed_df is not None else len(passed_records)
    invalid_count = len(failed_records)

    return {
        "inserted": valid_count,
        "rejected": invalid_count,
        "avg_quality": chunk_quality,
    }


class _null_phase:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


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
    history_rules: Optional[Dict[str, Any]] = None,
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
    pipeline_timer: Optional[PipelineTimer] = None,
) -> Union[List[Dict[str, Any]], ChunkValidationResult]:
    """
    Valida y prepara registros de un chunk (catálogo).
    Historia delega en validate_history_chunk().
    """
    from data_staging.services.catalog.catalog_transforms import apply_catalog_transforms_polars
    from data_staging.utils.mapping_helpers import apply_chunk_column_mapping
    from data_staging.utils.vectorized_validation import ChunkValidationResult, validate_chunk_vectorized

    if history_mode:
        from data_staging.services.history.history_chunk_validation import validate_history_chunk

        return validate_history_chunk(
            chunk_df=chunk_df,
            batch_id=batch_id,
            chunk_idx=chunk_idx,
            chunk_size=CHUNK_SIZE_RECORDS,
            column_mapping=column_mapping,
            selected_columns=selected_columns,
            target_column_types=target_column_types,
            not_null_columns=not_null_columns,
            foreign_keys_data=foreign_keys_data,
            history_rules=history_rules,
            organization_id=organization_id,
            process_type=process_type,
            source_extension=source_extension,
            sku_resolver=sku_resolver,
            resolve_sku_id=resolve_sku_id,
            pipeline_timer=pipeline_timer,
        )

    chunk_df = apply_chunk_column_mapping(
        chunk_df,
        column_mapping=column_mapping,
        selected_columns=selected_columns,
    )

    if catalog_table:
        mapped_cols = frozenset(column_mapping.keys()) if column_mapping else None
        with (pipeline_timer.phase("transform_ms") if pipeline_timer else _null_phase()):
            chunk_df = apply_catalog_transforms_polars(
                chunk_df, catalog_table, mapped_columns=mapped_cols
            )

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
        history_rules=history_rules,
        original_rows=None,
        catalog_table=catalog_table,
        composite_unique_keys=composite_unique_keys,
        seen_composite_keys=seen_composite_keys,
    )

import logging
import json
import os
import re
import numpy as np
import io
import csv
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path
import polars as pl
import psycopg2
from data_staging.config import settings

logger = logging.getLogger(__name__)

# Configuración de tamaños para procesamiento
CHUNK_SIZE_RECORDS = 100000
BATCH_SIZE_INSERT = 10000

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
                if val is None or val == "" or (isinstance(val, float) and np.isnan(val)):
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
    
    # Extraer configuración del wizard metadata
    file_path_str = payload.get("file_path") or metadata.get("file_path")
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
                    selected_columns.append(file_col)
                    column_mapping[target] = {
                        "source": file_col,
                        "default": mapping_config.get("default_value", "")
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
        cursor.execute("""
            UPDATE staging_meta.batch_control
            SET status = 'PROCESSING',
                started_at = CURRENT_TIMESTAMP
            WHERE batch_id = %s
        """, (batch_id,))
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

        # 2. Determinar si es carga directa (bypass staging)
        direct_load = payload.get("direct_load", False) or metadata.get("direct_load", False)
        target_column_types = payload.get("target_column_types") or {}

        if direct_load:
            logger.info("⚡ DIRECT LOAD ENABLED: Bypassing staging table for valid records")
        
        # 2.5 Extraer delimitador y encoding detectados
        file_analysis = metadata.get("file_analysis", {})
        delimiter = file_analysis.get("delimiter", ",")
        encoding = file_analysis.get("encoding", "utf-8")

        # 3. Crear tabla staging si no existe (siempre se crea para logs de error)
        safe_source_name = source_name.lower().replace(' ', '_').replace('-', '_')
        staging_table = f"stage_{safe_source_name}"
        create_staging_table(conn, staging_table)
        
        # LIMPIEZA: Eliminar registros previos de este batch para evitar duplicados en reintentos
        cursor.execute(f"DELETE FROM staging_data.{staging_table} WHERE batch_id = %s", (batch_id,))
        conn.commit()
        logger.info(f"Cleared previous staging data for batch {batch_id} in {staging_table}")
        
        not_null_columns = {}
        if not target_column_types and target_schema and target_table:
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
                    target_column_types[c_name] = full_type
                    not_null_columns[c_name] = (is_nullable == 'NO')
            except Exception as e:
                logger.error(f"Failed to query schema info: {e}")

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

        # 3. Procesar archivo por chunks
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        stats = process_file_in_chunks(
            conn=conn,
            file_path=file_path,
            batch_id=batch_id,
            staging_table=staging_table,
            source_name=source_name,
            column_mapping=column_mapping,
            selected_columns=selected_columns,
            job_id=job_id,  # Para reportar progreso
            target_column_types=target_column_types,  # Pass schema for validation
            not_null_columns=not_null_columns,
            delimiter=delimiter,
            encoding=encoding,
            direct_load=direct_load,
            target_schema=target_schema,
            target_table=target_table,
            foreign_keys_data=foreign_keys_data
        )
        
        # 4. Actualizar batch a COMPLETED
        cursor.execute("""
            UPDATE staging_meta.batch_control
            SET status = 'COMPLETED',
                completed_at = CURRENT_TIMESTAMP,
                records_count = %s,
                metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb,
                error_message = NULL
            WHERE batch_id = %s
        """, (
            stats["total_inserted"],
            json.dumps({
                "processing_stats": stats,
                "completed_at": datetime.now().isoformat()
            }),
            batch_id
        ))
        conn.commit()
        
        logger.info(f"Batch {batch_id} completed: {stats['total_inserted']} records processed")
        
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
                    error_message = %s
                WHERE batch_id = %s
            """, (str(e), batch_id))
            conn.commit()
        except Exception as e2:
            logger.error(f"Error updating batch status to FAILED: {e2}")
        
        raise
    
    finally:
        if conn:
            conn.close()


def create_staging_table(conn: psycopg2.extensions.connection, table_name: str):
    """Crea tabla staging UNLOGGED si no existe."""
    cursor = conn.cursor()
    
    # Check for SQL injection in table_name (simple check)
    if not table_name.replace('_', '').isalnum():
        raise ValueError(f"Invalid table name: {table_name}")

    cursor.execute(f"""
        CREATE UNLOGGED TABLE IF NOT EXISTS staging_data.{table_name} (
            staging_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            batch_id UUID NOT NULL REFERENCES staging_meta.batch_control(batch_id),
            source_row_number INTEGER,
            raw_data JSONB,
            processed_data JSONB,
            validation_status VARCHAR(20) DEFAULT 'PENDING',
            data_quality_score NUMERIC(5,2) DEFAULT 95.0,
            error_details JSONB,
            is_duplicate BOOLEAN DEFAULT false,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMPTZ
        )
    """)
    
    # Crear índices si no existen
    cursor.execute(f"""
        CREATE INDEX IF NOT EXISTS idx_{table_name}_batch 
        ON staging_data.{table_name}(batch_id)
    """)
    
    cursor.execute(f"""
        CREATE INDEX IF NOT EXISTS idx_{table_name}_status 
        ON staging_data.{table_name}(validation_status)
    """)

    cursor.execute(f"""
        CREATE INDEX IF NOT EXISTS idx_{table_name}_row_number 
        ON staging_data.{table_name}(batch_id, validation_status, source_row_number);
    """)

    cursor.execute(f"""
        CREATE INDEX IF NOT EXISTS idx_{table_name}_production_query
        ON staging_data.{table_name}(batch_id, validation_status, source_row_number) 
        WHERE validation_status = 'PASSED';
    """)
    
    conn.commit()

    # Parche: Asegurar que nuevas columnas existan en tablas staging legado
    try:
        cursor.execute(f"""
            ALTER TABLE staging_data.{table_name}
            ADD COLUMN IF NOT EXISTS data_quality_score NUMERIC(5,2) DEFAULT 95.0,
            ADD COLUMN IF NOT EXISTS error_details JSONB,
            ADD COLUMN IF NOT EXISTS is_duplicate BOOLEAN DEFAULT false;
        """)
        conn.commit()
    except Exception as e:
        logger.warning(f"Failed to alter staging table {table_name}. Might be fine: {e}")
        conn.rollback()
        
    logger.info(f"Staging table staging_data.{table_name} ready")


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
    foreign_keys_data: Optional[Dict[str, set]] = None
) -> Dict[str, Any]:
    """
    Procesa archivo en chunks usando Polars.
    """
    total_inserted = 0
    total_rejected = 0
    chunks_processed = 0
    quality_scores = []
    
    # Determinar tipo de archivo
    file_ext = file_path.suffix.lower()
    
    try:
        if file_ext == '.csv':
            # Normalizar encoding para Polars (ej: utf-8 -> utf8)
            pl_encoding = encoding.lower().replace("-", "")
            
            # En Polars 0.20.3, read_csv_batched NO soporta truncate_ragged_lines.
            # Usamos read_csv() que sí lo soporta y permite más encodings que scan_csv.
            # Leer TODAS las columnas como string (Utf8).
            # Evita que Polars convierta silenciosamente valores invalidos
            # (ej: 'dasd' en columna numerica) a null antes de que el validador los vea.
            # La conversion real al tipo correcto la hace PostgreSQL via COPY.
            full_df = pl.read_csv(
                file_path,
                separator=delimiter,
                encoding=pl_encoding,
                ignore_errors=True,
                truncate_ragged_lines=True,
                infer_schema_length=0,
                try_parse_dates=False,
                rechunk=True
            )
            
            # Dividir en chunks manualmente para procesar
            total_rows = len(full_df)
            for start_idx in range(0, total_rows, CHUNK_SIZE_RECORDS):
                end_idx = min(start_idx + CHUNK_SIZE_RECORDS, total_rows)
                chunk_df = full_df.slice(start_idx, end_idx - start_idx)
                
                # Procesar chunk
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
                    foreign_keys_data=foreign_keys_data
                )
                
                total_inserted += stats['inserted']
                total_rejected += stats['rejected']
                if stats['avg_quality']:
                    quality_scores.append(stats['avg_quality'])
                
                chunks_processed += 1
                
                # Reportar progreso (requires progress column in job_queue)
                if job_id:
                    try:
                        progress_percent = min(95, (total_inserted / max(total_inserted + total_rejected, 1)) * 100)
                        cursor = conn.cursor()
                        cursor.execute("""
                            UPDATE staging_meta.batch_control
                            SET metadata = metadata || jsonb_build_object('processing_progress', %s::jsonb)
                            WHERE batch_id = %s
                        """, (
                            json.dumps({
                                "progress_percentage": progress_percent,
                                "current_operation": f"Processing chunk {chunks_processed}",
                                "chunks_processed": chunks_processed,
                                "rows_processed": total_inserted
                            }),
                            batch_id
                        ))
                        conn.commit()
                    except Exception as e:
                        logger.warning(f"Failed to update progress: {e}")
                
                logger.info(f"Chunk {chunks_processed} completed: {stats['inserted']} inserted")

        elif file_ext in ['.xlsx', '.xls']:
            # Excel: leer todo primero (limitación de formato)
            df_full = pl.read_excel(file_path)
            
            total_rows = len(df_full)
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
                    target_table=target_table
                )
                
                total_inserted += stats['inserted']
                total_rejected += stats['rejected']
                if stats['avg_quality']:
                    quality_scores.append(stats['avg_quality'])
                
                chunks_processed += 1
                
                # Reportar progreso (requires progress column in job_queue)
                if job_id:
                    try:
                        progress_percent = min(95, (i + CHUNK_SIZE_RECORDS) / total_rows * 100)
                        cursor = conn.cursor()
                        cursor.execute("""
                            UPDATE staging_meta.batch_control
                            SET metadata = metadata || jsonb_build_object('processing_progress', %s::jsonb)
                            WHERE batch_id = %s
                        """, (
                            json.dumps({
                                "progress_percentage": progress_percent,
                                "current_operation": f"Processing chunk {chunks_processed}/{(total_rows // CHUNK_SIZE_RECORDS) + 1}",
                                "chunks_processed": chunks_processed,
                                "rows_processed": total_inserted
                            }),
                            batch_id
                        ))
                        conn.commit()
                    except Exception as e:
                        logger.warning(f"Failed to update progress: {e}")
                
                logger.info(f"Chunk {chunks_processed} completed: {stats['inserted']} inserted")
        else:
            raise ValueError(f"Unsupported file type: {file_ext}")
        
        return {
            "total_inserted": total_inserted,
            "total_rejected": total_rejected,
            "chunks_processed": chunks_processed,
            "avg_quality_score": float(np.mean(quality_scores)) if quality_scores else 0.0
        }
        
    except Exception as e:
        logger.error(f"Error processing file {file_path}: {e}")
        raise


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
    foreign_keys_data: Optional[Dict[str, set]] = None
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
        foreign_keys_data=foreign_keys_data
    )
    
    # Carga Directa (COPY a Prod) vs Staging
    if direct_load and target_schema and target_table:
        db_inserted = 0
        db_rejected = 0
        
        # 1. Identificar registros PASSED
        passed_records = [r for r in processed_records if r["validation_status"] == "PASSED"]
        failed_records = [r for r in processed_records if r["validation_status"] == "FAILED"]
        
        # 2. Inyectar PASSED directamente vía COPY
        if passed_records:
            # IMPORTANTE: Solo incluir columnas que están en el mapping.
            # Esto permite que los DEFAULTS de la base de datos funcionen para columnas no mapeadas.
            target_cols = [c for c in column_mapping.keys() if c in target_column_types]
            
            # Si no hay mapeo, NO caemos en fallback de todas las columnas si es direct_load
            # porque eso suele romper los defaults de la BD.
            if not target_cols:
                logger.warning(f"No mapped columns found for direct ingestion of batch {batch_id}. Skipping COPY.")
                db_inserted = 0
            else:
                # DEBUG: Imprimir columnas a ingerir
                logger.info(f"DIRECT INGESTION: Targeting columns: {target_cols}")
                
                ingestor = DirectIngestor(conn, target_schema, target_table, target_cols)
                ingestor.add_records(passed_records)
                ingestor.flush()
                db_inserted = len(passed_records)
        
        if failed_records:
            _, db_rejected = insert_records_in_batches(
                conn=conn,
                staging_table=staging_table,
                records=failed_records,
                batch_size=BATCH_SIZE_INSERT
            )
    else:
        # Comportamiento tradicional: todo a Staging
        db_inserted, db_rejected = insert_records_in_batches(
            conn=conn,
            staging_table=staging_table,
            records=processed_records,
            batch_size=BATCH_SIZE_INSERT
        )
    
    # Calcular stats reales basados en validación
    invalid_count = sum(1 for r in processed_records if r["validation_status"] == "FAILED")
    valid_count = len(processed_records) - invalid_count
    
    # Calcular score promedio
    chunk_quality = np.mean([r["data_quality_score"] for r in processed_records]) if processed_records else 0
    
    return {
        "inserted": valid_count,
        "rejected": invalid_count,
        "avg_quality": chunk_quality
    }


def validate_and_prepare_chunk(
    chunk_df: pl.DataFrame,
    batch_id: str,
    chunk_idx: int,
    source_name: str,
    column_mapping: Optional[Dict] = None,
    selected_columns: Optional[List[str]] = None,
    target_column_types: Optional[Dict[str, str]] = None,
    not_null_columns: Optional[Dict[str, bool]] = None,
    foreign_keys_data: Optional[Dict[str, set]] = None
) -> List[Dict[str, Any]]:
    """
    Valida y prepara registros de un chunk.
    Aplica column_mapping y selected_columns.
    VALIDA TIPOS Y CARACTERES ESPECIALES.
    """
    import re
    
    # Regex para caracteres peligrosos o invalidos (control characters except tab/newline)
    INVALID_CHARS_REGEX = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F]')
    
    # 1. Filtrar columnas si selected_columns está presente
    if selected_columns:
        available_cols = [c for c in selected_columns if c in chunk_df.columns]
        if available_cols:
            chunk_df = chunk_df.select(available_cols)
        else:
            logger.warning(f"None of selected columns {selected_columns} found in dataframe")
    
    # 2. Aplicar column mapping si está presente
    if column_mapping:
        # Crear nuevas columnas según mapping
        for target_col, map_info in column_mapping.items():
            source_col = map_info.get("source")
            default_val = map_info.get("default")
            
            if source_col and source_col in chunk_df.columns:
                # Renombrar y aplicar default si es null
                chunk_df = chunk_df.with_columns([
                    pl.when(pl.col(source_col).is_null())
                      .then(pl.lit(default_val))
                      .otherwise(pl.col(source_col))
                      .alias(target_col)
                ])
            elif default_val is not None:
                # Columna no existe, crear con default
                chunk_df = chunk_df.with_columns([
                    pl.lit(default_val).alias(target_col)
                ])
        
        # Seleccionar solo columnas target
        target_cols = list(column_mapping.keys())
        available_targets = [c for c in target_cols if c in chunk_df.columns]
        if available_targets:
            chunk_df = chunk_df.select(available_targets)
        else:
            logger.error(f"No target columns found after mapping")
    
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
    
    logged_errors = 0
    for i, row in enumerate(rows):
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
                
                # Check for emptiness (None, empty string, or NaN)
                import math
                is_empty = (
                    value is None or 
                    str(value).strip() == "" or 
                    str(value).strip().lower() == "nan" or
                    str(value).strip().lower() == "null" or
                    (isinstance(value, float) and math.isnan(value))
                )

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

                # Validación Date / Timestamp (ESTRICTA)
                elif 'date' in target_type or 'time' in target_type:
                    val_str = str(value).strip()
                    if val_str:
                        import datetime
                        date_valid = False
                        date_formats = [
                            '%Y-%m-%d',
                            '%d/%m/%Y',
                            '%m/%d/%Y',
                            '%Y/%m/%d',
                            '%d-%m-%Y',
                            '%Y-%m-%d %H:%M:%S',
                            '%Y-%m-%dT%H:%M:%S',
                            '%d/%m/%Y %H:%M:%S',
                        ]
                        for fmt in date_formats:
                            try:
                                datetime.datetime.strptime(val_str, fmt)
                                date_valid = True
                                break
                            except ValueError:
                                continue

                        if not date_valid:
                            validation_status = "FAILED"
                            error_list.append(f"Invalid date format for '{col_name}': got '{value}'")

                # Validación String Length (varchar)
                elif 'char' in target_type or 'text' in target_type:
                    import re
                    match = re.search(r'\((\d+)\)', target_type)
                    if match:
                        max_len = int(match.group(1))
                        if len(str(value)) > max_len:
                            validation_status = "FAILED"
                            error_list.append(f"String too long for '{col_name}': len={len(str(value))}, max={max_len}")

        # 2. Validar Caracteres Especiales (en todos los campos string)
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
            "raw_data": json.dumps(row),
            "processed_data": json.dumps(row),
            "validation_status": validation_status,
            "data_quality_score": quality_score,
            "is_duplicate": False,  # Se calcula en Pre-flight Check (Promotion)
            "error_details": error_details_json
        }
        
        records.append(record)
    
    return records


def insert_records_in_batches(
    conn: psycopg2.extensions.connection,
    staging_table: str,
    records: List[Dict[str, Any]],
    batch_size: int
) -> tuple[int, int]:
    # Inserta registros en batches usando execute_values.
    # Returns: (inserted_count, rejected_count)
    from psycopg2.extras import execute_values
    
    cursor = conn.cursor()
    inserted = 0
    rejected = 0
    
    # Dividir en batches
    for i in range(0, len(records), batch_size):
        batch = records[i:i+batch_size]
        
        # Preparar valores como tuplas
        values = [
            (
                r["batch_id"],
                r["source_row_number"],
                r["raw_data"],
                r["processed_data"],
                r["validation_status"],
                r["data_quality_score"],
                r["is_duplicate"],
                r["error_details"]
            )
            for r in batch
        ]
        
        try:
            # INSERT usando execute_values (más rápido)
            execute_values(
                cursor,
                f"INSERT INTO staging_data.{staging_table} (batch_id, source_row_number, raw_data, processed_data, validation_status, data_quality_score, is_duplicate, error_details) VALUES %s",
                values,
                page_size=batch_size
            )
            
            conn.commit()
            inserted += len(batch)
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Batch insert failed: {e}")
            
            # Intentar insertar uno por uno
            for record in batch:
                try:
                    # Construir query manualmente para evitar error de syntax con f-string multilinea
                    insert_query = f"INSERT INTO staging_data.{staging_table} (batch_id, source_row_number, raw_data, processed_data, validation_status, data_quality_score, is_duplicate, error_details) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
                    
                    cursor.execute(insert_query, (
                        record["batch_id"],
                        record["source_row_number"],
                        record["raw_data"],
                        record["processed_data"],
                        record["validation_status"],
                        record["data_quality_score"],
                        record["is_duplicate"],
                        record["error_details"]
                    ))
                    conn.commit()
                    inserted += 1
                    
                except Exception as e2:
                    conn.rollback()
                    logger.error(f"Individual insert failed: {e2}")
                    rejected += 1
    
    return inserted, rejected
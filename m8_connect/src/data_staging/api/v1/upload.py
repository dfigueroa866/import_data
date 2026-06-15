# src/data_staging/api/v1/upload.py - Complete File Upload Implementation

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
import uuid
import os
import shutil
import asyncio
from pathlib import Path
from datetime import datetime, timezone
import polars as pl
import json
from typing import List, Optional, Dict, Any, Tuple
from pydantic import BaseModel
import logging
from data_staging.schemas.upload import (
    BulkDeleteRequest,
    BulkDeleteFiltersRequest,
    ColumnMapping,
    ProcessRequest,
)

from data_staging.database import get_db_session, get_database_session
from data_staging.config import settings
from data_staging.utils.encoding_utils import (
    detect_file_encoding,
    encoding_for_polars,
    encoding_for_python,
    normalize_encoding_name,
)
from data_staging.utils.json_helpers import to_json_safe
from data_staging.utils.parquet_typing import fetch_target_column_types_sql
from data_staging.auth.security import (
    TokenUser,
    get_current_user,
    ensure_organization_id_mapping,
)
from data_staging.utils.batch_control import (
    collect_batch_file_paths,
    is_safe_sql_identifier,
    normalize_metadata,
    resolve_effective_file_path,
    resolve_original_file_path,
    staging_table_for_source,
    with_file_path,
)



logger = logging.getLogger(__name__)

# Sin actualización de progreso y sin job activo en cola → preview/validación huérfana (p. ej. reinicio del worker).
PREVIEW_STALE_SECONDS = 600
VALIDATION_STALE_SECONDS = 600
PROMOTION_STALE_SECONDS = 600


def _validation_job_active(db: Session, batch_id: str) -> bool:
    row = db.execute(
        text("""
            SELECT 1 FROM staging_meta.job_queue
            WHERE job_type = 'VALIDATE_BATCH'
              AND payload->>'batch_id' = :batch_id
              AND status IN ('PENDING', 'PROCESSING')
            LIMIT 1
        """),
        {"batch_id": batch_id},
    ).fetchone()
    return row is not None


def _promotion_job_active(db: Session, batch_id: str) -> bool:
    row = db.execute(
        text("""
            SELECT 1 FROM staging_meta.job_queue
            WHERE job_type = 'PROMOTE_BATCH'
              AND payload->>'batch_id' = :batch_id
              AND status IN ('PENDING', 'PROCESSING')
            LIMIT 1
        """),
        {"batch_id": batch_id},
    ).fetchone()
    return row is not None


def _preview_job_active(db: Session, batch_id: str) -> bool:
    row = db.execute(
        text("""
            SELECT 1 FROM staging_meta.job_queue
            WHERE job_type = 'PREVIEW_BATCH'
              AND payload->>'batch_id' = :batch_id
              AND status IN ('PENDING', 'PROCESSING')
            LIMIT 1
        """),
        {"batch_id": batch_id},
    ).fetchone()
    return row is not None


def _parse_iso_utc_timestamp(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        text = str(value).strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _preview_progress_updated_at(metadata: Dict[str, Any]) -> Optional[datetime]:
    progress = metadata.get("processing_progress") or {}
    return _parse_iso_utc_timestamp(progress.get("updated_at"))


def _is_orphan_promotion(
    metadata: Dict[str, Any],
    batch_id: str,
    *,
    batch_status: Optional[str] = None,
    db: Optional[Session] = None,
) -> bool:
    """True when promotion progress is stuck without an active PROMOTE_BATCH job."""
    if batch_status not in ("COMPLETED", "PARTIALLY_PROMOTED", None):
        return False
    progress = metadata.get("processing_progress") or {}
    phase = progress.get("phase")
    if phase not in ("promoting", "staging", "queued"):
        return False
    if db is not None and _promotion_job_active(db, batch_id):
        return False
    updated = _preview_progress_updated_at(metadata)
    if updated is None:
        return True
    age_seconds = (datetime.now(timezone.utc) - updated).total_seconds()
    return age_seconds >= PROMOTION_STALE_SECONDS


def _recover_orphan_promotion(
    db: Session,
    batch_id: str,
    metadata: Dict[str, Any],
    *,
    reason: str,
) -> Dict[str, Any]:
    recovered = dict(metadata)
    progress = dict(recovered.get("processing_progress") or {})
    progress["phase"] = "promotion_failed"
    progress["current_operation"] = reason
    recovered["processing_progress"] = progress
    recovered["promotion_error"] = reason
    db.execute(
        text("""
            UPDATE staging_meta.batch_control
            SET metadata = :metadata,
                error_message = :error_message,
                updated_at = CURRENT_TIMESTAMP
            WHERE batch_id = :batch_id
        """),
        {
            "metadata": json.dumps(recovered),
            "error_message": reason,
            "batch_id": batch_id,
        },
    )
    db.commit()
    logger.warning("Recovered orphan promotion for batch %s", batch_id)
    return recovered


def _is_orphan_preview(metadata: Dict[str, Any], batch_id: str, db: Optional[Session] = None) -> bool:
    """True when DB says preview is running but no PREVIEW_BATCH job is active."""
    if not metadata.get("preview_in_progress"):
        return False
    if db is not None and _preview_job_active(db, batch_id):
        return False
    updated = _preview_progress_updated_at(metadata)
    if updated is None:
        return True
    age_seconds = (datetime.now(timezone.utc) - updated).total_seconds()
    return age_seconds >= PREVIEW_STALE_SECONDS


def _recover_orphan_preview(
    db: Session,
    batch_id: str,
    metadata: Dict[str, Any],
    *,
    reason: str,
) -> Dict[str, Any]:
    recovered = dict(metadata)
    recovered["preview_in_progress"] = False
    recovered["preview_error"] = reason
    db.execute(
        text("""
            UPDATE staging_meta.batch_control
            SET metadata = :metadata, updated_at = CURRENT_TIMESTAMP
            WHERE batch_id = :batch_id
        """),
        {"metadata": json.dumps(recovered), "batch_id": batch_id},
    )
    db.commit()
    logger.warning("Recovered orphan preview for batch %s", batch_id)
    return recovered


def _is_orphan_validation(
    metadata: Dict[str, Any], batch_id: str, db: Optional[Session] = None
) -> bool:
    """True when DB says validation is running but no VALIDATE_BATCH job is active."""
    if not metadata.get("validation_in_progress"):
        return False
    if metadata.get("validation_complete"):
        return False
    if db is not None and _validation_job_active(db, batch_id):
        return False
    updated = _preview_progress_updated_at(metadata)
    if updated is None:
        return True
    age_seconds = (datetime.now(timezone.utc) - updated).total_seconds()
    return age_seconds >= VALIDATION_STALE_SECONDS


def _recover_orphan_validation(
    db: Session,
    batch_id: str,
    metadata: Dict[str, Any],
    *,
    reason: str,
) -> Dict[str, Any]:
    recovered = dict(metadata)
    recovered["validation_in_progress"] = False
    recovered["validation_error"] = reason
    db.execute(
        text("""
            UPDATE staging_meta.batch_control
            SET metadata = :metadata, updated_at = CURRENT_TIMESTAMP
            WHERE batch_id = :batch_id
        """),
        {"metadata": json.dumps(recovered), "batch_id": batch_id},
    )
    db.commit()
    logger.warning("Recovered orphan validation for batch %s", batch_id)
    return recovered


def _resolve_preview_encoding(file_path: str, file_analysis: Dict[str, Any]) -> str:
    """Prefer encoding detected in step 1; detect only when missing."""
    stored = normalize_encoding_name(file_analysis.get("encoding", "utf-8"))
    if file_analysis.get("encoding"):
        return stored
    if Path(file_path).suffix.lower() == ".parquet":
        return stored
    if file_path and Path(file_path).is_file():
        return normalize_encoding_name(detect_file_encoding(file_path))
    return stored


def _build_preview_response_payload(
    *,
    batch_id: str,
    batch_source_name: str,
    metadata: Dict[str, Any],
    agg_stats: Dict[str, Any],
    org_id: str,
    load_type: str,
    process_type: Optional[str],
) -> Dict[str, Any]:
    preview_stats = dict(agg_stats)
    preview_data = preview_stats.pop("preview_data", None)
    if preview_data is None:
        preview_data = []

    if load_type == "history":
        from data_staging.services.history.history_config import enrich_history_preview_rows

        preview_data = enrich_history_preview_rows(
            preview_data or [],
            process_type=process_type,
            source_extension=metadata.get("source_extension"),
            organization_id=org_id,
        )

    return to_json_safe({
        "batch_id": batch_id,
        "validation_summary": preview_stats,
        "target_schema": metadata.get("target_schema"),
        "target_table": metadata.get("target_table"),
        "staging_table": batch_source_name,
        "load_type": load_type,
        "process_type": process_type,
        "organization_id": org_id,
        "organization_name": None,
        "validated_in_preview": metadata.get("validated_in_preview", False),
        "preview_data": preview_data,
    })


def _map_preview_progress_phase(metadata: Dict[str, Any], phase: str) -> str:
    if phase in ("mapping_validating", "mapping_validation_done"):
        return phase
    if not metadata.get("preview_in_progress"):
        return phase
    if phase in ("preview_validating", "preview_aggregating", "preview_failed"):
        return phase
    if phase in ("validating", "finishing", "preparing", "queued"):
        return "preview_validating"
    if phase == "done" and metadata.get("preview_generated"):
        return "preview_done"
    return phase


router = APIRouter()


_batch_org_column_ready = False


def _ensure_batch_control_org_column(db: Session) -> None:
    """Columna organization_id: una sola vez por proceso, sin ALTER en cada request."""
    global _batch_org_column_ready
    if _batch_org_column_ready:
        return
    try:
        exists = db.execute(
            text("""
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'staging_meta'
                  AND table_name = 'batch_control'
                  AND column_name = 'organization_id'
                LIMIT 1
            """)
        ).fetchone()
        if not exists:
            db.execute(
                text("""
                    ALTER TABLE staging_meta.batch_control
                    ADD COLUMN IF NOT EXISTS organization_id TEXT
                """)
            )
            db.execute(
                text("""
                    UPDATE staging_meta.batch_control
                    SET organization_id = metadata->>'organization_id'
                    WHERE (organization_id IS NULL OR organization_id = '')
                      AND metadata->>'organization_id' IS NOT NULL
                      AND metadata->>'organization_id' <> ''
                """)
            )
        db.commit()
        _batch_org_column_ready = True
    except Exception as exc:
        db.rollback()
        logger.warning("No se pudo asegurar organization_id en batch_control: %s", exc)


def _staging_table_exists(db: Session, table_name: str) -> bool:
    if not is_safe_sql_identifier(table_name):
        return False
    return (
        db.execute(
            text("""
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'staging_data'
                  AND table_name = :table_name
                LIMIT 1
            """),
            {"table_name": table_name},
        ).fetchone()
        is not None
    )


def _delete_batch_files(batch_id: str, row_metadata: Any, file_path_column: Optional[str]) -> None:
    meta = normalize_metadata(row_metadata)
    paths = collect_batch_file_paths(meta, file_path_column)
    load_storage_dir = meta.get("load_storage_dir")

    # Buscar archivos legacy en disco plano que comiencen con el batch_id prefix
    try:
        from data_staging.config import settings
        upload_dir = Path(settings.UPLOAD_PATH)
        temp_dir = Path(settings.TEMP_PATH)

        for directory in (upload_dir, temp_dir):
            if directory.exists() and directory.is_dir():
                for file_in_dir in directory.iterdir():
                    if file_in_dir.is_file() and file_in_dir.name.startswith(batch_id):
                        paths.append(str(file_in_dir.resolve()))
    except Exception as exc:
        logger.warning("Error al buscar archivos adicionales para el batch %s: %s", batch_id, exc)

    seen = set()
    for path_str in paths:
        if path_str == load_storage_dir:
            continue
        p = Path(path_str).resolve()
        p_str = str(p)
        if p_str in seen:
            continue
        seen.add(p_str)
        try:
            if p.is_file():
                p.unlink()
                logger.info("Archivo eliminado: %s", p_str)
        except OSError as exc:
            logger.warning("No se pudo borrar archivo %s: %s", p_str, exc)

    if load_storage_dir:
        storage_path = Path(str(load_storage_dir))
        if storage_path.is_dir():
            try:
                shutil.rmtree(storage_path)
                logger.info("Carpeta de carga eliminada: %s", storage_path)
            except OSError as exc:
                logger.warning(
                    "No se pudo borrar carpeta de carga %s: %s",
                    storage_path,
                    exc,
                )


def _signal_batches_cancelled(db: Session, batch_ids: List[str]) -> None:
    """Marca batches y jobs activos como cancelados antes de borrar o detener workers."""
    if not batch_ids:
        return
    db.execute(
        text("""
            UPDATE staging_meta.job_queue
            SET status = 'CANCELLED',
                error_message = COALESCE(error_message, 'Cancelled by user'),
                completed_at = CURRENT_TIMESTAMP,
                started_at = NULL,
                worker_id = NULL
            WHERE payload->>'batch_id' = ANY(:ids)
              AND status IN ('PENDING', 'PROCESSING')
        """),
        {"ids": batch_ids},
    )
    db.execute(
        text("""
            UPDATE staging_meta.batch_control
            SET status = 'CANCELLED',
                error_message = COALESCE(error_message, 'Cancelado por el usuario'),
                completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP),
                metadata = metadata || jsonb_build_object(
                    'preview_in_progress', false,
                    'validation_in_progress', false,
                    'processing_progress', jsonb_build_object(
                        'phase', 'cancelled',
                        'current_operation', 'Cancelado por el usuario',
                        'progress_percentage', 0
                    )
                ),
                updated_at = CURRENT_TIMESTAMP
            WHERE batch_id::text = ANY(:ids)
              AND status NOT IN ('PROMOTED', 'PARTIALLY_PROMOTED', 'CANCELLED')
        """),
        {"ids": batch_ids},
    )


def _purge_batches_bulk(db: Session, rows: list) -> int:
    """Elimina varios batches en pocas consultas (sin timeout por fila)."""
    if not rows:
        return 0

    db.execute(text("SET LOCAL statement_timeout = '0'"))

    batch_ids = [str(r.batch_id) for r in rows]
    _signal_batches_cancelled(db, batch_ids)
    db.commit()
    by_table: Dict[str, List[str]] = {}
    for row in rows:
        table = staging_table_for_source(row.source_name or "")
        by_table.setdefault(table, []).append(str(row.batch_id))

    for table, ids in by_table.items():
        if not _staging_table_exists(db, table):
            continue
        db.execute(
            text(
                f"DELETE FROM staging_data.{table} "
                "WHERE batch_id::text = ANY(:ids)"
            ),
            {"ids": ids},
        )

    db.execute(
        text("""
            DELETE FROM staging_meta.job_queue
            WHERE payload->>'batch_id' = ANY(:ids)
        """),
        {"ids": batch_ids},
    )
    db.execute(
        text(
            "DELETE FROM staging_meta.validation_logs "
            "WHERE batch_id::text = ANY(:ids)"
        ),
        {"ids": batch_ids},
    )
    db.execute(
        text(
            "DELETE FROM staging_meta.load_history "
            "WHERE batch_id::text = ANY(:ids)"
        ),
        {"ids": batch_ids},
    )
    db.execute(
        text(
            "DELETE FROM staging_meta.batch_control "
            "WHERE batch_id::text = ANY(:ids)"
        ),
        {"ids": batch_ids},
    )

    for row in rows:
        _delete_batch_files(str(row.batch_id), row.metadata, row.file_path)

    return len(batch_ids)


def _batch_filters_where(
    *,
    status: Optional[str] = None,
    source_name: Optional[str] = None,
    search: Optional[str] = None,
    organization_id: Optional[str] = None,
) -> tuple[str, Dict[str, Any]]:
    conditions: List[str] = []
    params: Dict[str, Any] = {}
    if status:
        conditions.append("bc.status = :status")
        params["status"] = status
    if source_name:
        conditions.append("bc.source_name ILIKE :source_name")
        params["source_name"] = f"%{source_name}%"
    if search:
        conditions.append(
            "("
            "bc.batch_id::text ILIKE :search OR "
            "bc.source_name ILIKE :search OR "
            "COALESCE(bc.file_name, '') ILIKE :search"
            ")"
        )
        params["search"] = f"%{search.strip()}%"
    if organization_id:
        conditions.append(
            "COALESCE(bc.organization_id, bc.metadata->>'organization_id') = :organization_id"
        )
        params["organization_id"] = organization_id
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return where_clause, params


def _batch_id_exists_clause(where_clause: str) -> str:
    return (
        " AND bc.batch_id = :batch_id"
        if where_clause
        else " WHERE bc.batch_id = :batch_id"
    )


def _delete_batch_record(db: Session, batch_id: str) -> bool:
    """Elimina batch, staging, jobs y archivos en disco."""
    row = db.execute(
        text("""
            SELECT batch_id, source_name, file_path, metadata
            FROM staging_meta.batch_control
            WHERE batch_id = :batch_id
        """),
        {"batch_id": batch_id},
    ).fetchone()
    if not row:
        return False
    return _purge_batches_bulk(db, [row]) > 0




class FileUploadService:
    """Service for handling file uploads and processing"""
    
    def __init__(self):
        self.upload_dir = Path(settings.UPLOAD_PATH)
        self.temp_dir = Path(settings.TEMP_PATH)
        self.allowed_extensions = settings.ALLOWED_FILE_EXTENSIONS
        self.max_file_size = settings.MAX_FILE_SIZE
        
        # Ensure directories exist
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
    
    def validate_file(self, file: UploadFile) -> Dict[str, Any]:
        """Validate uploaded file"""
        errors = []
        
        # Check file extension
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in self.allowed_extensions:
            errors.append(f"File extension {file_ext} not allowed. Allowed: {self.allowed_extensions}")
        
        # Check file size (if we can get it)
        if hasattr(file, 'size') and file.size:
            if file.size > self.max_file_size:
                errors.append(f"File size {file.size} exceeds maximum {self.max_file_size} bytes")
        
        # Check filename
        if not file.filename or len(file.filename) == 0:
            errors.append("Filename is required")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "file_extension": file_ext,
            "file_size": getattr(file, 'size', None)
        }
    
    async def save_file(
        self,
        file: UploadFile,
        batch_id: str,
        *,
        storage_dir: Optional[Path] = None,
        target_column_types: Optional[Dict[str, str]] = None,
    ) -> Tuple[Path, Optional[Dict[str, Any]]]:
        """Save upload to disk. CSV uploads are converted to typed .raw.parquet."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_ext = Path(file.filename).suffix
        safe_filename = f"{batch_id}_{timestamp}_{file.filename}"
        base_dir = storage_dir if storage_dir is not None else self.upload_dir
        base_dir.mkdir(parents=True, exist_ok=True)
        file_path = base_dir / safe_filename

        try:
            with open(file_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)

            logger.info(f"File saved: {file_path}")

            if file_ext.lower() == ".csv":
                file_analysis = self.analyze_file_structure(file_path)
                if file_analysis.get("error"):
                    raise HTTPException(
                        status_code=400,
                        detail=file_analysis["error"],
                    )
                try:
                    from data_staging.utils.raw_parquet import csv_to_raw_parquet

                    raw_parquet = csv_to_raw_parquet(
                        file_path,
                        delimiter=file_analysis.get("delimiter", ","),
                        target_column_types=target_column_types,
                    )
                    file_path.unlink(missing_ok=True)
                    logger.info(
                        "CSV converted to raw Parquet (source removed): %s",
                        raw_parquet,
                    )
                    file_analysis["logical_file_type"] = "csv"
                    file_analysis["stored_format"] = "raw_parquet"
                    return raw_parquet, file_analysis
                except HTTPException:
                    raise
                except Exception as conv_exc:
                    logger.error("CSV to Parquet conversion failed: %s", conv_exc)
                    raise HTTPException(
                        status_code=500,
                        detail=f"Error converting CSV to Parquet: {conv_exc}",
                    ) from conv_exc

            return file_path, None

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error saving file: {e}")
            raise HTTPException(status_code=500, detail=f"Error saving file: {str(e)}")
    
    def detect_file_type(self, file_path: Path) -> str:
        """Detect file type and structure"""
        name_lower = file_path.name.lower()
        file_ext = file_path.suffix.lower()

        if name_lower.endswith(".raw.parquet") or file_ext == ".parquet":
            return "parquet"
        if file_ext in [".csv"]:
            return "csv"
        if file_ext in [".xlsx", ".xls"]:
            return "excel"
        if file_ext in [".json"]:
            return "json"
        return "unknown"
    
    def analyze_file_structure(self, file_path: Path) -> Dict[str, Any]:
        """Analyze file structure and extract metadata"""
        file_type = self.detect_file_type(file_path)
        
        try:
            if file_type == 'csv':
                detected_encoding = normalize_encoding_name(
                    detect_file_encoding(file_path)
                )
                pl_encoding = encoding_for_polars(detected_encoding)
                sample_df = None
                read_error = None
                detected_delimiter = ","
                text_encoding = encoding_for_python(detected_encoding)

                try:
                    curr_delimiter = ","
                    sample_df = pl.read_csv(
                        file_path,
                        n_rows=100,
                        encoding=pl_encoding,
                        ignore_errors=True,
                        truncate_ragged_lines=True,
                        infer_schema_length=100,
                    )

                    if len(sample_df.columns) == 1:
                        with open(file_path, "r", encoding=text_encoding) as f:
                            first_line = f.readline()
                            if "," in first_line or ";" in first_line or "\t" in first_line:
                                f.seek(0)
                                import csv

                                dialect = csv.Sniffer().sniff(f.read(1024))
                                curr_delimiter = dialect.delimiter

                                sample_df = pl.read_csv(
                                    file_path,
                                    n_rows=100,
                                    separator=curr_delimiter,
                                    encoding=pl_encoding,
                                    ignore_errors=True,
                                    truncate_ragged_lines=True,
                                    infer_schema_length=100,
                                )
                    detected_delimiter = curr_delimiter
                except Exception as e:
                    read_error = e

                if sample_df is None:
                    raise Exception(f"Failed to read CSV. Last error: {read_error}")

                # Convert column types to string for JSON serialization
                column_types = {col: str(dtype) for col, dtype in zip(sample_df.columns, sample_df.dtypes)}
                
                # Get sample data and replace null with None for JSON serialization
                sample_rows = sample_df.head(5).to_dicts()

                return {
                    "file_type": file_type,
                    "columns": list(sample_df.columns),
                    "column_types": column_types,
                    "sample_rows": len(sample_df),
                    "estimated_total_rows": self._estimate_csv_rows(file_path),
                    "sample_data": sample_rows,
                    "delimiter": detected_delimiter,
                    "encoding": detected_encoding
                }

            elif file_type == "parquet":
                from data_staging.utils.chunk_iterators import count_parquet_rows

                sample_df = pl.scan_parquet(file_path).head(100).collect()
                column_types = {
                    col: str(dtype) for col, dtype in zip(sample_df.columns, sample_df.dtypes)
                }
                sample_rows = sample_df.head(5).to_dicts()
                return {
                    "file_type": "parquet",
                    "columns": list(sample_df.columns),
                    "column_types": column_types,
                    "sample_rows": len(sample_df),
                    "estimated_total_rows": count_parquet_rows(file_path),
                    "sample_data": sample_rows,
                    "delimiter": ",",
                    "encoding": "utf-8",
                    "stored_format": "raw_parquet"
                    if file_path.name.lower().endswith(".raw.parquet")
                    else "parquet",
                }
            
            elif file_type == 'excel':
                # Analyze Excel using Polars
                sample_df = pl.read_excel(file_path, sheet_id=1)
                
                # Note: Polars doesn't have easy sheet name detection, use pandas for that only
                import pandas as pd_temp
                excel_file = pd_temp.ExcelFile(file_path)
                sheet_names = excel_file.sheet_names
                
                # Convert column types
                column_types = {col: str(dtype) for col, dtype in zip(sample_df.columns, sample_df.dtypes)}
                sample_rows = sample_df.head(5).to_dicts()
                
                return {
                    "file_type": file_type,
                    "sheet_names": sheet_names,
                    "default_sheet": sheet_names[0],
                    "columns": list(sample_df.columns),
                    "column_types": column_types,
                    "sample_rows": len(sample_df),
                    "sample_data": sample_rows
                }
            
            elif file_type == 'json':
                # Analyze JSON using Polars
                try:
                    # Try reading as NDJSON first (one JSON object per line)
                    sample_df = pl.read_ndjson(file_path)
                    
                    column_types = {col: str(dtype) for col, dtype in zip(sample_df.columns, sample_df.dtypes)}
                    sample_rows = sample_df.head(5).to_dicts()
                    
                    return {
                        "file_type": file_type,
                        "structure": "ndjson",
                        "columns": list(sample_df.columns),
                        "column_types": column_types,
                        "sample_rows": len(sample_df),
                        "estimated_total_rows": len(sample_df),
                        "sample_data": sample_rows
                    }
                except:
                    # Fallback: regular JSON array
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    if isinstance(data, list) and len(data) > 0:
                        return {
                            "file_type": file_type,
                            "structure": "array",
                            "columns": list(data[0].keys()) if isinstance(data[0], dict) else [],
                            "sample_rows": min(len(data), 100),
                            "estimated_total_rows": len(data),
                            "sample_data": data[:5]
                        }
                    elif isinstance(data, dict):
                        # Single object or nested structure
                        return {
                            "file_type": file_type,
                            "structure": "object",
                            "keys": list(data.keys()),
                            "sample_data": data
                        }
            
            else:
                return {
                    "file_type": file_type,
                    "error": f"Unsupported file type: {file_type}"
                }
                
        except Exception as e:
            logger.error(f"Error analyzing file {file_path}: {e}")
            return {
                "file_type": file_type,
                "error": f"Error analyzing file: {str(e)}"
            }
    
    def _estimate_csv_rows(self, file_path: Path) -> int:
        """Estimate total rows in CSV file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                # Count lines (rough estimate)
                lines = sum(1 for _ in f)
                return max(0, lines - 1)  # Subtract header
        except:
            return 0

# Global service instance
upload_service = FileUploadService()

@router.post("/file")
async def upload_file(
    file: UploadFile = File(...),
    source_name: Optional[str] = None,
    db: Session = Depends(get_db_session)
):
    """
    Upload a file for processing.
    
    New implementation using Job Queue:
    1. Validate file
    2. Save to disk
    3. Create batch_control record
    4. Enqueue job in job_queue
    5. Return immediately
    """
    try:
        # 1. Validate file
        validation = upload_service.validate_file(file)
        if not validation["valid"]:
            raise HTTPException(
                status_code=400,
                detail=f"File validation failed: {', '.join(validation['errors'])}"
            )
        
        # 2. Generate batch ID
        batch_id = str(uuid.uuid4())
        
        # 3. Save file (CSV → .raw.parquet, source CSV removed)
        file_path, _csv_analysis = await upload_service.save_file(file, batch_id)
        file_size = file_path.stat().st_size
        
        # 4. Determine source name
        if not source_name:
            source_name = Path(file.filename).stem
        
        # 5. Create batch record
        file_path_str = str(file_path)
        upload_metadata = with_file_path(
            {"uploaded_at": datetime.utcnow().isoformat() + "Z", "original_file_path": file_path_str},
            file_path_str,
        )
        db.execute(text("""
            INSERT INTO staging_meta.batch_control 
            (batch_id, source_name, source_type, file_name, file_path, file_size,
             status, metadata, created_at, updated_at)
            VALUES (
                :batch_id, :source_name, 'file', :file_name, :file_path, :file_size,
                'UPLOADED', :metadata, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """), {
            "batch_id": batch_id,
            "source_name": source_name,
            "file_name": file.filename,
            "file_path": file_path_str,
            "file_size": file_size,
            "metadata": json.dumps(upload_metadata),
        })
        db.commit()
        
        # 6. Create job in queue (only if one doesn't exist already)
        from data_staging.workers.job_queue import create_job
        from data_staging.config import settings
        
        # Check if job already exists for this batch
        existing_job = db.execute(text("""
            SELECT job_id FROM staging_meta.job_queue
            WHERE payload->>'batch_id' = :batch_id
            AND status IN ('PENDING', 'PROCESSING')
            LIMIT 1
        """), {"batch_id": batch_id}).fetchone()
        
        if existing_job:
            job_id = str(existing_job[0])
            logger.info(f"Job already exists for batch {batch_id}: {job_id} - reusing existing job")
        else:
            job_id = create_job(
                database_url=str(settings.DATABASE_URL),
                job_type="PROCESS_FILE",
                payload={
                    "batch_id": batch_id,
                    "file_path": str(file_path),
                    "source_name": source_name
                },
                priority=0
            )
            logger.info(f"Created new job for batch {batch_id}: {job_id}")
        
        logger.info(f"File uploaded: batch_id={batch_id}, job_id={job_id}")
        
        # 7. Return immediately
        return {
            "batch_id": batch_id,
            "job_id": job_id,
            "message": "File uploaded and queued for processing",
            "file_name": file.filename,
            "file_size": file_size,
            "source_name": source_name,
            "status": "uploaded",
            "check_status_url": f"/api/v1/upload/batch/{batch_id}/status"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@router.get("/batch/{batch_id}/status")
async def get_batch_status(batch_id: str, db: Session = Depends(get_db_session)):
    """Get status of a batch upload"""
    
    try:
        # Get batch info
        result = db.execute(text("""
            SELECT batch_id, source_name, source_type, file_name, file_size, 
                   records_count, status, created_at, started_at, completed_at, 
                   error_message, metadata
            FROM staging_meta.batch_control 
            WHERE batch_id = :batch_id
        """), {"batch_id": batch_id})
        
        batch = result.fetchone()
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
        
        # 2. Obtener job info
        from data_staging.workers.job_queue import get_job_status
        from data_staging.config import settings
        
        # Buscar job asociado a este batch
        job_result = db.execute(text("""
            SELECT job_id FROM staging_meta.job_queue
            WHERE payload->>'batch_id' = :batch_id
            ORDER BY created_at DESC
            LIMIT 1
        """), {"batch_id": batch_id})
        
        job_row = job_result.fetchone()
        job_info = None
        
        if job_row:
            job_id = str(job_row[0])
            job_info = get_job_status(str(settings.DATABASE_URL), job_id)
            
        # 3. Get processing history
        result = db.execute(text("""
            SELECT load_id, load_type, target_table, records_inserted, records_updated,
                   records_rejected, data_quality_score, load_start_time, load_end_time,
                   duration_seconds, status, error_details
            FROM staging_meta.load_history 
            WHERE batch_id = :batch_id
            ORDER BY load_start_time DESC
        """), {"batch_id": batch_id})
        
        load_history = []
        for row in result:
            load_history.append({
                "load_id": row.load_id,
                "load_type": row.load_type,
                "target_table": row.target_table,
                "records_inserted": row.records_inserted,
                "records_updated": row.records_updated,
                "records_rejected": row.records_rejected,
                "data_quality_score": row.data_quality_score,
                "load_start_time": row.load_start_time.isoformat() if row.load_start_time else None,
                "load_end_time": row.load_end_time.isoformat() if row.load_end_time else None,
                "duration_seconds": row.duration_seconds,
                "status": row.status,
                "error_details": row.error_details
            })
        
        # Parse metadata
        metadata = batch.metadata if batch.metadata else {}
        
        return {
            "batch_id": batch.batch_id,
            "source_name": batch.source_name,
            "source_type": batch.source_type,
            "file_name": batch.file_name,
            "file_size": batch.file_size,
            "records_count": batch.records_count,
            "status": batch.status,
            "created_at": batch.created_at.isoformat() if batch.created_at else None,
            "started_at": batch.started_at.isoformat() if batch.started_at else None,
            "completed_at": batch.completed_at.isoformat() if batch.completed_at else None,
            "error_message": batch.error_message,
            "metadata": metadata,
            "load_history": load_history,
            "job": job_info
        }
        
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing batch: {e}")
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")



@router.post("/batch/{batch_id}/process")
async def process_batch(
    batch_id: str,
    request: ProcessRequest,
    db: Session = Depends(get_db_session),
    current_user: TokenUser = Depends(get_current_user),
):
    """
    Procesa un batch con configuración avanzada.
    Ahora usa job queue en lugar de BackgroundTasks.
    """
    try:
        # 1. Verificar batch existe
        result = db.execute(text("""
            SELECT batch_id, file_name, source_name, file_path, metadata 
            FROM staging_meta.batch_control 
            WHERE batch_id = :batch_id
        """), {"batch_id": batch_id})
        
        batch = result.fetchone()
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
        
        # 2. Obtener metadata
        metadata = normalize_metadata(batch.metadata)
        
        # 3. Actualizar metadata con request
        if request.column_mapping:
            metadata["column_mappings"] = {
                k: v.dict() for k, v in request.column_mapping.items()
            }
        
        if request.columns:
            metadata["selected_columns"] = request.columns
            
        if request.direct_load:
            metadata["direct_load"] = True
            logger.info(f"Direct load requested for batch {batch_id}")
            
        if request.auto_production:
            metadata["auto_production"] = True
            logger.info(f"Auto-production enabled for batch {batch_id}")

        org_id = current_user.organization_id
        mappings, toggles = ensure_organization_id_mapping(
            metadata.get("column_mappings", {}),
            metadata.get("column_toggles", {}),
            org_id,
        )
        metadata["column_mappings"] = mappings
        metadata["column_toggles"] = toggles
        metadata["organization_id"] = org_id

        effective_path = resolve_effective_file_path(
            metadata, file_path_column=getattr(batch, "file_path", None)
        )
        if not effective_path:
            effective_path = str(Path(settings.UPLOAD_PATH) / f"{batch_id}_{batch.file_name}")
        metadata = with_file_path(metadata, effective_path)
        metadata.pop("processing_progress", None)
        
        # 4. Guardar metadata y columnas de control
        db.execute(text("""
            UPDATE staging_meta.batch_control
            SET metadata = :metadata,
                file_path = :file_path,
                status = 'PROCESSING',
                started_at = COALESCE(started_at, CURRENT_TIMESTAMP),
                error_message = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE batch_id = :batch_id
        """), {
            "metadata": json.dumps(metadata),
            "file_path": effective_path,
            "batch_id": batch_id
        })
        db.commit()
        
        # 5. Ruta para el job
        file_path = effective_path
            
        # 5b. Fetch Target Column Types for Validation
        target_schema = metadata.get("target_schema")
        target_table = metadata.get("target_table")
        target_column_types = {}
        
        if target_schema and target_table:
            try:
                type_query = text("""
                    SELECT column_name, data_type, character_maximum_length
                    FROM information_schema.columns 
                    WHERE table_schema = :schema AND table_name = :table
                """)
                type_result = db.execute(type_query, {"schema": target_schema, "table": target_table})
                
                for row in type_result:
                    col_name = row.column_name
                    dtype = row.data_type
                    length = row.character_maximum_length
                    
                    full_type = dtype
                    if length:
                        full_type = f"{dtype}({length})"
                    
                    target_column_types[col_name] = full_type
                    
                logger.info(f"Fetched {len(target_column_types)} column types for validation")
            except Exception as e:
                logger.error(f"Failed to fetch column types: {e}")

        # 6. Crear job en queue (solo si no existe ya)
        from data_staging.workers.job_queue import create_job
        
        # Check if job already exists for this batch
        existing_job = db.execute(text("""
            SELECT job_id FROM staging_meta.job_queue
            WHERE payload->>'batch_id' = :batch_id
            AND status IN ('PENDING', 'PROCESSING')
            LIMIT 1
        """), {"batch_id": batch_id}).fetchone()
        
        if existing_job:
            job_id = str(existing_job[0])
            logger.info(f"Job already exists for batch {batch_id}: {job_id} - reusing existing job")
        else:
            job_id = create_job(
                database_url=str(settings.DATABASE_URL),
                job_type="PROCESS_FILE",
                payload={
                    "batch_id": batch_id,
                    "file_path": file_path,
                    "source_name": batch.source_name,
                    "column_mappings": metadata.get("column_mappings"),
                    "selected_columns": metadata.get("selected_columns"),
                    "auto_production": metadata.get("auto_production", False),
                    "production_schema": metadata.get("production_schema"),
                    "production_table": metadata.get("production_table"),
                    "dedup_columns": metadata.get("dedup_columns"),
                    "target_column_types": target_column_types,
                    "direct_load": metadata.get("direct_load", False)
                },
                priority=0
            )
            logger.info(f"Created new job for batch {batch_id}: {job_id}")
        
        return {
            "message": "Processing queued",
            "batch_id": batch_id,
            "job_id": job_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error queueing processing: {e}")
        raise HTTPException(status_code=500, detail=str(e))


_BATCH_ACTIVE_STATUSES = frozenset({
    "PROCESSING",
    "PENDING",
    "PENDING_PROCESS",
    "PENDING_MAPPING",
    "PENDING_PREVIEW",
})


def _as_utc_aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _format_duration_seconds(seconds: int) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        minutes, secs = divmod(seconds, 60)
        return f"{minutes}m {secs}s" if secs else f"{minutes}m"
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    parts = [f"{hours}h"]
    if minutes:
        parts.append(f"{minutes}m")
    if secs and hours < 2:
        parts.append(f"{secs}s")
    return " ".join(parts)


def _compute_batch_load_duration(
    *,
    status: str,
    created_at: Optional[datetime],
    started_at: Optional[datetime],
    completed_at: Optional[datetime],
    promotion_in_progress: bool = False,
) -> Dict[str, Any]:
    """Duration from processing start until completion (or now if still running)."""
    start = _as_utc_aware(started_at or created_at)
    if not start:
        return {
            "duration_seconds": None,
            "duration_label": None,
            "duration_in_progress": False,
        }

    in_progress = status in _BATCH_ACTIVE_STATUSES or promotion_in_progress
    end = datetime.now(timezone.utc) if in_progress else _as_utc_aware(completed_at)
    if not end:
        return {
            "duration_seconds": None,
            "duration_label": None,
            "duration_in_progress": in_progress,
        }

    seconds = max(0, int((end - start).total_seconds()))
    label = _format_duration_seconds(seconds)
    if in_progress:
        label = f"{label}…"

    return {
        "duration_seconds": seconds,
        "duration_label": label,
        "duration_in_progress": in_progress,
    }


@router.get("/batches")
async def list_batches(
    limit: int = 10,
    offset: int = 0,
    status: Optional[str] = None,
    source_name: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db_session),
    current_user: TokenUser = Depends(get_current_user),
):
    """List uploaded batches with optional filtering and pagination."""
    
    try:
        limit = max(1, min(int(limit), 100))
        offset = max(0, int(offset))

        where_clause, params = _batch_filters_where(
            status=status,
            source_name=source_name,
            search=search,
            organization_id=current_user.organization_id,
        )
        params["limit"] = limit
        params["offset"] = offset

        query = text(f"""
            SELECT bc.batch_id, bc.source_name, bc.source_type, bc.file_name, bc.file_size,
                   bc.records_count, bc.status,
                   bc.created_at, bc.started_at, bc.completed_at, bc.error_message,
                   COALESCE(bc.organization_id, bc.metadata->>'organization_id') AS organization_id,
                   o.name AS organization_name,
                   EXISTS (
                       SELECT 1
                       FROM staging_meta.job_queue jq
                       WHERE jq.payload->>'batch_id' = bc.batch_id::text
                         AND jq.job_type = 'PROMOTE_BATCH'
                         AND jq.status IN ('PENDING', 'PROCESSING')
                   ) AS promotion_in_progress
            FROM staging_meta.batch_control bc
            LEFT JOIN public.organizations o
              ON o.id::text = COALESCE(bc.organization_id, bc.metadata->>'organization_id')
            {where_clause}
            ORDER BY COALESCE(bc.created_at, bc.started_at, bc.completed_at) DESC NULLS LAST
            LIMIT :limit OFFSET :offset
        """)
        
        result = db.execute(query, params)
        
        batches = []
        for row in result:
            created_at = row.created_at
            started_at = row.started_at
            completed_at = row.completed_at
            display_at = created_at or started_at or completed_at
            duration = _compute_batch_load_duration(
                status=row.status,
                created_at=created_at,
                started_at=started_at,
                completed_at=completed_at,
                promotion_in_progress=bool(row.promotion_in_progress),
            )

            batches.append({
                "batch_id": str(row.batch_id),
                "source_name": row.source_name,
                "source_type": row.source_type,
                "file_name": row.file_name,
                "file_size": row.file_size,
                "records_count": row.records_count,
                "status": row.status,
                "created_at": created_at.isoformat() if created_at else None,
                "started_at": started_at.isoformat() if started_at else None,
                "completed_at": completed_at.isoformat() if completed_at else None,
                "display_at": display_at.isoformat() if display_at else None,
                "duration_seconds": duration["duration_seconds"],
                "duration_label": duration["duration_label"],
                "duration_in_progress": duration["duration_in_progress"],
                "promotion_in_progress": bool(row.promotion_in_progress),
                "error_message": row.error_message,
                "organization_id": row.organization_id,
                "organization_name": row.organization_name,
            })
        
        count_query = text(f"""
            SELECT COUNT(*) FROM staging_meta.batch_control bc
            {where_clause}
        """)
        total_count = db.execute(count_query, params).scalar() or 0
        page = (offset // limit) + 1 if limit else 1
        total_pages = max(1, (total_count + limit - 1) // limit) if limit else 1
        
        return {
            "batches": batches,
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "page": page,
            "total_pages": total_pages,
        }
        
    except Exception as e:
        logger.error(f"Error listing batches: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving batches: {str(e)}")


# ============================================================================
# UPLOAD WIZARD ENDPOINTS
# ============================================================================

@router.post("/file-temp")
async def upload_file_temp(
    file: UploadFile = File(...),
    target_schema: Optional[str] = Form(None),
    target_table: Optional[str] = Form(None),
    load_type: Optional[str] = Form("history"),
    process_type: Optional[str] = Form(None),
    db: Session = Depends(get_db_session),
    current_user: TokenUser = Depends(get_current_user),
):
    """
    Upload file for wizard - parses headers but doesn't process yet.
    
    Steps:
    1. Upload file
    2. Parse headers/columns
    3. Create batch record with status 'PENDING_MAPPING'
    4. Return batch_id + file_headers for Step 2 mapping
    """
    try:
        # 1. Validate file
        validation = upload_service.validate_file(file)
        if not validation["valid"]:
            raise HTTPException(
                status_code=400,
                detail=f"File validation failed: {', '.join(validation['errors'])}"
            )
        
        # 2. Generate batch ID
        batch_id = str(uuid.uuid4())

        normalized_load_type = (load_type or "history").lower()
        if normalized_load_type not in ("history", "catalog"):
            normalized_load_type = "history"

        production_table = None
        catalog_name = None
        source_name = target_table if target_table else Path(file.filename).stem

        if normalized_load_type == "history":
            from data_staging.services.history.history_config import (
                HISTORY_SOURCE_NAME,
                HISTORY_TARGET_SCHEMA,
                HISTORY_TARGET_TABLE,
                get_history_table_meta,
                is_valid_process_type,
                source_from_filename,
                valid_process_type_keys,
            )

            if not is_valid_process_type(process_type):
                valid = ", ".join(valid_process_type_keys()) or "Weekly, Monthly"
                raise HTTPException(
                    status_code=400,
                    detail=f"Selecciona un tipo de proceso válido: {valid}.",
                )

            target_schema = HISTORY_TARGET_SCHEMA
            target_table = HISTORY_TARGET_TABLE
            source_name = HISTORY_SOURCE_NAME
        elif normalized_load_type == "catalog":
            if not target_table:
                raise HTTPException(
                    status_code=400,
                    detail="Selecciona un catálogo configurado (target_table).",
                )
            from data_staging.services.catalog.catalog_registry import get_catalog_table

            catalog_entry = get_catalog_table(target_table)
            if not catalog_entry:
                raise HTTPException(
                    status_code=400,
                    detail=f"Catálogo desconocido o inactivo: {target_table}",
                )
            catalog_name = target_table
            target_schema = target_schema or catalog_entry.get("target_schema")
            production_table = catalog_entry.get("target_table") or target_table

        from data_staging.utils.load_storage_paths import (
            ensure_load_storage_dir,
            load_storage_metadata_fields,
        )

        org_id = current_user.organization_id
        if not org_id:
            raise HTTPException(status_code=400, detail="organization_id is required")

        load_timestamp = datetime.now()
        try:
            storage_dir = ensure_load_storage_dir(
                org_id,
                normalized_load_type,  # type: ignore[arg-type]
                catalog_name=catalog_name,
                load_timestamp=load_timestamp,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        target_column_types: Dict[str, str] = {}
        if target_schema and target_table:
            try:
                target_column_types = fetch_target_column_types_sql(
                    db, target_schema, target_table
                )
            except Exception as exc:
                logger.warning(
                    "Could not load target column types for typed Parquet: %s", exc
                )

        # 3. Save file (CSV → typed .raw.parquet, source CSV removed)
        file_path, csv_analysis = await upload_service.save_file(
            file,
            batch_id,
            storage_dir=storage_dir,
            target_column_types=target_column_types or None,
        )
        file_size = file_path.stat().st_size
        
        # 4. Analyze file structure and parse headers
        file_analysis = csv_analysis or upload_service.analyze_file_structure(file_path)
        
        if "error" in file_analysis:
            raise HTTPException(
                status_code=400,
                detail=f"Error analyzing file: {file_analysis['error']}"
            )
        
        file_headers = file_analysis.get("columns", [])

        # 6. Create batch record with PENDING_MAPPING status
        file_path_str = str(file_path)
        metadata = {
            "file_analysis": file_analysis,
            "file_headers": file_headers,
            "file_path": file_path_str,
            "original_file_path": file_path_str,
            "target_schema": target_schema,
            "target_table": target_table,
            "load_type": normalized_load_type,
            "process_type": process_type if normalized_load_type == "history" else None,
            "organization_id": org_id,
            "wizard_step": 1,
            **load_storage_metadata_fields(storage_dir, org_id, load_timestamp),
        }
        if catalog_name:
            metadata["catalog_name"] = catalog_name
            metadata["production_table"] = production_table
        if normalized_load_type == "history":
            metadata["history_config"] = get_history_table_meta()
            metadata["unique_keys"] = get_history_table_meta().get("unique_keys", [])
            metadata["source_extension"] = source_from_filename(file.filename or "")
        if target_column_types:
            metadata["target_column_types"] = target_column_types

        db.execute(text("""
            INSERT INTO staging_meta.batch_control 
            (batch_id, source_name, source_type, file_name, file_path, file_size,
             status, metadata, organization_id, created_at, updated_at)
            VALUES (
                :batch_id, :source_name, 'file', :file_name, :file_path, :file_size,
                'PENDING_MAPPING', :metadata, :organization_id,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """), {
            "batch_id": batch_id,
            "source_name": source_name,
            "file_name": file.filename,
            "file_path": file_path_str,
            "file_size": file_size,
            "metadata": json.dumps(metadata),
            "organization_id": org_id,
        })
        db.commit()
        
        logger.info(f"File uploaded (temp): batch_id={batch_id}, headers={len(file_headers)}")
        
        return {
            "batch_id": batch_id,
            "file_name": file.filename,
            "file_size": file_size,
            "file_type": file_analysis.get("file_type"),
            "file_headers": file_headers,
            "source_name": source_name,
            "suggested_staging_table": source_name,
            "estimated_rows": file_analysis.get("estimated_total_rows", file_analysis.get("sample_rows", 0)),
            "status": "pending_mapping",
            "message": "File uploaded successfully. Proceed to column mapping."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload temp failed: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.post("/batch/{batch_id}/mapping")
async def save_column_mapping(
    batch_id: str,
    mapping_data: Dict[str, Any],
    db: Session = Depends(get_db_session),
    current_user: TokenUser = Depends(get_current_user),
):
    """
    Save column mappings for wizard Step 2.
    
    Expected mapping_data:
    {
        "target_schema": "m8_schema",
        "target_table": "products",
        "column_mappings": {
            "product_name": {
                "target": "product_name",
                "default_value": "Unknown",
                "auto_mapped": true
            }
        },
        "column_toggles": {"product_name": true, "price": true},
        "dedup_columns": "email,phone"  // optional
    }
    """
    try:
        # 1. Verify batch exists
        result = db.execute(text("""
            SELECT batch_id, metadata FROM staging_meta.batch_control 
            WHERE batch_id = :batch_id
        """), {"batch_id": batch_id})
        
        batch = result.fetchone()
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
        
        # 2. Get existing metadata
        metadata = normalize_metadata(batch.metadata)
        
        # 3. Update metadata with mappings (organization_id always from authenticated user)
        load_type = mapping_data.get("load_type") or metadata.get("load_type", "history")
        org_id = current_user.organization_id
        column_mappings, column_toggles = ensure_organization_id_mapping(
            mapping_data.get("column_mappings", {}),
            mapping_data.get("column_toggles", {}),
            org_id,
        )
        metadata.update({
            "target_schema": mapping_data.get("target_schema"),
            "target_table": mapping_data.get("target_table"),
            "column_mappings": column_mappings,
            "column_toggles": column_toggles,
            "dedup_columns": mapping_data.get("dedup_columns"),
            "load_type": load_type,
            "process_type": mapping_data.get("process_type") if load_type == "history" else None,
            "organization_id": org_id,
            "wizard_step": 2
        })
        if load_type == "catalog":
            production_table = mapping_data.get("production_table")
            catalog_slug = mapping_data.get("target_table")
            if catalog_slug:
                metadata["catalog_name"] = catalog_slug
            if production_table:
                metadata["production_table"] = production_table
            elif catalog_slug:
                from data_staging.services.catalog.catalog_registry import get_catalog_table

                entry = get_catalog_table(catalog_slug)
                if entry:
                    metadata["production_table"] = entry.get("target_table") or catalog_slug
        elif load_type == "history":
            from data_staging.services.history.history_config import (
                HISTORY_SOURCE_NAME,
                HISTORY_TARGET_SCHEMA,
                HISTORY_TARGET_TABLE,
                get_history_table_meta,
            )

            metadata["target_schema"] = HISTORY_TARGET_SCHEMA
            metadata["target_table"] = HISTORY_TARGET_TABLE
            metadata["history_config"] = get_history_table_meta()
            metadata["unique_keys"] = get_history_table_meta().get("unique_keys", [])
            mapping_data["target_schema"] = HISTORY_TARGET_SCHEMA
            mapping_data["target_table"] = HISTORY_TARGET_TABLE

            trigger_validation = mapping_data.get("trigger_validation", True)
            if trigger_validation:
                for key in (
                    "validation_complete",
                    "validated_temp_file",
                    "rejected_temp_file",
                    "preview_result",
                    "preview_generated",
                    "aggregated_file_path",
                    "valid_temp_file",
                    "validation_error",
                    "preview_error",
                ):
                    metadata.pop(key, None)
                metadata["validation_in_progress"] = True
                metadata["preview_in_progress"] = False
                metadata["validated_in_preview"] = False

        # 4. Update source_name if target_table changed
        target_table = mapping_data.get("target_table")
        if load_type == "history":
            from data_staging.services.history.history_config import HISTORY_SOURCE_NAME

            source_name = HISTORY_SOURCE_NAME
            db.execute(text("""
                UPDATE staging_meta.batch_control
                SET metadata = :metadata,
                    source_name = :source_name,
                    organization_id = :organization_id,
                    status = 'PENDING_PREVIEW',
                    updated_at = CURRENT_TIMESTAMP
                WHERE batch_id = :batch_id
            """), {
                "metadata": json.dumps(metadata),
                "source_name": source_name,
                "organization_id": org_id,
                "batch_id": batch_id
            })
        elif target_table:
            source_name = target_table

            db.execute(text("""
                UPDATE staging_meta.batch_control
                SET metadata = :metadata,
                    source_name = :source_name,
                    organization_id = :organization_id,
                    status = 'PENDING_PREVIEW',
                    updated_at = CURRENT_TIMESTAMP
                WHERE batch_id = :batch_id
            """), {
                "metadata": json.dumps(metadata),
                "source_name": source_name,
                "organization_id": org_id,
                "batch_id": batch_id
            })
        else:
            db.execute(text("""
                UPDATE staging_meta.batch_control
                SET metadata = :metadata,
                    organization_id = :organization_id,
                    status = 'PENDING_PREVIEW',
                    updated_at = CURRENT_TIMESTAMP
                WHERE batch_id = :batch_id
            """), {
                "metadata": json.dumps(metadata),
                "organization_id": org_id,
                "batch_id": batch_id
            })
        
        db.commit()

        trigger_validation = mapping_data.get("trigger_validation", True)
        if load_type == "history" and trigger_validation:
            from data_staging.workers.job_queue import create_job as enqueue_job

            enqueue_job(
                str(settings.DATABASE_URL),
                "VALIDATE_BATCH",
                {"batch_id": batch_id, "organization_id": org_id},
            )
            logger.info("Validation job queued for batch %s (initial mapping)", batch_id)
        
        logger.info(f"Mappings saved for batch {batch_id}")
        
        return {
            "status": "success",
            "batch_id": batch_id,
            "message": "Column mappings saved successfully",
            "next_step": "preview",
            "validation_started": load_type == "history" and trigger_validation,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving mappings: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save mappings: {str(e)}")


@router.post("/batch/{batch_id}/preview")
async def generate_preview(
    batch_id: str,
    force: bool = False,
    db: Session = Depends(get_db_session),
    current_user: TokenUser = Depends(get_current_user),
):
    """
    Start preview generation for wizard Step 3 (async).
    Returns 202 while processing; poll /progress and GET /preview-result.
    """
    try:
        db.execute(text("SET LOCAL statement_timeout = '15000'"))

        result = db.execute(text("""
            SELECT batch_id, metadata, source_name FROM staging_meta.batch_control 
            WHERE batch_id = :batch_id
        """), {"batch_id": batch_id})

        batch = result.fetchone()
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")

        metadata = normalize_metadata(batch.metadata)
        org_id = current_user.organization_id

        if _is_orphan_validation(metadata, batch_id, db):
            metadata = _recover_orphan_validation(
                db,
                batch_id,
                metadata,
                reason=(
                    "La validación se interrumpió (servidor o worker detenido). "
                    "Reinicia los workers y vuelve a subir el archivo."
                ),
            )

        if _is_orphan_preview(metadata, batch_id, db):
            metadata = _recover_orphan_preview(
                db,
                batch_id,
                metadata,
                reason=(
                    "La vista previa se interrumpió (servidor reiniciado o proceso detenido). "
                    "Pulsa Reintentar."
                ),
            )

        if metadata.get("preview_result") and metadata.get("preview_generated") and not force:
            return JSONResponse(content=metadata["preview_result"])

        preview_job_active = _preview_job_active(db, batch_id)
        if metadata.get("preview_in_progress") or preview_job_active:
            if force and not preview_job_active:
                metadata["preview_in_progress"] = False
                metadata.pop("preview_error", None)
                metadata.pop("preview_result", None)
                db.execute(
                    text("""
                        UPDATE staging_meta.batch_control
                        SET metadata = :metadata, updated_at = CURRENT_TIMESTAMP
                        WHERE batch_id = :batch_id
                    """),
                    {"metadata": json.dumps(metadata), "batch_id": batch_id},
                )
                db.commit()
            else:
                return JSONResponse(
                    status_code=202,
                    content={"status": "processing", "batch_id": batch_id},
                )

        file_path = resolve_original_file_path(
            metadata, file_path_column=getattr(batch, "file_path", None)
        )
        if not file_path or not Path(file_path).is_file():
            raise HTTPException(
                status_code=400,
                detail=(
                    "No se encontró el archivo original del batch. "
                    "Vuelve al paso 1 y sube el archivo de nuevo."
                ),
            )

        load_type = metadata.get("load_type", "history")
        process_type = metadata.get("process_type")
        if load_type == "history":
            from data_staging.services.history.history_config import (
                is_valid_process_type,
                valid_process_type_keys,
            )

            if not is_valid_process_type(process_type):
                valid = ", ".join(valid_process_type_keys()) or "Weekly, Monthly"
                raise HTTPException(
                    status_code=400,
                    detail=f"Tipo de proceso inválido. Debe ser uno de: {valid}.",
                )

            if metadata.get("validation_error"):
                raise HTTPException(
                    status_code=400,
                    detail=str(metadata["validation_error"]),
                )

            if metadata.get("validation_in_progress") or _validation_job_active(db, batch_id):
                return JSONResponse(
                    status_code=202,
                    content={
                        "status": "validating",
                        "batch_id": batch_id,
                        "message": "Validación de mapeo en curso (paso 2).",
                    },
                )

            if not metadata.get("validation_complete"):
                logger.warning(
                    "Preview requested for batch %s without step-2 validation; running legacy pipeline",
                    batch_id,
                )

        if load_type == "catalog":
            if metadata.get("preview_result") and metadata.get("preview_generated") and not force:
                return JSONResponse(content=metadata["preview_result"])

            if force or metadata.get("preview_error"):
                metadata.pop("preview_error", None)
                metadata.pop("preview_result", None)
                metadata["preview_generated"] = False

            column_mappings, column_toggles = ensure_organization_id_mapping(
                metadata.get("column_mappings", {}),
                metadata.get("column_toggles", {}),
                org_id,
            )
            metadata["column_mappings"] = column_mappings
            metadata["column_toggles"] = column_toggles
            metadata["organization_id"] = org_id
            file_analysis = metadata.get("file_analysis", {}) or {}
            encoding = _resolve_preview_encoding(file_path, file_analysis)

            from data_staging.services.catalog_preview_service import (
                CatalogPreviewError,
                run_catalog_wizard_preview,
            )

            try:
                agg_stats, _agg_path = run_catalog_wizard_preview(
                    file_path,
                    metadata,
                    organization_id=org_id,
                    encoding=encoding,
                    delimiter=file_analysis.get("delimiter", ","),
                )
            except CatalogPreviewError as exc:
                metadata["preview_in_progress"] = False
                metadata["preview_error"] = str(exc)
                db.execute(
                    text("""
                        UPDATE staging_meta.batch_control
                        SET metadata = :metadata, updated_at = CURRENT_TIMESTAMP
                        WHERE batch_id = :batch_id
                    """),
                    {"metadata": json.dumps(metadata), "batch_id": batch_id},
                )
                db.commit()
                raise HTTPException(status_code=500, detail=str(exc)) from exc

            metadata["wizard_step"] = 3
            metadata["preview_generated"] = True
            metadata["preview_in_progress"] = False
            metadata.pop("preview_error", None)

            response_payload = _build_preview_response_payload(
                batch_id=batch_id,
                batch_source_name=getattr(batch, "source_name", "") or "",
                metadata=metadata,
                agg_stats=agg_stats,
                org_id=org_id,
                load_type="catalog",
                process_type="Catalog",
            )
            metadata["preview_result"] = response_payload
            db.execute(
                text("""
                    UPDATE staging_meta.batch_control
                    SET metadata = :metadata,
                        status = 'PENDING_PROCESS',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE batch_id = :batch_id
                """),
                {"metadata": json.dumps(metadata), "batch_id": batch_id},
            )
            db.commit()
            logger.info("Catalog preview generated synchronously for batch %s", batch_id)
            return JSONResponse(content=response_payload)

        metadata["preview_in_progress"] = True
        metadata.pop("preview_error", None)
        metadata.pop("preview_result", None)
        db.execute(
            text("""
                UPDATE staging_meta.batch_control
                SET metadata = :metadata, updated_at = CURRENT_TIMESTAMP
                WHERE batch_id = :batch_id
            """),
            {"metadata": json.dumps(metadata), "batch_id": batch_id},
        )
        db.commit()

        from data_staging.workers.job_queue import create_job as enqueue_job

        enqueue_job(
            str(settings.DATABASE_URL),
            "PREVIEW_BATCH",
            {"batch_id": batch_id, "organization_id": org_id},
        )

        return JSONResponse(
            status_code=202,
            content={"status": "processing", "batch_id": batch_id},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting preview: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start preview: {str(e)}")


@router.get("/batch/{batch_id}/preview-result")
async def get_preview_result(
    batch_id: str,
    db: Session = Depends(get_db_session),
    current_user: TokenUser = Depends(get_current_user),
):
    """Return preview payload when background generation completes."""
    db.execute(text("SET LOCAL statement_timeout = '15000'"))
    result = db.execute(
        text("""
            SELECT metadata FROM staging_meta.batch_control
            WHERE batch_id = :batch_id
        """),
        {"batch_id": batch_id},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Batch not found")

    metadata = normalize_metadata(row.metadata)
    if _is_orphan_preview(metadata, batch_id, db):
        metadata = _recover_orphan_preview(
            db,
            batch_id,
            metadata,
            reason=(
                "La vista previa se interrumpió (servidor reiniciado o proceso detenido). "
                "Pulsa Reintentar."
            ),
        )
    if metadata.get("preview_in_progress") or _preview_job_active(db, batch_id):
        raise HTTPException(status_code=409, detail="La vista previa sigue generándose.")

    preview_error = metadata.get("preview_error")
    if preview_error:
        raise HTTPException(status_code=500, detail=str(preview_error))

    cached = metadata.get("preview_result")
    if cached:
        return cached

    if metadata.get("preview_generated"):
        raise HTTPException(
            status_code=404,
            detail="Vista previa completada pero sin resultado en caché. Reinicia el paso 3.",
        )

    raise HTTPException(status_code=404, detail="Vista previa no iniciada.")


def _format_promotion_summary(inserted: int, updated: int) -> str:
    """Human-readable insert vs update counts after catalog promotion."""
    if inserted <= 0 and updated <= 0:
        return "Importación a producción completada."
    if updated <= 0:
        return f"{inserted:,} registro(s) insertado(s) (nuevos en la tabla)."
    if inserted <= 0:
        return f"{updated:,} registro(s) actualizado(s) (ya existían; se sobrescribieron con el archivo)."
    return (
        f"{inserted:,} insertado(s) y {updated:,} actualizado(s) "
        f"({inserted + updated:,} en total)."
    )


_PROMOTION_BATCH_SIZE = int(getattr(settings, "PROMOTION_BATCH_SIZE", 250_000))


def _promotion_chunks_total(total_rows: int) -> int:
    return max(1, (max(total_rows, 1) + _PROMOTION_BATCH_SIZE - 1) // _PROMOTION_BATCH_SIZE)


def _initial_promotion_progress(
    *,
    promote_total: int,
    rows_processed: int = 0,
    queued: bool = True,
) -> Dict[str, Any]:
    """Seed metadata.processing_progress when a PROMOTE_BATCH job is queued."""
    chunks_total = _promotion_chunks_total(promote_total)
    chunks_processed = rows_processed // _PROMOTION_BATCH_SIZE if rows_processed else 0
    pct = min(99.0, (rows_processed / max(promote_total, 1)) * 100) if promote_total else 0.0
    return {
        "progress_percentage": round(pct, 1),
        "current_operation": (
            "En cola — esperando promoción a producción…"
            if queued
            else f"Promoviendo a producción ({rows_processed:,} de {promote_total:,} registros)…"
        ),
        "phase": "queued" if queued else "promoting",
        "total_rows": promote_total,
        "rows_processed": rows_processed,
        "loaded_rows": rows_processed,
        "rejected_rows": 0,
        "chunks_processed": chunks_processed,
        "chunks_total": chunks_total,
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }


def _apply_active_promotion_progress(
    *,
    metadata: Dict[str, Any],
    batch,
    live_progress: Dict[str, Any],
    final_stats: Dict[str, Any],
    job_status: Optional[str],
) -> Dict[str, Any]:
    """Build live progress fields while batch stays COMPLETED/PARTIALLY_PROMOTED during promotion."""
    promoted = int(metadata.get("promoted_rows") or live_progress.get("rows_processed") or 0)
    promoted_inserted = int(metadata.get("promoted_inserted") or 0)
    promoted_updated = int(metadata.get("promoted_updated") or 0)
    if promoted_inserted or promoted_updated:
        promoted = max(promoted, promoted_inserted + promoted_updated)
    promote_total = int(batch.records_count or 0)
    if promote_total <= 0:
        promote_total = int(live_progress.get("total_rows") or 0)
    if promote_total <= 0:
        promote_total = max(promoted, 1)

    chunks_total = int(
        live_progress.get("chunks_total") or _promotion_chunks_total(promote_total)
    )
    chunks_processed = int(live_progress.get("chunks_processed") or 0)
    if chunks_processed == 0 and promoted > 0:
        chunks_processed = min(chunks_total, promoted // _PROMOTION_BATCH_SIZE + (1 if promoted % _PROMOTION_BATCH_SIZE else 0))

    if job_status == "PENDING":
        progress_percentage = max(float(live_progress.get("progress_percentage") or 0), 2.0)
        current_operation = live_progress.get("current_operation") or (
            "En cola — esperando promoción a producción…"
        )
        phase = live_progress.get("phase") or "queued"
    else:
        progress_percentage = float(live_progress.get("progress_percentage") or 0)
        row_pct = min(99.0, (promoted / max(promote_total, 1)) * 100)
        progress_percentage = max(progress_percentage, row_pct)
        current_operation = live_progress.get("current_operation") or (
            f"Promoviendo a producción ({promoted:,} de {promote_total:,} registros)…"
        )
        phase = live_progress.get("phase") or "promoting"

    return {
        "progress_percentage": progress_percentage,
        "current_operation": current_operation,
        "phase": phase,
        "total_rows": promote_total,
        "processed_rows": promoted,
        "loaded_rows": promoted,
        "rejected_count": int(final_stats.get("total_rejected") or 0),
        "chunks_processed": chunks_processed,
        "chunks_total": chunks_total,
        "promoted_inserted": promoted_inserted,
        "promoted_updated": promoted_updated,
    }


@router.get("/batch/{batch_id}/progress")
async def get_processing_progress(
    batch_id: str,
    db: Session = Depends(get_db_session)
):
    """
    Get real-time processing progress for wizard Step 4.
    """
    try:
        db.execute(text("SET LOCAL statement_timeout = '15000'"))

        # Get batch info
        result = db.execute(text("""
            SELECT batch_id, status, records_count, error_message, metadata,
                   source_name, started_at, completed_at
            FROM staging_meta.batch_control 
            WHERE batch_id = :batch_id
        """), {"batch_id": batch_id})
        
        batch = result.fetchone()
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
        
        metadata = normalize_metadata(batch.metadata)

        if _is_orphan_validation(metadata, batch_id, db):
            metadata = _recover_orphan_validation(
                db,
                batch_id,
                metadata,
                reason=(
                    "La validación se interrumpió (servidor o worker detenido). "
                    "Reinicia los workers y vuelve a subir el archivo."
                ),
            )

        if _is_orphan_preview(metadata, batch_id, db):
            metadata = _recover_orphan_preview(
                db,
                batch_id,
                metadata,
                reason=(
                    "La vista previa se interrumpió (servidor reiniciado o proceso detenido). "
                    "Pulsa Reintentar."
                ),
            )

        if _is_orphan_promotion(metadata, batch_id, batch_status=batch.status, db=db):
            metadata = _recover_orphan_promotion(
                db,
                batch_id,
                metadata,
                reason=(
                    "La promoción se interrumpió (servidor o worker detenido). "
                    "Reinicia los workers (python run_workers.py) y pulsa Reintentar."
                ),
            )

        # Prefer active job; stale FAILED jobs must not mask a new PROCESS_FILE run
        job_row = db.execute(text("""
            SELECT job_id, job_type, status, error_message
            FROM staging_meta.job_queue
            WHERE payload->>'batch_id' = :batch_id
              AND status IN ('PENDING', 'PROCESSING')
            ORDER BY created_at DESC
            LIMIT 1
        """), {"batch_id": batch_id}).fetchone()

        if not job_row:
            job_row = db.execute(text("""
                SELECT job_id, job_type, status, error_message
                FROM staging_meta.job_queue
                WHERE payload->>'batch_id' = :batch_id
                ORDER BY created_at DESC
                LIMIT 1
            """), {"batch_id": batch_id}).fetchone()

        job_status = job_row.status if job_row else None
        job_type = job_row.job_type if job_row else None
        job_error = job_row.error_message if job_row else None
        job_id = str(job_row.job_id) if job_row and job_row.job_id else None

        # Real-time progress written by workers into metadata.processing_progress
        live_progress = metadata.get("processing_progress", {}) or {}
        final_stats = metadata.get("processing_stats", {}) or {}

        status = batch.status
        error_message = batch.error_message
        progress_percentage = 0.0
        current_operation = "Iniciando…"
        phase = "preparing"

        file_analysis = metadata.get("file_analysis", {}) or {}
        total_rows = int(
            live_progress.get("total_rows")
            or file_analysis.get("estimated_total_rows")
            or file_analysis.get("row_count")
            or 0
        )
        processed_rows = 0
        loaded_rows = 0
        rejected_count = 0
        chunks_processed = int(live_progress.get("chunks_processed") or 0)
        chunks_total = int(live_progress.get("chunks_total") or 1)

        # Job failed but batch still in-progress → sync only when no active job remains
        if (
            job_status == "FAILED"
            and status not in ("PROMOTED", "PARTIALLY_PROMOTED", "FAILED", "PROCESSING")
        ):
            label = "Procesamiento" if job_type == "PROCESS_FILE" else "Promoción"
            error_message = job_error or error_message or f"{label} falló en el worker"
            db.execute(text("""
                UPDATE staging_meta.batch_control
                SET status = 'FAILED',
                    error_message = :error_message,
                    completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP),
                    updated_at = CURRENT_TIMESTAMP
                WHERE batch_id = :batch_id
            """), {"batch_id": batch_id, "error_message": error_message})
            db.commit()
            status = "FAILED"

        is_promote_job = job_type == "PROMOTE_BATCH"
        active_promotion = (
            is_promote_job
            and job_status in ("PENDING", "PROCESSING")
            and status in ("COMPLETED", "PARTIALLY_PROMOTED")
        )

        preview_in_progress = bool(metadata.get("preview_in_progress")) or (
            _preview_job_active(db, batch_id)
        )
        validation_in_progress = bool(metadata.get("validation_in_progress")) or (
            _validation_job_active(db, batch_id)
        )
        preview_error = metadata.get("preview_error")
        preview_result = metadata.get("preview_result")
        validation_error = metadata.get("validation_error")

        if validation_in_progress:
            progress_percentage = float(live_progress.get("progress_percentage") or 5.0)
            current_operation = live_progress.get("current_operation") or "Validando mapeo…"
            phase = live_progress.get("phase") or "mapping_validating"
            total_rows = int(live_progress.get("total_rows") or total_rows)
            processed_rows = int(live_progress.get("rows_processed") or 0)
            loaded_rows = int(live_progress.get("loaded_rows") or 0)
            rejected_count = int(live_progress.get("rejected_rows") or 0)
            chunks_processed = int(live_progress.get("chunks_processed") or chunks_processed)
            chunks_total = int(live_progress.get("chunks_total") or chunks_total)
        elif validation_error and not metadata.get("validation_complete"):
            progress_percentage = 0.0
            current_operation = f"Error en validación: {validation_error}"
            phase = "mapping_validation_failed"
        elif preview_in_progress:
            progress_percentage = float(live_progress.get("progress_percentage") or 5.0)
            current_operation = live_progress.get("current_operation") or "Generando vista previa…"
            phase = _map_preview_progress_phase(
                metadata,
                live_progress.get("phase") or "preview_validating",
            )
            total_rows = int(live_progress.get("total_rows") or total_rows)
            processed_rows = int(live_progress.get("rows_processed") or 0)
            loaded_rows = int(live_progress.get("loaded_rows") or 0)
            rejected_count = int(live_progress.get("rejected_rows") or 0)
            chunks_processed = int(live_progress.get("chunks_processed") or chunks_processed)
            chunks_total = int(live_progress.get("chunks_total") or chunks_total)
        elif preview_error and not preview_result:
            progress_percentage = 0.0
            current_operation = f"Error en vista previa: {preview_error}"
            phase = "preview_failed"
        elif preview_result or (
            metadata.get("preview_generated") and preview_result is not None
        ):
            progress_percentage = 100.0
            current_operation = "Vista previa lista"
            phase = "preview_done"
            loaded_rows = int(final_stats.get("total_inserted") or batch.records_count or 0)
            rejected_count = int(final_stats.get("total_rejected") or 0)
            processed_rows = loaded_rows + rejected_count
            if not total_rows:
                total_rows = processed_rows
        elif status == "PENDING_MAPPING":
            progress_percentage = 25
            current_operation = "Esperando mapeo de columnas"
            phase = "preparing"
        elif status == "PENDING_PREVIEW":
            progress_percentage = 50
            current_operation = "Esperando confirmación de vista previa"
            phase = "preparing"
        elif status == "PENDING_PROCESS" or status == "PENDING":
            progress_percentage = 5
            current_operation = "Listo para validar — iniciando…"
            phase = "queued"
        elif status == "PROCESSING" or (
            status in ("PENDING", "PENDING_PROCESS")
            and job_status in ("PENDING", "PROCESSING")
        ):
            if job_status == "PENDING":
                progress_percentage = max(float(live_progress.get("progress_percentage") or 0), 5.0)
                current_operation = (
                    "En cola — el worker tomará el trabajo en breve…"
                    if not is_promote_job
                    else "En cola — esperando promoción a producción…"
                )
                phase = "queued"
            else:
                progress_percentage = float(live_progress.get("progress_percentage") or 12.0)
                current_operation = live_progress.get("current_operation") or (
                    "Promoviendo a producción…" if is_promote_job else "Validando filas del archivo…"
                )
                phase = live_progress.get("phase") or (
                    "promoting" if is_promote_job else "validating"
                )
            total_rows = int(live_progress.get("total_rows") or total_rows)
            processed_rows = int(live_progress.get("rows_processed") or 0)
            loaded_rows = int(live_progress.get("loaded_rows") or 0)
            rejected_count = int(live_progress.get("rejected_rows") or 0)
            chunks_processed = int(live_progress.get("chunks_processed") or chunks_processed)
            chunks_total = int(live_progress.get("chunks_total") or chunks_total)
            if is_promote_job and job_status == "PROCESSING":
                promoted = int(metadata.get("promoted_rows") or 0)
                promote_total = int(batch.records_count or total_rows or 1)
                progress_percentage = max(
                    progress_percentage,
                    min(99.0, (promoted / max(promote_total, 1)) * 100),
                )
                processed_rows = promoted
                loaded_rows = promoted
                total_rows = promote_total
                current_operation = (
                    f"Promoviendo a producción ({promoted:,} de {promote_total:,} registros)…"
                )
                phase = "promoting"
        elif active_promotion:
            promo = _apply_active_promotion_progress(
                metadata=metadata,
                batch=batch,
                live_progress=live_progress,
                final_stats=final_stats,
                job_status=job_status,
            )
            progress_percentage = promo["progress_percentage"]
            current_operation = promo["current_operation"]
            phase = promo["phase"]
            total_rows = promo["total_rows"]
            processed_rows = promo["processed_rows"]
            loaded_rows = promo["loaded_rows"]
            rejected_count = promo["rejected_count"]
            chunks_processed = promo["chunks_processed"]
            chunks_total = promo["chunks_total"]
        elif status == "COMPLETED":
            progress_percentage = 100
            current_operation = "Validación completada"
            phase = "done"
            loaded_rows = int(final_stats.get("total_inserted") or batch.records_count or 0)
            rejected_count = int(final_stats.get("total_rejected") or 0)
            processed_rows = loaded_rows + rejected_count
            if not total_rows:
                total_rows = processed_rows
        elif status == "PROMOTED":
            progress_percentage = 100
            promoted_inserted = int(metadata.get("promoted_inserted") or 0)
            promoted_updated = int(metadata.get("promoted_updated") or 0)
            loaded_rows = int(metadata.get("promoted_rows") or batch.records_count or 0)
            current_operation = _format_promotion_summary(promoted_inserted, promoted_updated)
            phase = "done"
            rejected_count = int(final_stats.get("total_rejected") or 0)
            processed_rows = loaded_rows
            total_rows = loaded_rows
        elif status == "FAILED":
            progress_percentage = 0
            current_operation = f"Error: {error_message or batch.error_message or 'Proceso fallido'}"
            phase = "failed"
        else:
            progress_percentage = float(live_progress.get("progress_percentage") or 0)
            current_operation = live_progress.get("current_operation") or current_operation
            phase = live_progress.get("phase") or phase

        if status == "COMPLETED" and processed_rows == 0 and batch.records_count and not active_promotion:
            loaded_rows = int(batch.records_count)
            rejected_count = int(final_stats.get("total_rejected") or rejected_count)
            processed_rows = loaded_rows + rejected_count

        is_successful = status in ("COMPLETED", "PROMOTED")

        promoted_inserted = int(metadata.get("promoted_inserted") or 0)
        promoted_updated = int(metadata.get("promoted_updated") or 0)

        return {
            "batch_id": batch_id,
            "status": status,
            "job_id": job_id,
            "job_status": job_status,
            "job_type": job_type,
            "is_successful": is_successful,
            "progress_percentage": round(progress_percentage, 1),
            "phase": phase,
            "current_operation": current_operation,
            "total_rows": total_rows,
            "processed_rows": processed_rows,
            "loaded_rows": loaded_rows,
            "rejected_rows": rejected_count,
            "promoted_inserted": promoted_inserted,
            "promoted_updated": promoted_updated,
            "records_count": int(batch.records_count or 0),
            "promotion_summary": _format_promotion_summary(promoted_inserted, promoted_updated)
            if status == "PROMOTED"
            else None,
            "chunks_processed": chunks_processed,
            "chunks_total": chunks_total,
            "target_schema": metadata.get("target_schema"),
            "target_table": metadata.get("target_table"),
            "staging_table": batch.source_name,
            "started_at": batch.started_at.isoformat() if batch.started_at else None,
            "completed_at": batch.completed_at.isoformat() if batch.completed_at else None,
            "error_message": error_message or batch.error_message,
            "direct_load": metadata.get("direct_load", False),
            "auto_production": metadata.get("auto_production", False),
            "progress_updated_at": live_progress.get("updated_at"),
            "validation_complete": bool(metadata.get("validation_complete")),
            "validation_in_progress": validation_in_progress,
            "validation_job_active": _validation_job_active(db, batch_id),
            "promotion_job_active": _promotion_job_active(db, batch_id),
            "promotion_timing_ms": metadata.get("promotion_timing_ms"),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting progress: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get progress: {str(e)}")



# --- Promotion Endpoints ---

@router.post("/staging/promote/{batch_id}")
async def promote_batch(
    batch_id: str,
    db: Session = Depends(get_db_session)
):
    """
    Trigger promotion of a batch to production.
    """
    try:
        # 1. Validate batch exists and is ready
        batch = db.execute(
            text(
                "SELECT status, metadata, records_count FROM staging_meta.batch_control "
                "WHERE batch_id = :batch_id"
            ),
            {"batch_id": batch_id},
        ).fetchone()
        
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")

        metadata = batch.metadata
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        target_schema = metadata.get("target_schema")
        target_table = metadata.get("target_table")

        if batch.status == "PROMOTED":
            return {
                "message": "El batch ya fue promovido a producción",
                "status": "PROMOTED",
                "target": f"{target_schema}.{target_table}" if target_schema and target_table else None,
            }

        # Allow promotion if COMPLETED (processed to staging) or FAILED promotion (retry)
        if batch.status not in ['COMPLETED', 'FAILED']:
             # Strict check: only allow if it passed staging processing
             pass 
        
        if not target_schema or not target_table:
             raise HTTPException(status_code=400, detail="Target schema/table not defined for this batch")

        # 2. Check if a promotion job is already running
        existing_job = db.execute(text("""
            SELECT job_id FROM staging_meta.job_queue 
            WHERE job_type = 'PROMOTE_BATCH' 
            AND status IN ('PENDING', 'PROCESSING')
            AND payload::jsonb ->> 'batch_id' = :batch_id
        """), {"batch_id": batch_id}).fetchone()
        
        if existing_job:
            return JSONResponse(
                status_code=202,
                content={"message": "Promotion already in progress", "job_id": existing_job.job_id}
            )

        # 3. Create Promotion Job
        # Clear previous error message if retrying; reset live progress for Step 4 UI
        final_stats = metadata.get("processing_stats", {}) or {}
        promote_total = int(
            final_stats.get("total_inserted") or batch.records_count or 0
        )
        rows_already_promoted = int(metadata.get("promoted_rows") or 0)
        metadata["processing_progress"] = _initial_promotion_progress(
            promote_total=promote_total,
            rows_processed=rows_already_promoted,
            queued=True,
        )

        db.execute(text("""
            UPDATE staging_meta.batch_control
            SET error_message = NULL,
                metadata = :metadata,
                updated_at = CURRENT_TIMESTAMP
            WHERE batch_id = :batch_id
        """), {"batch_id": batch_id, "metadata": json.dumps(metadata)})
        db.commit()

        from data_staging.workers.job_queue import create_job as enqueue_job

        job_id = enqueue_job(
            database_url=str(settings.DATABASE_URL),
            job_type="PROMOTE_BATCH",
            payload={
                "batch_id": batch_id,
                "target_schema": target_schema,
                "target_table": target_table,
                "dedup_columns": metadata.get("dedup_columns", []),
            },
            priority=10,
        )
        
        return {
            "message": "Promotion job queued",
            "job_id": job_id,
            "target": f"{target_schema}.{target_table}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering promotion: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/staging/promote/{batch_id}/resume")
async def resume_promotion(
    batch_id: str,
    db: Session = Depends(get_db_session)
):
    """
    Resume a batch promotion that failed mid-flight and is in PARTIALLY_PROMOTED state.
    """
    try:
        # 1. Validate batch exists and is ready
        batch = db.execute(text("SELECT status, metadata FROM staging_meta.batch_control WHERE batch_id = :batch_id"), {"batch_id": batch_id}).fetchone()
        
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
            
        # specifically allow PARTIALLY_PROMOTED or FAILED
        if batch.status not in ['PARTIALLY_PROMOTED', 'FAILED']:
             raise HTTPException(status_code=400, detail=f"Cannot resume a batch in '{batch.status}' status. Must be PARTIALLY_PROMOTED or FAILED.")
        
        metadata = batch.metadata
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
            
        target_schema = metadata.get("target_schema")
        target_table = metadata.get("target_table")
        
        if not target_schema or not target_table:
             raise HTTPException(status_code=400, detail="Target schema/table not defined for this batch")

        # 2. Check if a promotion job is already running
        existing_job = db.execute(text("""
            SELECT job_id FROM staging_meta.job_queue 
            WHERE job_type = 'PROMOTE_BATCH' 
            AND status IN ('PENDING', 'PROCESSING')
            AND payload::jsonb ->> 'batch_id' = :batch_id
        """), {"batch_id": batch_id}).fetchone()
        
        if existing_job:
            return JSONResponse(
                status_code=202,
                content={"message": "Promotion already in progress", "job_id": existing_job.job_id}
            )

        # 3. Create Promotion Job
        # Clear previous error message if retrying
        db.execute(text("""
            UPDATE staging_meta.batch_control
            SET error_message = NULL,
                status = 'PROCESSING',
                started_at = COALESCE(started_at, CURRENT_TIMESTAMP),
                updated_at = CURRENT_TIMESTAMP
            WHERE batch_id = :batch_id
        """), {"batch_id": batch_id})
        db.commit()

        from data_staging.workers.job_queue import create_job as enqueue_job

        job_id = enqueue_job(
            database_url=str(settings.DATABASE_URL),
            job_type="PROMOTE_BATCH",
            payload={
                "batch_id": batch_id,
                "target_schema": target_schema,
                "target_table": target_table,
                "dedup_columns": metadata.get("dedup_columns", []),
            },
            priority=10,
        )
        
        return {
            "message": "Resume promotion job queued",
            "job_id": job_id,
            "target": f"{target_schema}.{target_table}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resuming promotion: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch/{batch_id}/cancel")
async def cancel_batch(
    batch_id: str,
    db: Session = Depends(get_db_session),
):
    """Cancel a batch and stop pending/processing background jobs."""
    try:
        batch = db.execute(
            text("SELECT batch_id, status FROM staging_meta.batch_control WHERE batch_id = :batch_id"),
            {"batch_id": batch_id},
        ).fetchone()

        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")

        if batch.status in ("PROMOTED", "CANCELLED"):
            raise HTTPException(
                status_code=400,
                detail=f"No se puede cancelar un batch en estado '{batch.status}'",
            )

        _signal_batches_cancelled(db, [batch_id])
        db.commit()

        return {"message": "Batch cancelled", "batch_id": batch_id, "status": "CANCELLED"}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error cancelling batch {batch_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/staging/batch/{batch_id}/rejected/download")
async def download_rejected_records(
    batch_id: str,
    db: Session = Depends(get_db_session),
    current_user: TokenUser = Depends(get_current_user),
):
    """
    Descarga los registros rechazados desde el archivo en disco generado durante la validación.
    No accede a ninguna tabla en BD — cero WAL, cero espacio extra en Supabase.
    """
    try:
        batch = db.execute(
            text(
                "SELECT metadata, organization_id FROM staging_meta.batch_control "
                "WHERE batch_id = :batch_id"
            ),
            {"batch_id": batch_id},
        ).fetchone()

        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")

        if batch.organization_id and batch.organization_id != current_user.organization_id:
            raise HTTPException(status_code=403, detail="No tienes acceso a este batch")

        metadata = normalize_metadata(batch.metadata)
        source_file_columns = metadata.get("source_file_columns") or []
        rejected_count = int(
            (metadata.get("processing_stats") or {}).get("total_rejected")
            or metadata.get("rejected_rows")
            or 0
        )

        from data_staging.utils.batch_staging_files import (
            REJECTED_EXPORT_ERROR_COL,
            find_rejected_records_file,
            iter_rejected_download_lines,
        )

        resolved_rejected = find_rejected_records_file(
            batch_id,
            metadata.get("rejected_temp_file"),
            metadata,
        )

        if not resolved_rejected:
            if rejected_count > 0:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        "No se encontró el archivo de rechazados en el servidor. "
                        "Regenera la vista previa (paso 3) e inténtalo de nuevo."
                    ),
                )

            async def empty_csv():
                yield "\ufeff"
                import csv as _csv
                import io as _io

                buf = _io.StringIO()
                _csv.writer(buf, delimiter=",").writerow([REJECTED_EXPORT_ERROR_COL])
                yield buf.getvalue()

            return StreamingResponse(
                empty_csv(),
                media_type="text/csv; charset=utf-8",
                headers={"Content-Disposition": f"attachment; filename=rejected_records_{batch_id}.csv"}
            )

        def stream_file():
            for line in iter_rejected_download_lines(
                resolved_rejected,
                source_file_columns=source_file_columns,
            ):
                yield line

        return StreamingResponse(
            stream_file(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename=rejected_records_{batch_id}.csv"}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading rejected records: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/staging/batch/{batch_id}/valid/download")
async def download_valid_records(
    batch_id: str,
    db: Session = Depends(get_db_session)
):
    """
    Descarga los registros válidos desde el archivo Parquet/CSV en disco.
    """
    try:
        batch = db.execute(
            text("SELECT metadata FROM staging_meta.batch_control WHERE batch_id = :batch_id"),
            {"batch_id": batch_id}
        ).fetchone()

        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")

        metadata = batch.metadata or {}
        if isinstance(metadata, str):
            import json as _json
            metadata = _json.loads(metadata)

        from data_staging.utils.batch_staging_files import (
            find_valid_records_file,
            iter_valid_download_lines,
        )

        resolved_valid = find_valid_records_file(
            batch_id, metadata.get("valid_temp_file"), metadata
        )

        if not resolved_valid or not resolved_valid.exists():
            async def empty_csv():
                yield "\ufeff"

            return StreamingResponse(
                empty_csv(),
                media_type="text/csv; charset=utf-8",
                headers={"Content-Disposition": f"attachment; filename=valid_records_{batch_id}.csv"}
            )

        def stream_file():
            for line in iter_valid_download_lines(resolved_valid):
                yield line

        return StreamingResponse(
            stream_file(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename=valid_records_{batch_id}.csv"}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading valid records: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/batch/{batch_id}")
async def delete_batch(
    batch_id: str,
    db: Session = Depends(get_db_session),
    current_user: TokenUser = Depends(get_current_user),
):
    """Elimina un batch y todos sus datos relacionados (archivo, jobs, etc.)."""
    try:
        where_clause, params = _batch_filters_where(organization_id=current_user.organization_id)
        params["batch_id"] = batch_id
        exists = db.execute(
            text(f"""
                SELECT 1 FROM staging_meta.batch_control bc
                {where_clause}{_batch_id_exists_clause(where_clause)}
            """),
            params,
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Batch not found")

        if not _delete_batch_record(db, batch_id):
            raise HTTPException(status_code=404, detail="Batch not found")
        db.commit()
        return {"status": "success", "message": f"Batch {batch_id} deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting batch {batch_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batches/bulk-delete")
async def bulk_delete_batches(
    body: BulkDeleteRequest,
    db: Session = Depends(get_db_session),
    current_user: TokenUser = Depends(get_current_user),
):
    """Elimina varios batches por ID (solo de la organización del usuario)."""
    if not body.batch_ids:
        raise HTTPException(status_code=400, detail="batch_ids vacío")

    not_found: List[str] = []
    try:
        where_clause, params = _batch_filters_where(
            organization_id=current_user.organization_id
        )
        params["ids"] = body.batch_ids
        id_clause = (
            " AND bc.batch_id::text = ANY(:ids)"
            if where_clause
            else " WHERE bc.batch_id::text = ANY(:ids)"
        )
        rows = db.execute(
            text(f"""
                SELECT bc.batch_id, bc.source_name, bc.file_path, bc.metadata
                FROM staging_meta.batch_control bc
                {where_clause}{id_clause}
            """),
            params,
        ).fetchall()
        found = {str(r.batch_id) for r in rows}
        not_found = [bid for bid in body.batch_ids if bid not in found]
        deleted = _purge_batches_bulk(db, rows)
        db.commit()
        return {
            "status": "success",
            "deleted": deleted,
            "not_found": not_found,
            "message": f"{deleted} batch(es) eliminado(s)",
        }
    except Exception as e:
        db.rollback()
        logger.error("Error bulk delete batches: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batches/delete-all")
async def delete_all_batches(
    body: BulkDeleteFiltersRequest,
    db: Session = Depends(get_db_session),
    current_user: TokenUser = Depends(get_current_user),
):
    """Elimina todos los batches que coincidan con filtros (organización del usuario)."""
    try:
        where_clause, params = _batch_filters_where(
            status=body.status,
            search=body.search,
            organization_id=current_user.organization_id,
        )
        rows = db.execute(
            text(f"""
                SELECT bc.batch_id, bc.source_name, bc.file_path, bc.metadata
                FROM staging_meta.batch_control bc
                {where_clause}
            """),
            params,
        ).fetchall()
        deleted = _purge_batches_bulk(db, rows)
        db.commit()
        return {
            "status": "success",
            "deleted": deleted,
            "message": f"{deleted} batch(es) eliminado(s)",
        }
    except Exception as e:
        db.rollback()
        logger.error("Error delete-all batches: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

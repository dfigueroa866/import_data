"""Catalog wizard pipeline: step 2 validates rows; step 3 builds preview (no aggregation)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import polars as pl
import psycopg2

from data_staging.config import settings
from data_staging.services.catalog.catalog_validation import build_catalog_validation_context
from data_staging.services.history.history_preview_pipeline import validated_intermediate_path
from data_staging.utils.batch_staging_files import rejected_records_path, valid_records_path
from data_staging.utils.json_helpers import to_json_safe
from data_staging.utils.pipeline_timing import PipelineTimer, persist_timing_metadata
from data_staging.workers.file_processor import (
    open_progress_connection,
    process_file_in_chunks,
    report_processing_progress,
)

logger = logging.getLogger(__name__)

PREVIEW_ROW_LIMIT = 20


def _clear_staging_files(batch_id: str, metadata: Optional[Dict[str, Any]] = None) -> None:
    for path in (
        rejected_records_path(batch_id, metadata),
        valid_records_path(batch_id, metadata),
        validated_intermediate_path(batch_id, metadata),
    ):
        if path.exists():
            path.unlink()


def validate_original_file_catalog(
    *,
    batch_id: str,
    file_path: Path,
    ctx,
    encoding: str,
    delimiter: str,
    conn: psycopg2.extensions.connection,
    progress_conn: Optional[psycopg2.extensions.connection] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Tuple[int, int, Path, int]:
    """Run catalog validation on all original rows. Returns valid, rejected, path, total_rows."""
    rejected_path = rejected_records_path(batch_id, metadata)
    validated_path = validated_intermediate_path(batch_id, metadata)
    _clear_staging_files(batch_id, metadata)

    progress_conn = progress_conn or conn
    validation_timer = PipelineTimer("validation")
    report_processing_progress(
        progress_conn,
        batch_id,
        progress_percentage=5,
        current_operation="Iniciando validación de mapeo…",
        phase="mapping_validating",
        force=True,
    )

    stats = process_file_in_chunks(
        conn=conn,
        file_path=file_path,
        batch_id=batch_id,
        staging_table=f"stage_{batch_id}",
        source_name=batch_id,
        column_mapping=ctx.column_mapping,
        selected_columns=ctx.selected_columns,
        target_column_types=ctx.target_column_types,
        not_null_columns=ctx.not_null_columns,
        delimiter=delimiter,
        encoding=encoding,
        direct_load=False,
        target_schema=ctx.target_schema,
        target_table=ctx.target_table,
        foreign_keys_data=ctx.foreign_keys_data,
        valid_temp_file=validated_path,
        rejected_temp_file=rejected_path,
        catalog_table=ctx.catalog_slug or None,
        composite_unique_keys=ctx.composite_unique_keys or None,
        seen_composite_keys=set(),
        source_file_columns=ctx.source_file_columns,
        history_mode=False,
        history_rules=None,
        process_type=None,
        organization_id=ctx.organization_id,
        progress_conn=progress_conn,
        pipeline_timer=validation_timer,
    )

    timing_snapshot = validation_timer.snapshot()
    persist_timing_metadata(progress_conn, batch_id, timing_snapshot)

    total_valid = int(stats.get("total_inserted") or 0)
    total_rejected = int(stats.get("total_rejected") or 0)
    total_rows = total_valid + total_rejected

    report_processing_progress(
        progress_conn,
        batch_id,
        progress_percentage=50,
        current_operation="Validación completada",
        phase="mapping_validation_done",
        total_rows=total_rows,
        rows_processed=total_rows,
        loaded_rows=total_valid,
        rejected_rows=total_rejected,
        force=True,
    )

    return total_valid, total_rejected, validated_path, total_rows


def run_catalog_validation_only(
    *,
    batch_id: str,
    file_path: str,
    column_mappings: Dict[str, Dict[str, Any]],
    column_toggles: Dict[str, bool],
    encoding: str = "utf-8",
    delimiter: str = ",",
    organization_id: str,
    metadata: Dict[str, Any],
    file_name: str = "",
) -> Dict[str, Any]:
    """Step 2: validate all catalog rows; write {batch}_validated.parquet + rejected TSV."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")

    meta = dict(metadata)
    meta["column_mappings"] = column_mappings
    meta["column_toggles"] = column_toggles
    meta["organization_id"] = organization_id
    meta["load_type"] = "catalog"

    database_url = str(settings.DATABASE_URL)
    conn = psycopg2.connect(database_url)
    progress_conn = open_progress_connection()
    try:
        cursor = conn.cursor()
        ctx = build_catalog_validation_context(
            cursor,
            metadata=meta,
            file_path=path,
            organization_id=organization_id,
        )

        valid_rows, rejected_rows, validated_path, total_rows = validate_original_file_catalog(
            batch_id=batch_id,
            file_path=path,
            ctx=ctx,
            encoding=encoding,
            delimiter=delimiter,
            conn=conn,
            progress_conn=progress_conn,
            metadata=meta,
        )

        return {
            "valid_rows": valid_rows,
            "rejected_rows": rejected_rows,
            "total_rows": total_rows,
            "validated_path": str(validated_path),
            "has_error": valid_rows == 0,
            "error_detail": (
                "Ningún registro pasó la validación."
                if valid_rows == 0
                else None
            ),
        }
    finally:
        try:
            progress_conn.close()
        except Exception:
            pass
        conn.close()


def _preview_records_from_parquet(validated_path: Path, limit: int = PREVIEW_ROW_LIMIT) -> List[Dict[str, Any]]:
    if not validated_path.is_file() or validated_path.stat().st_size == 0:
        return []
    df = pl.read_parquet(validated_path, n_rows=limit)
    if df.is_empty():
        return []
    for col in df.columns:
        if df[col].dtype in (pl.Date, pl.Datetime):
            df = df.with_columns(pl.col(col).cast(pl.Utf8))
    return to_json_safe(df.to_dicts())


def run_catalog_preview_from_validated(
    *,
    batch_id: str,
    validated_path: Path,
    valid_rows: Optional[int] = None,
    rejected_rows: Optional[int] = None,
    total_rows: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], Path]:
    """Step 3: build preview from validated parquet (no aggregation)."""
    meta = dict(metadata or {})
    stats = meta.get("processing_stats") or {}
    valid_rows = int(valid_rows if valid_rows is not None else stats.get("total_inserted") or 0)
    rejected_rows = int(
        rejected_rows if rejected_rows is not None else stats.get("total_rejected") or 0
    )
    total_rows = int(total_rows if total_rows is not None else valid_rows + rejected_rows)

    progress_conn = open_progress_connection()
    try:
        report_processing_progress(
            progress_conn,
            batch_id,
            progress_percentage=90,
            current_operation="Generando vista previa…",
            phase="preview_validating",
            total_rows=total_rows,
            rows_processed=total_rows,
            loaded_rows=valid_rows,
            rejected_rows=rejected_rows,
            force=True,
        )

        if not validated_path.is_file() or validated_path.stat().st_size == 0:
            return {
                "has_error": True,
                "error_detail": "No se encontró el archivo validado del paso 2.",
                "valid_rows": valid_rows,
                "rejected_rows": rejected_rows,
                "total_rows": total_rows,
                "grouped_rows": 0,
                "dropped_rows": 0,
                "preview_data": [],
            }, validated_path

        if valid_rows == 0:
            return {
                "has_error": True,
                "error_detail": (
                    "Ningún registro pasó la validación. "
                    "Descarga los rechazados para corregir."
                ),
                "valid_rows": 0,
                "rejected_rows": rejected_rows,
                "total_rows": total_rows,
                "grouped_rows": 0,
                "dropped_rows": 0,
                "preview_data": [],
            }, validated_path

        preview_data = _preview_records_from_parquet(validated_path)

        return {
            "has_error": False,
            "valid_rows": valid_rows,
            "rejected_rows": rejected_rows,
            "total_rows": total_rows,
            "grouped_rows": valid_rows,
            "dropped_rows": 0,
            "df_before_dropna": valid_rows,
            "df_after_dropna": valid_rows,
            "preview_data": preview_data,
        }, validated_path
    finally:
        try:
            progress_conn.close()
        except Exception:
            pass


def process_catalog_preview_with_validation(
    *,
    batch_id: str,
    file_path: str,
    column_mappings: Dict[str, Dict[str, Any]],
    column_toggles: Dict[str, bool],
    encoding: str = "utf-8",
    delimiter: str = ",",
    organization_id: str,
    metadata: Dict[str, Any],
    file_name: str = "",
) -> Tuple[Dict[str, Any], Path]:
    """Legacy: validate + preview in one pass (when step-2 validation was skipped)."""
    validation = run_catalog_validation_only(
        batch_id=batch_id,
        file_path=file_path,
        column_mappings=column_mappings,
        column_toggles=column_toggles,
        encoding=encoding,
        delimiter=delimiter,
        organization_id=organization_id,
        metadata=metadata,
        file_name=file_name,
    )
    if validation.get("has_error"):
        return {
            "has_error": True,
            "error_detail": validation.get("error_detail")
            or "Ningún registro pasó la validación. Descarga los rechazados para corregir.",
            "total_rows": validation.get("total_rows") or 0,
            "rejected_rows": validation.get("rejected_rows") or 0,
            "valid_rows": 0,
            "grouped_rows": 0,
            "dropped_rows": 0,
            "preview_data": [],
        }, Path(file_path)

    validated_path = Path(validation["validated_path"])
    return run_catalog_preview_from_validated(
        batch_id=batch_id,
        validated_path=validated_path,
        valid_rows=validation.get("valid_rows"),
        rejected_rows=validation.get("rejected_rows"),
        total_rows=validation.get("total_rows"),
        metadata=metadata,
    )

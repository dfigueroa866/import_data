"""Step 3 history preview: validate original rows, then aggregate valid rows only."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import polars as pl
import psycopg2

from data_staging.config import settings
from data_staging.services.aggregation_service import process_aggregation
from data_staging.services.history.history_validation import (
    build_history_validation_context,
    identity_wizard_mappings_for_columns,
)
from data_staging.utils.batch_staging_files import (
    get_temp_dir,
    rejected_records_path,
    valid_records_path,
)
from data_staging.utils.pipeline_timing import PipelineTimer, persist_timing_metadata
from data_staging.workers.file_processor import (
    open_progress_connection,
    process_file_in_chunks,
    report_processing_progress,
)

logger = logging.getLogger(__name__)

VALIDATED_SUFFIX = "_validated.parquet"


def validated_intermediate_path(batch_id: str) -> Path:
    return get_temp_dir() / f"{batch_id}{VALIDATED_SUFFIX}"


def _clear_staging_files(batch_id: str) -> None:
    for path in (
        rejected_records_path(batch_id),
        valid_records_path(batch_id),
        validated_intermediate_path(batch_id),
    ):
        if path.exists():
            path.unlink()


def _delete_validated_intermediate(batch_id: str) -> None:
    path = validated_intermediate_path(batch_id)
    if path.is_file():
        try:
            path.unlink()
        except OSError as exc:
            logger.warning("Could not delete validated intermediate %s: %s", path, exc)


def validate_original_file(
    *,
    batch_id: str,
    file_path: Path,
    ctx,
    encoding: str,
    delimiter: str,
    conn: psycopg2.extensions.connection,
    progress_conn: Optional[psycopg2.extensions.connection] = None,
) -> Tuple[int, int, Path, int]:
    """Run PROCESS_FILE validation on all original rows. Returns valid, rejected, path, total_rows."""
    rejected_path = rejected_records_path(batch_id)
    validated_path = validated_intermediate_path(batch_id)
    _clear_staging_files(batch_id)

    progress_conn = progress_conn or conn
    report_processing_progress(
        progress_conn,
        batch_id,
        progress_percentage=5,
        current_operation="Iniciando validación de vista previa…",
        phase="preview_validating",
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
        catalog_table=None,
        composite_unique_keys=None,
        seen_composite_keys=None,
        source_file_columns=ctx.source_file_columns,
        history_mode=True,
        process_type=ctx.process_type,
        organization_id=ctx.organization_id,
        sku_resolver=ctx.sku_resolver,
        resolve_sku_id=ctx.resolve_sku_id,
        source_extension=ctx.source_extension,
        progress_conn=progress_conn,
    )

    total_valid = int(stats.get("total_inserted") or 0)
    total_rejected = int(stats.get("total_rejected") or 0)
    total_rows = total_valid + total_rejected

    report_processing_progress(
        progress_conn,
        batch_id,
        progress_percentage=50,
        current_operation="Validación completada — agregando filas válidas…",
        phase="preview_aggregating",
        total_rows=total_rows,
        rows_processed=total_rows,
        loaded_rows=total_valid,
        rejected_rows=total_rejected,
        force=True,
    )

    return total_valid, total_rejected, validated_path, total_rows


def process_history_preview_with_validation(
    *,
    batch_id: str,
    file_path: str,
    column_mappings: Dict[str, Dict[str, Any]],
    column_toggles: Dict[str, bool],
    process_type: str,
    encoding: str = "utf-8",
    delimiter: str = ",",
    organization_id: str,
    metadata: Dict[str, Any],
    file_name: str = "",
) -> Tuple[Dict[str, Any], Path]:
    """
    Validate all original rows (worker rules), write rejected TSV, aggregate valid rows.
    Returns aggregation stats merged with validation counts.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")

    meta = dict(metadata)
    meta["column_mappings"] = column_mappings
    meta["column_toggles"] = column_toggles
    meta["organization_id"] = organization_id
    meta["process_type"] = process_type

    preview_timer = PipelineTimer("preview")
    database_url = str(settings.DATABASE_URL)
    conn = psycopg2.connect(database_url)
    progress_conn = open_progress_connection()
    try:
        cursor = conn.cursor()
        ctx = build_history_validation_context(
            cursor,
            metadata=meta,
            file_path=path,
            file_name=file_name,
            organization_id=organization_id,
        )

        with preview_timer.phase("validation_ms"):
            valid_rows, rejected_rows, validated_path, total_rows = validate_original_file(
                batch_id=batch_id,
                file_path=path,
                ctx=ctx,
                encoding=encoding,
                delimiter=delimiter,
                conn=conn,
                progress_conn=progress_conn,
            )

        if valid_rows == 0:
            return {
                "has_error": True,
                "error_detail": "Ningún registro pasó la validación. Descarga los rechazados para corregir.",
                "total_rows": total_rows,
                "rejected_rows": rejected_rows,
                "valid_rows": 0,
                "dropped_rows": 0,
                "preview_data": [],
            }, path

        if not validated_path.is_file() or validated_path.stat().st_size == 0:
            return {
                "has_error": True,
                "error_detail": "No se generó archivo de filas válidas tras la validación.",
                "total_rows": total_rows,
                "rejected_rows": rejected_rows,
                "valid_rows": valid_rows,
                "dropped_rows": 0,
                "preview_data": [],
            }, path

        schema_cols = list(pl.read_parquet(validated_path, n_rows=0).columns)
        agg_mappings, agg_toggles = identity_wizard_mappings_for_columns(schema_cols)

        agg_progress_start = 55.0
        agg_progress_end = 99.0
        chunk_size = int(getattr(settings, "AGGREGATION_CHUNK_SIZE", 500_000))
        chunks_total = max(1, (valid_rows + chunk_size - 1) // chunk_size)

        def _report_agg_progress(
            rows_done: int,
            agg_total_rows: int,
            chunk_idx: int,
            _chunks_total: int,
        ) -> None:
            fraction = rows_done / max(agg_total_rows, 1)
            pct = agg_progress_start + fraction * (agg_progress_end - agg_progress_start) * 0.85
            report_processing_progress(
                progress_conn,
                batch_id,
                progress_percentage=pct,
                current_operation=(
                    f"Agregando filas {rows_done:,} de {agg_total_rows:,} "
                    f"(bloque {chunk_idx}/{_chunks_total})…"
                ),
                phase="preview_aggregating",
                total_rows=total_rows,
                rows_processed=total_rows,
                loaded_rows=valid_rows,
                rejected_rows=rejected_rows,
                chunks_processed=chunk_idx,
                chunks_total=_chunks_total,
                force=True,
            )

        def _report_reduce_progress(step_idx: int, reduce_total: int) -> None:
            base = agg_progress_start + 0.85 * (agg_progress_end - agg_progress_start)
            span = agg_progress_end - base
            fraction = step_idx / max(reduce_total, 1)
            pct = base + span * fraction
            report_processing_progress(
                progress_conn,
                batch_id,
                progress_percentage=pct,
                current_operation=(
                    f"Consolidando grupos ({step_idx}/{reduce_total})…"
                ),
                phase="preview_aggregating",
                total_rows=total_rows,
                rows_processed=total_rows,
                loaded_rows=valid_rows,
                rejected_rows=rejected_rows,
                chunks_processed=step_idx,
                chunks_total=reduce_total,
                force=True,
            )

        def _enrich_agg_df(agg_df: pl.DataFrame) -> pl.DataFrame:
            from data_staging.services.history.history_transforms import apply_history_transforms_polars

            if agg_df.is_empty():
                return agg_df
            with preview_timer.phase("enrich_ms"):
                return apply_history_transforms_polars(
                    agg_df,
                    organization_id=organization_id,
                    process_type=process_type,
                    source_extension=ctx.source_extension,
                    sku_resolver=ctx.sku_resolver,
                    resolve_sku_id=ctx.resolve_sku_id,
                    aggregated_mode=True,
                )

        _report_agg_progress(0, valid_rows, 0, chunks_total)

        with preview_timer.phase("aggregation_ms"):
            agg_stats, agg_path = process_aggregation(
                file_path=str(validated_path),
                column_mappings=agg_mappings,
                column_toggles=agg_toggles,
                process_type=process_type,
                encoding=encoding,
                delimiter=delimiter,
                total_rows_hint=valid_rows,
                progress_callback=_report_agg_progress,
                reduce_progress_callback=_report_reduce_progress,
                df_finalizer=_enrich_agg_df,
                batch_id=batch_id,
            )

        if not agg_stats.get("has_error") and agg_path.is_file():
            with preview_timer.phase("finalize_ms"):
                _delete_validated_intermediate(batch_id)

        report_processing_progress(
            progress_conn,
            batch_id,
            progress_percentage=99,
            current_operation="Vista previa casi lista…",
            phase="preview_aggregating",
            total_rows=total_rows,
            rows_processed=total_rows,
            loaded_rows=valid_rows,
            rejected_rows=rejected_rows,
            force=True,
        )

        agg_stats["total_rows"] = total_rows
        agg_stats["rejected_rows"] = rejected_rows
        agg_stats["valid_rows"] = valid_rows
        agg_stats["dropped_rows"] = 0
        agg_stats["df_before_dropna"] = valid_rows
        agg_stats["df_after_dropna"] = valid_rows

        if agg_stats.get("has_error"):
            agg_stats["error_detail"] = agg_stats.get("error_detail") or "Error en agregación tras validación."

        persist_timing_metadata(progress_conn, batch_id, preview_timer.snapshot())
        return agg_stats, agg_path
    finally:
        try:
            progress_conn.close()
        except Exception:
            pass
        conn.close()

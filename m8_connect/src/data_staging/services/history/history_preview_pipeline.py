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
    rejected_records_path,
    valid_records_path,
)
from data_staging.utils.load_storage_paths import batch_artifact_path
from data_staging.utils.pipeline_timing import PipelineTimer, persist_timing_metadata
from data_staging.workers.file_processor import (
    open_progress_connection,
    process_file_in_chunks,
    report_processing_progress,
)

logger = logging.getLogger(__name__)

VALIDATED_SUFFIX = "_validated.parquet"


def validated_intermediate_path(batch_id: str, metadata: Optional[Dict[str, Any]] = None) -> Path:
    return batch_artifact_path(batch_id, VALIDATED_SUFFIX, metadata)


def _clear_staging_files(batch_id: str, metadata: Optional[Dict[str, Any]] = None) -> None:
    for path in (
        rejected_records_path(batch_id, metadata),
        valid_records_path(batch_id, metadata),
        validated_intermediate_path(batch_id, metadata),
    ):
        if path.exists():
            path.unlink()


def _delete_validated_intermediate(
    batch_id: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    path = validated_intermediate_path(batch_id, metadata)
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
    metadata: Optional[Dict[str, Any]] = None,
) -> Tuple[int, int, Path, int]:
    """Run PROCESS_FILE validation on all original rows. Returns valid, rejected, path, total_rows."""
    rejected_path = rejected_records_path(batch_id, metadata)
    validated_path = validated_intermediate_path(batch_id, metadata)
    _clear_staging_files(batch_id, metadata)

    progress_conn = progress_conn or conn
    from data_staging.services.history.history_config import resolve_history_rules

    history_rules = resolve_history_rules(metadata)
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
        catalog_table=None,
        composite_unique_keys=None,
        seen_composite_keys=None,
        source_file_columns=ctx.source_file_columns,
        history_mode=True,
        history_rules=history_rules,
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
        current_operation="Validación completada",
        phase="mapping_validation_done",
        total_rows=total_rows,
        rows_processed=total_rows,
        loaded_rows=total_valid,
        rejected_rows=total_rejected,
        force=True,
    )

    return total_valid, total_rejected, validated_path, total_rows


def run_history_validation_only(
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
) -> Dict[str, Any]:
    """Step 2: validate all rows; write {batch}_validated.parquet + rejected TSV."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")

    meta = dict(metadata)
    meta["column_mappings"] = column_mappings
    meta["column_toggles"] = column_toggles
    meta["organization_id"] = organization_id
    meta["process_type"] = process_type

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

        valid_rows, rejected_rows, validated_path, total_rows = validate_original_file(
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


def run_history_aggregation_from_validated(
    *,
    batch_id: str,
    validated_path: Path,
    column_mappings: Dict[str, Dict[str, Any]],
    column_toggles: Dict[str, bool],
    process_type: str,
    encoding: str = "utf-8",
    delimiter: str = ",",
    organization_id: str,
    metadata: Dict[str, Any],
    file_name: str = "",
    valid_rows: Optional[int] = None,
    rejected_rows: Optional[int] = None,
    total_rows: Optional[int] = None,
) -> Tuple[Dict[str, Any], Path]:
    """Step 3: aggregate validated parquet → agglomerated; drops validated after success."""
    meta = dict(metadata)
    meta["column_mappings"] = column_mappings
    meta["column_toggles"] = column_toggles
    meta["organization_id"] = organization_id
    meta["process_type"] = process_type

    if not validated_path.is_file() or validated_path.stat().st_size == 0:
        return {
            "has_error": True,
            "error_detail": "No se encontró el archivo validado del paso 2.",
            "valid_rows": valid_rows or 0,
            "rejected_rows": rejected_rows or 0,
            "total_rows": total_rows or 0,
            "preview_data": [],
        }, validated_path

    preview_timer = PipelineTimer("preview")
    progress_conn = open_progress_connection()
    database_url = str(settings.DATABASE_URL)
    conn = psycopg2.connect(database_url)
    try:
        cursor = conn.cursor()
        ctx = build_history_validation_context(
            cursor,
            metadata=meta,
            file_path=validated_path,
            file_name=file_name,
            organization_id=organization_id,
        )

        stats = meta.get("processing_stats") or {}
        valid_rows = int(valid_rows if valid_rows is not None else stats.get("total_inserted") or 0)
        rejected_rows = int(
            rejected_rows if rejected_rows is not None else stats.get("total_rejected") or 0
        )
        total_rows = int(total_rows if total_rows is not None else valid_rows + rejected_rows)

        schema_cols = list(pl.read_parquet(validated_path, n_rows=0).columns)
        agg_mappings, agg_toggles = identity_wizard_mappings_for_columns(schema_cols)

        agg_progress_start = 5.0
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
                current_operation=f"Consolidando grupos ({step_idx}/{reduce_total})…",
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
            from data_staging.services.history.history_config import resolve_history_rules
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
                    history_rules=resolve_history_rules(meta),
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
                metadata=meta,
            )

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
            agg_stats["error_detail"] = agg_stats.get("error_detail") or "Error en agregación."
        else:
            _delete_validated_intermediate(batch_id, meta)
            stored_validated = meta.get("validated_temp_file")
            if stored_validated:
                stored_path = Path(stored_validated)
                if (
                    stored_path.is_file()
                    and stored_path.resolve() != Path(agg_path).resolve()
                ):
                    try:
                        stored_path.unlink()
                    except OSError as exc:
                        logger.warning(
                            "Could not delete stored validated file %s: %s",
                            stored_path,
                            exc,
                        )

        persist_timing_metadata(progress_conn, batch_id, preview_timer.snapshot())
        return agg_stats, agg_path
    finally:
        try:
            progress_conn.close()
        except Exception:
            pass
        conn.close()


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
    """Legacy: validate + aggregate in one pass (used when step-2 validation was skipped)."""
    validation = run_history_validation_only(
        batch_id=batch_id,
        file_path=file_path,
        column_mappings=column_mappings,
        column_toggles=column_toggles,
        process_type=process_type,
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
            "dropped_rows": 0,
            "preview_data": [],
        }, Path(file_path)

    validated_path = Path(validation["validated_path"])
    return run_history_aggregation_from_validated(
        batch_id=batch_id,
        validated_path=validated_path,
        column_mappings=column_mappings,
        column_toggles=column_toggles,
        process_type=process_type,
        encoding=encoding,
        delimiter=delimiter,
        organization_id=organization_id,
        metadata=metadata,
        file_name=file_name,
        valid_rows=validation.get("valid_rows"),
        rejected_rows=validation.get("rejected_rows"),
        total_rows=validation.get("total_rows"),
    )

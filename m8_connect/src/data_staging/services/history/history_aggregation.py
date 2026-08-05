"""Step 3 history aggregation: group validated rows by period (weekly/monthly).

Assumes ``{batch}_validated.parquet`` already has target column names and clean types
from step 2. No remapping, type coercion, or FK validation here.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import polars as pl

from data_staging.config import settings
from data_staging.services.aggregation_service import cleanup_agg_partial_files
from data_staging.services.history.history_config import (
    date_truncate_for_process_type,
    granularity_for_process_type,
    resolve_history_rules,
)
from data_staging.utils.chunk_iterators import count_parquet_rows, iter_parquet_chunks
from data_staging.utils.load_storage_paths import resolve_batch_work_dir

logger = logging.getLogger(__name__)

PERIOD_COL = "period_start"
HISTORY_GROUP_DIMS = ["organization_id", "location_code", "sku", PERIOD_COL]
SUM_METRIC_COLS = ("quantity", "pieces", "total_price")
MEAN_METRIC_COLS = ("unit_price",)

AggProgressCallback = Callable[[int, int, int, int], None]
ReduceProgressCallback = Callable[[int, int], None]


def _agg_partial_path(batch_id: str, index: int, metadata: Any = None) -> Path:
    work_dir = resolve_batch_work_dir(metadata) if metadata else Path(settings.UPLOAD_PATH)
    return work_dir / f"{batch_id}_agg_partial_{index}.parquet"


def _history_agg_metrics(columns: List[str]) -> List[pl.Expr]:
    metrics: List[pl.Expr] = []
    for col in SUM_METRIC_COLS:
        if col in columns:
            metrics.append(pl.col(col).sum().alias(col))
    for col in MEAN_METRIC_COLS:
        if col in columns:
            metrics.append(pl.col(col).mean().alias(col))
    return metrics


def _output_path_for_validated(validated_path: Path) -> Path:
    stem = validated_path.stem
    if stem.endswith("_agglomerated"):
        return validated_path.parent / f"{stem}.parquet"
    return validated_path.parent / f"{stem}_agglomerated.parquet"


def _truncate_period_start(chunk: pl.DataFrame, truncate_interval: str) -> pl.DataFrame:
    """Agrupa por periodo: truncate sobre pl.Date ya validado en paso 2 (sin re-parsear)."""
    series = chunk.get_column(PERIOD_COL)
    if series.dtype == pl.Datetime:
        chunk = chunk.with_columns(pl.col(PERIOD_COL).dt.date().alias(PERIOD_COL))
    elif series.dtype != pl.Date:
        raise TypeError(
            f"{PERIOD_COL} debe ser Date tras la validación (paso 2); "
            f"tipo recibido: {series.dtype}"
        )
    return chunk.with_columns(
        pl.col(PERIOD_COL).dt.truncate(truncate_interval).alias(PERIOD_COL)
    )


def _preview_dicts_from_df(agg_df: pl.DataFrame) -> List[Dict[str, Any]]:
    preview_data = agg_df.head(20)
    try:
        for col in preview_data.columns:
            if preview_data[col].dtype in (pl.Date, pl.Datetime, pl.Time):
                preview_data = preview_data.with_columns(pl.col(col).cast(pl.Utf8))
        return preview_data.to_dicts() if preview_data.height else []
    except Exception:
        return []


def aggregate_validated_parquet(
    *,
    validated_path: Path,
    process_type: str,
    metadata: Optional[Dict[str, Any]] = None,
    batch_id: Optional[str] = None,
    valid_rows_hint: Optional[int] = None,
    progress_callback: Optional[AggProgressCallback] = None,
    reduce_progress_callback: Optional[ReduceProgressCallback] = None,
) -> Tuple[Dict[str, Any], Path]:
    """
    Truncate period_start (weekly/monthly), group by natural key, sum metrics.

    Map: chunk → partial group_by → parquet on disk.
    Reduce: single group_by over all partials (no incremental re-merge).
    """
    validated_path = Path(validated_path)
    output_path = _output_path_for_validated(validated_path)

    schema_cols = list(pl.read_parquet(validated_path, n_rows=0).columns)
    dims = [c for c in HISTORY_GROUP_DIMS if c in schema_cols]
    metrics = _history_agg_metrics(schema_cols)

    if PERIOD_COL not in schema_cols or "quantity" not in schema_cols:
        return {
            "has_error": True,
            "error_detail": (
                f"El archivo validado debe incluir '{PERIOD_COL}' y 'quantity'."
            ),
        }, validated_path

    if not metrics:
        return {
            "has_error": True,
            "error_detail": "No hay columnas numéricas para agregar.",
        }, validated_path

    chunk_size = int(getattr(settings, "AGGREGATION_CHUNK_SIZE", 500_000))
    valid_rows = (
        int(valid_rows_hint)
        if valid_rows_hint is not None and valid_rows_hint > 0
        else count_parquet_rows(validated_path)
    )
    chunks_total = max(1, (valid_rows + chunk_size - 1) // chunk_size)
    truncate_interval = date_truncate_for_process_type(process_type)

    if batch_id:
        cleanup_agg_partial_files(batch_id, metadata)

    partial_paths: List[Path] = []
    rows_done = 0
    chunk_idx = 0

    for chunk in iter_parquet_chunks(validated_path, chunk_size):
        if batch_id:
            from data_staging.utils.batch_cancel import raise_if_batch_cancelled

            raise_if_batch_cancelled(batch_id)

        chunk_idx += 1
        rows_done += chunk.height
        if chunk.is_empty():
            if progress_callback:
                progress_callback(rows_done, valid_rows, chunk_idx, chunks_total)
            continue

        partial = _truncate_period_start(chunk, truncate_interval).group_by(dims).agg(metrics)

        if batch_id and not partial.is_empty():
            partial_path = _agg_partial_path(batch_id, chunk_idx, metadata)
            partial.write_parquet(partial_path)
            partial_paths.append(partial_path)
        elif not partial.is_empty():
            partial_paths.append(partial)

        if progress_callback:
            progress_callback(rows_done, valid_rows, chunk_idx, chunks_total)

    if not partial_paths:
        return {
            "has_error": False,
            "total_rows": valid_rows,
            "grouped_rows": 0,
            "df_before_dropna": valid_rows,
            "df_after_dropna": valid_rows,
            "dropped_rows": 0,
            "consolidated_rows": valid_rows,
            "compression_factor": 0.0,
            "preview_data": [],
        }, output_path

    if reduce_progress_callback:
        reduce_progress_callback(0, 1)

    if len(partial_paths) == 1:
        only = partial_paths[0]
        agg_df = pl.read_parquet(only) if isinstance(only, Path) else only
    else:
        lazy_frames = [
            pl.scan_parquet(p) if isinstance(p, Path) else p.lazy()
            for p in partial_paths
        ]
        agg_df = (
            pl.concat(lazy_frames, how="diagonal_relaxed")
            .group_by(dims)
            .agg(metrics)
            .collect()
        )

    if reduce_progress_callback:
        reduce_progress_callback(1, 1)

    meta_dict = metadata if isinstance(metadata, dict) else {}
    sales_channel_default = resolve_history_rules(meta_dict).get("sales_channel_default") or "SELL_IN"
    granularity_val = granularity_for_process_type(process_type)
    source_ext = (meta_dict.get("source_extension") or "csv").strip().lower() or "csv"

    if not agg_df.is_empty():
        agg_df = agg_df.with_columns([
            pl.lit(granularity_val).alias("granularity"),
            pl.lit(source_ext).alias("source"),
            pl.lit(sales_channel_default).alias("sales_channel"),
        ])
        from data_staging.services.history.history_transforms import (
            apply_history_derived_columns_polars,
        )

        agg_df = apply_history_derived_columns_polars(agg_df)
        stored_types = meta_dict.get("target_column_types") or {}
        if stored_types:
            from data_staging.utils.parquet_typing import cast_dataframe_to_target_types

            types_without_period = {
                k: v for k, v in stored_types.items() if k != PERIOD_COL
            }
            if types_without_period:
                agg_df = cast_dataframe_to_target_types(
                    agg_df,
                    types_without_period,
                    skip_already_typed=True,
                )
        agg_df.write_parquet(output_path)

    if batch_id:
        cleanup_agg_partial_files(batch_id, metadata)

    grouped_rows = agg_df.height
    consolidated = max(0, valid_rows - grouped_rows)
    compression = round(valid_rows / grouped_rows, 2) if grouped_rows > 0 else 0.0

    return {
        "has_error": False,
        "total_rows": valid_rows,
        "grouped_rows": grouped_rows,
        "df_before_dropna": valid_rows,
        "df_after_dropna": valid_rows,
        "dropped_rows": 0,
        "consolidated_rows": consolidated,
        "compression_factor": compression,
        "preview_data": _preview_dicts_from_df(agg_df),
    }, output_path

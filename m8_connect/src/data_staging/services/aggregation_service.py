import glob
import polars as pl
from pathlib import Path
from typing import Callable, Dict, Any, Tuple, List, Optional
import datetime

from data_staging.services.catalog.catalog_transforms import coerce_period_start_to_date
from data_staging.utils.mapping_helpers import is_wizard_virtual_mapping
from data_staging.utils.encoding_utils import detect_file_encoding, encoding_for_polars
from data_staging.config import settings
from data_staging.utils.chunk_iterators import iter_csv_chunks, iter_parquet_chunks, count_csv_rows, count_parquet_rows
from data_staging.utils.batch_staging_files import get_temp_dir
from data_staging.utils.load_storage_paths import resolve_batch_work_dir

# Tolerancia global para diferencias de flotantes (como en weekly.py)
TOTAL_PRICE_TOL = 1e-6

# Columnas destino public.sales_history (nombres lógicos en agregación)
DATE_COL = "period_start"
QTY_COL = "quantity"
LOC_COL = "location_code"
SKU_COL = "sku"

_LEGACY_TARGET_ALIASES = {
    "start_date": DATE_COL,
    "qty": QTY_COL,
    "loc": LOC_COL,
    "dmd_unit": SKU_COL,
    "sku_code": SKU_COL,
}


def _apply_legacy_column_aliases(df: pl.DataFrame) -> pl.DataFrame:
    """Compatibilidad con mapeos antiguos (start_date, qty, loc, dmd_unit)."""
    renames = {
        old: new
        for old, new in _LEGACY_TARGET_ALIASES.items()
        if old in df.columns and new not in df.columns
    }
    if renames:
        df = df.rename(renames)
    return df

class AggregationError(Exception):
    pass


def _clean_chunk_types(df: pl.DataFrame) -> pl.DataFrame:
    """Clean numeric/date columns on a chunk (same rules as full-file path)."""
    for numeric_col in [QTY_COL, "unit_price", "total_price", "pieces"]:
        if numeric_col in df.columns:
            if df[numeric_col].dtype in [pl.Utf8, pl.Object]:
                df = df.with_columns(
                    pl.col(numeric_col).str.replace_all(",", "").str.strip_chars().cast(pl.Float64, strict=False)
                )
            else:
                df = df.with_columns(pl.col(numeric_col).cast(pl.Float64, strict=False))

    if DATE_COL in df.columns:
        df = coerce_period_start_to_date(df, DATE_COL)
    return df


def _build_agg_metrics(df: pl.DataFrame) -> List:
    metrics = []
    if QTY_COL in df.columns:
        metrics.append(pl.col(QTY_COL).sum().alias(QTY_COL))
    if "total_price" in df.columns:
        metrics.append(pl.col("total_price").sum().alias("total_price"))
    if "unit_price" in df.columns:
        metrics.append(pl.col("unit_price").mean().alias("unit_price"))
    if "pieces" in df.columns:
        metrics.append(pl.col("pieces").sum().alias("pieces"))
    return metrics


def _prepare_chunk_for_agg(
    df: pl.DataFrame,
    actual_rename_mapping: Dict[str, str],
    static_mappings: Dict[str, Any],
) -> pl.DataFrame:
    df = df.rename(actual_rename_mapping)
    df = _apply_legacy_column_aliases(df)
    for target_col, default_val in static_mappings.items():
        if target_col not in df.columns:
            df = df.with_columns(pl.lit(default_val).alias(target_col))
    df = _clean_chunk_types(df)
    return df


AggregationProgressCallback = Callable[[int, int, int, int], None]
AggregationReduceCallback = Callable[[int, int], None]
AggregationDfFinalizer = Callable[[pl.DataFrame], pl.DataFrame]


def _agg_spill_threshold_rows() -> int:
    return int(getattr(settings, "AGG_SPILL_THRESHOLD_ROWS", 5_000_000))


def _agg_in_memory_max_rows() -> int:
    return int(getattr(settings, "AGG_IN_MEMORY_MAX_ROWS", 10_000_000))


def _agg_acc_max_rows() -> int:
    return int(getattr(settings, "AGG_ACC_MAX_ROWS", 3_000_000))


def _should_use_agg_spill(total_rows: int) -> bool:
    return total_rows >= _agg_spill_threshold_rows()


def _agg_work_dir(metadata: Any = None) -> Path:
    if metadata:
        return resolve_batch_work_dir(metadata)
    return get_temp_dir()


def _agg_partial_glob(batch_id: str, metadata: Any = None) -> str:
    return str(_agg_work_dir(metadata) / f"{batch_id}_agg_partial_*.parquet")


def _agg_partial_path(batch_id: str, index: int, metadata: Any = None) -> Path:
    return _agg_work_dir(metadata) / f"{batch_id}_agg_partial_{index}.parquet"


def cleanup_agg_partial_files(batch_id: Optional[str], metadata: Any = None) -> None:
    if not batch_id:
        return
    for path in glob.glob(_agg_partial_glob(batch_id, metadata)):
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass


def _merge_agg_partials(acc: Optional[pl.DataFrame], partial: pl.DataFrame, dims: List[str]) -> pl.DataFrame:
    if partial.is_empty():
        return acc if acc is not None else partial
    if acc is None or acc.is_empty():
        return partial
    combined = pl.concat([acc, partial], how="diagonal_relaxed")
    metrics = _build_agg_metrics(combined)
    if metrics and dims:
        return combined.group_by(dims).agg(metrics)
    return combined


def _finalize_agg_df_from_partials(
    partial_paths: List[Path],
    group_dimensions: List[str],
    reduce_progress_callback: Optional[AggregationReduceCallback] = None,
) -> pl.DataFrame:
    if not partial_paths:
        return pl.DataFrame()
    dims = [c for c in group_dimensions if c in pl.read_parquet(partial_paths[0], n_rows=0).columns]
    metrics_exprs = _build_agg_metrics(pl.read_parquet(partial_paths[0], n_rows=0))
    if not metrics_exprs:
        return pl.concat([pl.read_parquet(p) for p in partial_paths], how="diagonal_relaxed")

    total_steps = len(partial_paths)
    if total_steps == 1:
        if reduce_progress_callback:
            reduce_progress_callback(1, 1)
        frame = pl.read_parquet(partial_paths[0])
        return frame.group_by(dims).agg(metrics_exprs) if dims else frame

    accumulator: Optional[pl.DataFrame] = None
    for step_idx, partial_path in enumerate(partial_paths, start=1):
        partial = pl.read_parquet(partial_path)
        accumulator = _merge_agg_partials(accumulator, partial, dims)
        if reduce_progress_callback:
            reduce_progress_callback(step_idx, total_steps)
    return accumulator if accumulator is not None else pl.DataFrame()


def _discover_agg_column_mappings(
    column_mappings: Dict[str, Dict[str, Any]],
    column_toggles: Dict[str, bool],
) -> Tuple[Dict[str, str], List[str], Dict[str, Any], bool, bool]:
    rename_mapping: Dict[str, str] = {}
    cols_to_keep: List[str] = []
    static_mappings: Dict[str, Any] = {}
    start_date_col = None
    qty_col = None

    for file_col, config in column_mappings.items():
        if column_toggles.get(file_col, True):
            target = config.get("target")
            if target:
                if is_wizard_virtual_mapping(file_col, config):
                    static_mappings[target] = config.get("default_value", "")
                else:
                    cols_to_keep.append(file_col)
                    rename_mapping[file_col] = target
                if target in (DATE_COL, "start_date"):
                    start_date_col = DATE_COL
                elif target in (QTY_COL, "qty"):
                    qty_col = QTY_COL

    return rename_mapping, cols_to_keep, static_mappings, bool(start_date_col), bool(qty_col)


def _build_agg_stats_payload(
    *,
    total_rows_original: int,
    rows_before_agg: int,
    grouped_rows: int,
    orig_qty: float,
    agg_qty: float,
    orig_total: float,
    agg_total: float,
    loc_diff_count: int = 0,
    dmd_unit_diff_count: int = 0,
    preview_dicts: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    diff_qty = orig_qty - agg_qty
    diff_total = orig_total - agg_total
    has_error = False
    error_detail = None

    if abs(diff_qty) > 0.001:
        has_error = True
        error_detail = f"QTY mismatch. Orig: {orig_qty}, Agg: {agg_qty}"

    consolidated_rows = rows_before_agg - grouped_rows
    compression_factor = round(rows_before_agg / grouped_rows, 2) if grouped_rows > 0 else 0.0

    return {
        "total_rows": total_rows_original,
        "grouped_rows": grouped_rows,
        "df_before_dropna": rows_before_agg,
        "df_after_dropna": rows_before_agg,
        "dropped_rows": 0,
        "consolidated_rows": consolidated_rows,
        "compression_factor": compression_factor,
        "loc_diff_count": loc_diff_count,
        "dmd_unit_diff_count": dmd_unit_diff_count,
        "orig_qty": round(orig_qty, 2),
        "agg_qty": round(agg_qty, 2),
        "orig_total": round(orig_total, 2),
        "agg_total": round(agg_total, 2),
        "diff_qty": round(diff_qty, 2),
        "diff_total": round(diff_total, 2),
        "has_warnings": False,
        "has_error": has_error,
        "error_detail": error_detail,
        "preview_data": preview_dicts or [],
    }


def _preview_dicts_from_df(agg_df: pl.DataFrame) -> List[Dict[str, Any]]:
    preview_data = agg_df.head(20)
    try:
        for col in preview_data.columns:
            if preview_data[col].dtype in [pl.Date, pl.Datetime, pl.Time]:
                preview_data = preview_data.with_columns(pl.col(col).cast(pl.Utf8))
        return preview_data.to_dicts() if preview_data.height else []
    except Exception:
        return []


def process_aggregation_streaming(
    file_path: str,
    column_mappings: Dict[str, Dict[str, Any]],
    column_toggles: Dict[str, bool],
    process_type: str,
    encoding: str = "utf-8",
    delimiter: str = ",",
    total_rows_hint: Optional[int] = None,
    progress_callback: Optional[AggregationProgressCallback] = None,
    reduce_progress_callback: Optional[AggregationReduceCallback] = None,
    df_finalizer: Optional[AggregationDfFinalizer] = None,
    batch_id: Optional[str] = None,
    metadata: Any = None,
) -> Tuple[Dict[str, Any], Path]:
    """Map-reduce aggregation by chunks (memory-bounded, spill-capable)."""
    path = Path(file_path)
    chunk_size = getattr(settings, "AGGREGATION_CHUNK_SIZE", 500_000)
    is_parquet = path.suffix.lower() == ".parquet"
    pl_encoding = encoding_for_polars(detect_file_encoding(path))

    rename_mapping, cols_to_keep, static_mappings, has_date, has_qty = _discover_agg_column_mappings(
        column_mappings, column_toggles
    )

    if not has_qty or not has_date:
        return {
            "has_error": True,
            "error_detail": (
                "Faltan columnas obligatorias para agregar: "
                f"'{DATE_COL}' y '{QTY_COL}'."
            ),
        }, path

    if is_parquet:
        total_rows_original = (
            int(total_rows_hint)
            if total_rows_hint is not None and total_rows_hint > 0
            else count_parquet_rows(path)
        )
        chunk_iter = iter_parquet_chunks(path, chunk_size)
    else:
        total_rows_original = (
            int(total_rows_hint)
            if total_rows_hint is not None and total_rows_hint > 0
            else count_csv_rows(path, delimiter, encoding)
        )
        chunk_iter = iter_csv_chunks(path, chunk_size, delimiter, encoding)

    group_dimensions = ["organization_id", LOC_COL, SKU_COL, DATE_COL]
    rows_before_agg = 0
    orig_qty = 0.0
    orig_total = 0.0
    chunks_total = max(1, (total_rows_original + chunk_size - 1) // chunk_size)
    chunk_idx = 0

    use_spill = _should_use_agg_spill(total_rows_original) or total_rows_original > _agg_in_memory_max_rows()
    if batch_id:
        cleanup_agg_partial_files(batch_id, metadata)

    accumulator: Optional[pl.DataFrame] = None
    spill_paths: List[Path] = []
    spill_index = 0

    for chunk in chunk_iter:
        if batch_id:
            from data_staging.utils.batch_cancel import raise_if_batch_cancelled

            raise_if_batch_cancelled(batch_id)
        chunk_idx += 1
        actual_cols = [c for c in cols_to_keep if c in chunk.columns]
        if actual_cols:
            chunk = chunk.select(actual_cols)
        chunk = _prepare_chunk_for_agg(chunk, rename_mapping, static_mappings)
        rows_before_agg += chunk.height
        if QTY_COL in chunk.columns:
            orig_qty += float(chunk[QTY_COL].sum())
        if "total_price" in chunk.columns:
            orig_total += float(chunk["total_price"].sum())
        if chunk.is_empty():
            if progress_callback:
                progress_callback(rows_before_agg, total_rows_original, chunk_idx, chunks_total)
            continue

        from data_staging.services.history.history_config import date_truncate_for_process_type

        truncate_interval = date_truncate_for_process_type(process_type)
        chunk = chunk.with_columns(pl.col(DATE_COL).dt.truncate(truncate_interval))
        dims = [c for c in group_dimensions if c in chunk.columns]
        metrics = _build_agg_metrics(chunk)
        if not metrics:
            if progress_callback:
                progress_callback(rows_before_agg, total_rows_original, chunk_idx, chunks_total)
            continue

        partial = chunk.group_by(dims).agg(metrics)

        if use_spill and batch_id:
            spill_index += 1
            spill_path = _agg_partial_path(batch_id, spill_index, metadata)
            partial.write_parquet(spill_path)
            spill_paths.append(spill_path)
        else:
            accumulator = _merge_agg_partials(accumulator, partial, dims)
            if (
                accumulator is not None
                and accumulator.height > _agg_acc_max_rows()
                and batch_id
            ):
                use_spill = True
                spill_index += 1
                spill_path = _agg_partial_path(batch_id, spill_index, metadata)
                accumulator.write_parquet(spill_path)
                spill_paths.append(spill_path)
                accumulator = None

        if progress_callback:
            progress_callback(rows_before_agg, total_rows_original, chunk_idx, chunks_total)

    if use_spill and spill_paths:
        if accumulator is not None and not accumulator.is_empty():
            spill_index += 1
            tail_path = _agg_partial_path(batch_id, spill_index, metadata)
            accumulator.write_parquet(tail_path)
            spill_paths.append(tail_path)
            accumulator = None
        agg_df = _finalize_agg_df_from_partials(
            spill_paths,
            group_dimensions,
            reduce_progress_callback=reduce_progress_callback,
        )
        cleanup_agg_partial_files(batch_id, metadata)
    elif accumulator is not None and not accumulator.is_empty():
        if reduce_progress_callback:
            reduce_progress_callback(1, 1)
        agg_df = accumulator
    else:
        agg_df = pl.DataFrame()

    grouped_rows = agg_df.height
    agg_qty = float(agg_df[QTY_COL].sum()) if QTY_COL in agg_df.columns and agg_df.height else 0.0
    agg_total = float(agg_df["total_price"].sum()) if "total_price" in agg_df.columns and agg_df.height else 0.0

    stem = path.stem
    output_path = path.parent / (f"{stem}.parquet" if stem.endswith("_agglomerated") else f"{stem}_agglomerated.parquet")

    if agg_df.height:
        from data_staging.services.history.history_config import (
            granularity_for_process_type,
            resolve_history_rules,
        )

        meta_dict = metadata if isinstance(metadata, dict) else {}
        sales_channel_default = resolve_history_rules(meta_dict).get("sales_channel_default") or "SELL_IN"
        granularity_val = granularity_for_process_type(process_type)
        original_ext = path.suffix.lower().lstrip(".")
        if original_ext == "parquet":
            original_ext = "csv"

        agg_df = agg_df.with_columns([
            pl.lit(granularity_val).alias("granularity"),
            pl.lit(original_ext).alias("source"),
            pl.lit(sales_channel_default).alias("sales_channel"),
        ])
        if df_finalizer:
            agg_df = df_finalizer(agg_df)
        agg_df.write_parquet(output_path)

    stats = _build_agg_stats_payload(
        total_rows_original=total_rows_original,
        rows_before_agg=rows_before_agg,
        grouped_rows=grouped_rows,
        orig_qty=orig_qty,
        agg_qty=agg_qty,
        orig_total=orig_total,
        agg_total=agg_total,
        preview_dicts=_preview_dicts_from_df(agg_df),
    )
    return stats, output_path


def process_aggregation(
    file_path: str,
    column_mappings: Dict[str, Dict[str, Any]],
    column_toggles: Dict[str, bool],
    process_type: str,
    encoding: str = "utf-8",
    delimiter: str = ",",
    total_rows_hint: Optional[int] = None,
    progress_callback: Optional[AggregationProgressCallback] = None,
    reduce_progress_callback: Optional[AggregationReduceCallback] = None,
    df_finalizer: Optional[AggregationDfFinalizer] = None,
    batch_id: Optional[str] = None,
    metadata: Any = None,
) -> Tuple[Dict[str, Any], Path]:
    """
    Procesa el archivo completo agrupándolo semanal o mensualmente.

    Args:
        file_path: Ruta al archivo CSV original cargado.
        column_mappings: Mapeos desde nombres originales hacia nombres destino.
        column_toggles: Diccionario que indica qué columnas del archivo original se mantienen activas.
        process_type: 'Weekly' o 'Monthly'.
        encoding: Codificación del archivo CSV.
        delimiter: Separador del archivo CSV.

    Returns:
        Un diccionario con los stats (filas, qty) y la ruta del archivo ya procesado (si aplica).
    """
    path = Path(file_path)
    if not path.exists():
        raise AggregationError(f"File not found: {file_path}")

    from data_staging.services.history.history_config import is_valid_process_type, valid_process_type_keys

    if not is_valid_process_type(process_type):
        valid = ", ".join(valid_process_type_keys()) or "Weekly, Monthly"
        raise AggregationError(
            f"process_type inválido: {process_type!r}. Use: {valid}"
        )

    use_streaming = getattr(settings, "AGGREGATION_CHUNK_SIZE", 500_000) > 0
    if use_streaming:
        return process_aggregation_streaming(
            file_path,
            column_mappings,
            column_toggles,
            process_type,
            encoding,
            delimiter,
            total_rows_hint=total_rows_hint,
            progress_callback=progress_callback,
            reduce_progress_callback=reduce_progress_callback,
            df_finalizer=df_finalizer,
            batch_id=batch_id,
            metadata=metadata,
        )

    pl_encoding = encoding_for_polars(detect_file_encoding(path))

    # 1. Preparar lista de columnas a leer y su mapeo al nombre final en db
    rename_mapping = {}
    cols_to_keep = []
    
    # Identificar nombres finales clave según el mapeo que hizo el usuario
    # El usuario mapea en Step 2 (ej: "FECHA" -> period_start)
    start_date_col = None
    qty_col = None
    total_price_col = None

    # Valores estáticos (fixed/custom)
    static_mappings = {}

    for file_col, config in column_mappings.items():
        if column_toggles.get(file_col, True):
            target = config.get("target")
            if target:
                if is_wizard_virtual_mapping(file_col, config):
                    static_mappings[target] = config.get("default_value", "")
                else:
                    cols_to_keep.append(file_col)
                    rename_mapping[file_col] = target
                
                if target in (DATE_COL, "start_date"):
                    start_date_col = DATE_COL
                elif target in (QTY_COL, "qty"):
                    qty_col = QTY_COL
                elif target == "total_price":
                    total_price_col = target

    # Verificar existencia mínima de columnas core para Weekly/Monthly
    if not qty_col or not start_date_col:
        return {
            "has_error": True,
            "error_detail": (
                "Faltan columnas obligatorias para agregar: "
                f"'{DATE_COL}' y '{QTY_COL}'. "
                f"Mapeadas: period_start={start_date_col}, quantity={qty_col}"
            ),
        }, path

    is_parquet = path.suffix.lower() == ".parquet"

    # Obtener cabeceras del archivo para saber si ya viene mapeado/aglomerado
    file_columns = []
    try:
        if is_parquet:
            file_columns = list(pl.read_parquet(path, n_rows=0).columns)
        else:
            file_columns = list(pl.read_csv(path, n_rows=0, separator=delimiter, encoding=pl_encoding).columns)
    except Exception:
        file_columns = []

    actual_cols_to_keep = []
    actual_rename_mapping = {}
    if file_columns:
        for file_col, target in rename_mapping.items():
            if file_col in file_columns:
                actual_cols_to_keep.append(file_col)
                actual_rename_mapping[file_col] = target
            elif target in file_columns:
                actual_cols_to_keep.append(target)
    else:
        actual_cols_to_keep = cols_to_keep
        actual_rename_mapping = rename_mapping

    # 2. Leer archivo en Polars filtrando solo las columnas de interés
    try:
        if is_parquet:
            df = pl.read_parquet(
                path,
                columns=actual_cols_to_keep,
                rechunk=True
            )
        else:
            df = pl.read_csv(
                path,
                columns=actual_cols_to_keep,
                separator=delimiter,
                encoding=pl_encoding,
                ignore_errors=True,
                truncate_ragged_lines=True,
                infer_schema_length=0,
            )
    except Exception as e:
        raise AggregationError(f"Failed to read file with Polars: {str(e)}")

    # 3. Renombrar columnas a su target e inyectar columnas estáticas
    df = df.rename(actual_rename_mapping)
    df = _apply_legacy_column_aliases(df)
    for target_col, default_val in static_mappings.items():
        if target_col not in df.columns:
            df = df.with_columns(pl.lit(default_val).alias(target_col))

    total_rows_original = df.height

    # 4. Limpieza (Clean + Types)
    try:
        for numeric_col in [QTY_COL, "unit_price", "total_price", "pieces"]:
            if numeric_col in df.columns:
                if df[numeric_col].dtype in [pl.Utf8, pl.Object]:
                    df = df.with_columns(
                        pl.col(numeric_col).str.replace_all(",", "").str.strip_chars().cast(pl.Float64, strict=False)
                    )
                else:
                    df = df.with_columns(pl.col(numeric_col).cast(pl.Float64, strict=False))

        if DATE_COL in df.columns:
            df = coerce_period_start_to_date(df, DATE_COL)
    except Exception as e:
        return {"has_error": True, "error_detail": f"Data type cleaning failed: {str(e)}"}, path

    rows_before_agg = df.height

    # Obtenemos globales previos a agrupar
    orig_qty = (
        float(df[QTY_COL].sum())
        if QTY_COL in df.columns and df[QTY_COL].dtype in pl.NUMERIC_DTYPES
        else 0.0
    )
    orig_total = float(df["total_price"].sum()) if "total_price" in df.columns and df["total_price"].dtype in pl.NUMERIC_DTYPES else 0.0

    # 6. Agrupación (Sobrescribir start_date in situ)
    # Lunes de la semana o Día 1 del mes
    from data_staging.services.history.history_config import date_truncate_for_process_type

    truncate_interval = date_truncate_for_process_type(process_type)
    df = df.with_columns(pl.col(DATE_COL).dt.truncate(truncate_interval))

    # 7. Agrupar y validar sumatorias
    metrics = []
    if QTY_COL in df.columns:
        metrics.append(pl.col(QTY_COL).sum().alias(QTY_COL))
    if "total_price" in df.columns:
        metrics.append(pl.col("total_price").sum().alias("total_price"))
    if "unit_price" in df.columns:
        metrics.append(pl.col("unit_price").mean().alias("unit_price"))
    if "pieces" in df.columns:
        metrics.append(pl.col("pieces").sum().alias("pieces"))

    group_dimensions = [c for c in ["organization_id", LOC_COL, SKU_COL, DATE_COL] if c in df.columns]

    agg_df = df.group_by(group_dimensions).agg(metrics)

    grouped_rows = agg_df.height
    agg_qty = float(agg_df[QTY_COL].sum()) if QTY_COL in agg_df.columns else 0.0
    agg_total = float(agg_df["total_price"].sum()) if "total_price" in agg_df.columns else 0.0

    diff_qty = orig_qty - agg_qty
    diff_total = orig_total - agg_total

    has_error = False
    error_detail = None
    loc_diff_count = 0
    if LOC_COL in df.columns and LOC_COL in agg_df.columns:
        df_loc = df.group_by(LOC_COL).agg([
            pl.col(QTY_COL).sum().alias("qty_orig"),
            pl.col("total_price").sum().alias("total_orig") if "total_price" in df.columns else pl.lit(0.0).alias("total_orig")
        ])
        agg_loc = agg_df.group_by(LOC_COL).agg([
            pl.col(QTY_COL).sum().alias("qty_agg"),
            pl.col("total_price").sum().alias("total_agg") if "total_price" in agg_df.columns else pl.lit(0.0).alias("total_agg")
        ])
        chk_loc = df_loc.join(agg_loc, on=LOC_COL, how="left").with_columns([
            ((pl.col("qty_orig").fill_null(0.0) - pl.col("qty_agg").fill_null(0.0)).round(4)).alias("diff_qty"),
            ((pl.col("total_orig").fill_null(0.0) - pl.col("total_agg").fill_null(0.0)).round(4)).alias("diff_total")
        ])
        bad_loc = chk_loc.filter((pl.col("diff_qty").abs() > 0.0001) | (pl.col("diff_total").abs() > TOTAL_PRICE_TOL))
        if bad_loc.height > 0:
            print("DEBUG: bad_loc found:", bad_loc.head(20).to_dicts())
        loc_diff_count = bad_loc.height

    dmd_unit_diff_count = 0
    if SKU_COL in df.columns and SKU_COL in agg_df.columns:
        df_sku = df.group_by(SKU_COL).agg([
            pl.col(QTY_COL).sum().alias("qty_orig"),
            pl.col("total_price").sum().alias("total_orig") if "total_price" in df.columns else pl.lit(0.0).alias("total_orig")
        ])
        agg_sku = agg_df.group_by(SKU_COL).agg([
            pl.col(QTY_COL).sum().alias("qty_agg"),
            pl.col("total_price").sum().alias("total_agg") if "total_price" in agg_df.columns else pl.lit(0.0).alias("total_agg")
        ])
        chk_sku = df_sku.join(agg_sku, on=SKU_COL, how="left").with_columns([
            ((pl.col("qty_orig").fill_null(0.0) - pl.col("qty_agg").fill_null(0.0)).round(4)).alias("diff_qty"),
            ((pl.col("total_orig").fill_null(0.0) - pl.col("total_agg").fill_null(0.0)).round(4)).alias("diff_total")
        ])
        bad_sku = chk_sku.filter((pl.col("diff_qty").abs() > 0.0001) | (pl.col("diff_total").abs() > TOTAL_PRICE_TOL))
        if bad_sku.height > 0:
            print("DEBUG: bad_sku found:", bad_sku.head(20).to_dicts())
        dmd_unit_diff_count = bad_sku.height

    consolidated_rows = rows_before_agg - agg_df.height
    compression_factor = round(rows_before_agg / agg_df.height, 2) if agg_df.height > 0 else 0.0

    if loc_diff_count > 0:
        has_error = True
        error_detail = f"Loc grouped differences found: {loc_diff_count} locations don't add up correctly."
    elif dmd_unit_diff_count > 0:
        has_error = True
        error_detail = f"SKU grouped differences found: {dmd_unit_diff_count} SKUs don't add up correctly."
    elif abs(diff_qty) > 0.001:
        has_error = True
        error_detail = f"QTY mismatch. Orig: {orig_qty}, Agg: {agg_qty}"
    elif "total_price" in df.columns and abs(diff_total) > TOTAL_PRICE_TOL:
        has_error = True
        error_detail = f"Total Price mismatch. Orig: {orig_total}, Agg: {agg_total}, threshold: {TOTAL_PRICE_TOL}"

    stem = path.stem
    if stem.endswith("_agglomerated"):
        output_path = path.parent / f"{stem}.parquet"
    else:
        output_path = path.parent / f"{stem}_agglomerated.parquet"

    # Inyectar columnas automáticas de historia para persistirlas en el archivo Parquet
    from data_staging.services.history.history_config import (
        granularity_for_process_type,
        resolve_history_rules,
    )

    meta_dict = metadata if isinstance(metadata, dict) else {}
    sales_channel_default = resolve_history_rules(meta_dict).get("sales_channel_default") or "SELL_IN"
    granularity_val = granularity_for_process_type(process_type)
    original_ext = path.suffix.lower().lstrip(".")
    if original_ext == "parquet":
        original_ext = "csv"

    agg_df = agg_df.with_columns([
        pl.lit(granularity_val).alias("granularity"),
        pl.lit(original_ext).alias("source"),
        pl.lit(sales_channel_default).alias("sales_channel"),
    ])

    if df_finalizer:
        agg_df = df_finalizer(agg_df)

    agg_df.write_parquet(output_path)

    preview_dicts = _preview_dicts_from_df(agg_df)

    return {
        "total_rows": total_rows_original,
        "grouped_rows": grouped_rows,
        "df_before_dropna": rows_before_agg,
        "df_after_dropna": rows_before_agg,
        "dropped_rows": 0,
        "consolidated_rows": consolidated_rows,
        "compression_factor": compression_factor,
        "loc_diff_count": loc_diff_count,
        "dmd_unit_diff_count": dmd_unit_diff_count,
        "orig_qty": round(orig_qty, 2),
        "agg_qty": round(agg_qty, 2),
        "orig_total": round(orig_total, 2),
        "agg_total": round(agg_total, 2),
        "diff_qty": round(diff_qty, 2),
        "diff_total": round(diff_total, 2),
        "has_warnings": False,
        "has_error": has_error,
        "error_detail": error_detail,
        "preview_data": preview_dicts
    }, output_path

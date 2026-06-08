import polars as pl
from pathlib import Path
from typing import Dict, Any, Tuple, List
import datetime

from data_staging.utils.mapping_helpers import is_virtual_mapping_key
from data_staging.utils.encoding_utils import detect_file_encoding, encoding_for_polars
from data_staging.config import settings
from data_staging.utils.chunk_iterators import iter_csv_chunks, iter_parquet_chunks, count_csv_rows, count_parquet_rows

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
        if df[DATE_COL].dtype == pl.Utf8:
            try:
                df = df.with_columns(pl.col(DATE_COL).str.to_datetime(strict=False).dt.date())
            except Exception:
                import pandas as pd

                parsed_dates = pd.to_datetime(df[DATE_COL].to_pandas(), errors="coerce").dt.date
                df = df.with_columns(pl.Series(DATE_COL, parsed_dates))
        elif df[DATE_COL].dtype == pl.Datetime:
            df = df.with_columns(pl.col(DATE_COL).dt.date())
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
    required_to_drop: List[str],
) -> pl.DataFrame:
    df = df.rename(actual_rename_mapping)
    df = _apply_legacy_column_aliases(df)
    for target_col, default_val in static_mappings.items():
        if target_col not in df.columns:
            df = df.with_columns(pl.lit(default_val).alias(target_col))
    df = _clean_chunk_types(df)
    subset = [c for c in required_to_drop if c in df.columns]
    if subset:
        df = df.drop_nulls(subset=subset)
    return df


def process_aggregation_streaming(
    file_path: str,
    column_mappings: Dict[str, Dict[str, Any]],
    column_toggles: Dict[str, bool],
    process_type: str,
    encoding: str = "utf-8",
    delimiter: str = ",",
) -> Tuple[Dict[str, Any], Path]:
    """Map-reduce aggregation by chunks (memory-bounded)."""
    path = Path(file_path)
    chunk_size = getattr(settings, "AGGREGATION_CHUNK_SIZE", 500_000)
    is_parquet = path.suffix.lower() == ".parquet"
    pl_encoding = encoding_for_polars(detect_file_encoding(path))

    # Reuse column discovery (wizard format: file_col -> {target: ...})
    rename_mapping = {}
    cols_to_keep = []
    start_date_col = None
    qty_col = None
    static_mappings = {}

    for file_col, config in column_mappings.items():
        if column_toggles.get(file_col, True):
            target = config.get("target")
            if target:
                if is_virtual_mapping_key(file_col):
                    static_mappings[target] = config.get("default_value", "")
                else:
                    cols_to_keep.append(file_col)
                    rename_mapping[file_col] = target
                if target in (DATE_COL, "start_date"):
                    start_date_col = DATE_COL
                elif target in (QTY_COL, "qty"):
                    qty_col = QTY_COL

    if not qty_col or not start_date_col:
        return {
            "has_error": True,
            "error_detail": (
                "Faltan columnas obligatorias para agregar: "
                f"'{DATE_COL}' y '{QTY_COL}'."
            ),
        }, path

    if is_parquet:
        total_rows_original = count_parquet_rows(path)
        chunk_iter = iter_parquet_chunks(path, chunk_size)
    else:
        total_rows_original = count_csv_rows(path, delimiter, encoding)
        chunk_iter = iter_csv_chunks(path, chunk_size, delimiter, encoding)

    required_to_drop = [DATE_COL, LOC_COL, SKU_COL, "hist_stream", QTY_COL, "dmd_group"]
    group_dimensions = ["organization_id", LOC_COL, SKU_COL, DATE_COL]
    partials: List[pl.DataFrame] = []
    df_before_dropna = 0
    orig_qty = 0.0
    orig_total = 0.0

    for chunk in chunk_iter:
        actual_cols = [c for c in cols_to_keep if c in chunk.columns]
        if actual_cols:
            chunk = chunk.select(actual_cols)
        chunk = _prepare_chunk_for_agg(chunk, rename_mapping, static_mappings, required_to_drop)
        df_before_dropna += chunk.height
        if QTY_COL in chunk.columns:
            orig_qty += float(chunk[QTY_COL].sum())
        if "total_price" in chunk.columns:
            orig_total += float(chunk["total_price"].sum())
        if chunk.is_empty():
            continue
        if process_type == "Weekly":
            chunk = chunk.with_columns(pl.col(DATE_COL).dt.truncate("1w"))
        else:
            chunk = chunk.with_columns(pl.col(DATE_COL).dt.truncate("1mo"))
        dims = [c for c in group_dimensions if c in chunk.columns]
        metrics = _build_agg_metrics(chunk)
        if metrics:
            partials.append(chunk.group_by(dims).agg(metrics))

    if not partials:
        agg_df = pl.DataFrame()
    else:
        combined = pl.concat(partials, how="diagonal_relaxed")
        dims = [c for c in group_dimensions if c in combined.columns]
        metrics = _build_agg_metrics(combined)
        agg_df = combined.group_by(dims).agg(metrics) if metrics else combined

    grouped_rows = agg_df.height
    agg_qty = float(agg_df[QTY_COL].sum()) if QTY_COL in agg_df.columns and agg_df.height else 0.0
    agg_total = float(agg_df["total_price"].sum()) if "total_price" in agg_df.columns and agg_df.height else 0.0
    diff_qty = orig_qty - agg_qty
    diff_total = orig_total - agg_total

    loc_diff_count = 0
    dmd_unit_diff_count = 0
    has_error = False
    error_detail = None

    if abs(diff_qty) > 0.001:
        has_error = True
        error_detail = f"QTY mismatch. Orig: {orig_qty}, Agg: {agg_qty}"

    stem = path.stem
    output_path = path.parent / (f"{stem}.parquet" if stem.endswith("_agglomerated") else f"{stem}_agglomerated.parquet")
    granularity_val = "week" if process_type == "Weekly" else "month"
    original_ext = path.suffix.lower().lstrip(".")
    if original_ext == "parquet":
        original_ext = "csv"

    if agg_df.height:
        agg_df = agg_df.with_columns([
            pl.lit(granularity_val).alias("granularity"),
            pl.lit(original_ext).alias("source"),
            pl.lit("SELL_IN").alias("sales_channel"),
        ])
        agg_df.write_parquet(output_path)

    preview_data = agg_df.head(20)
    try:
        for col in preview_data.columns:
            if preview_data[col].dtype in [pl.Date, pl.Datetime, pl.Time]:
                preview_data = preview_data.with_columns(pl.col(col).cast(pl.Utf8))
        preview_dicts = preview_data.to_dicts() if preview_data.height else []
    except Exception:
        preview_dicts = []

    consolidated_rows = df_before_dropna - grouped_rows
    compression_factor = round(df_before_dropna / grouped_rows, 2) if grouped_rows > 0 else 0.0

    return {
        "total_rows": total_rows_original,
        "grouped_rows": grouped_rows,
        "df_before_dropna": df_before_dropna,
        "df_after_dropna": df_before_dropna,
        "dropped_rows": total_rows_original - df_before_dropna,
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
        "preview_data": preview_dicts,
    }, output_path


def process_aggregation(
    file_path: str,
    column_mappings: Dict[str, Dict[str, Any]],
    column_toggles: Dict[str, bool],
    process_type: str,
    encoding: str = "utf-8",
    delimiter: str = ","
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

    if process_type not in ("Weekly", "Monthly"):
        raise AggregationError(
            f"process_type debe ser Weekly o Monthly (recibido: {process_type!r})"
        )

    use_streaming = getattr(settings, "AGGREGATION_CHUNK_SIZE", 500_000) > 0
    if use_streaming:
        return process_aggregation_streaming(
            file_path, column_mappings, column_toggles, process_type, encoding, delimiter
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
                if is_virtual_mapping_key(file_col):
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
        }

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
            if df[DATE_COL].dtype == pl.Utf8:
                try:
                    df = df.with_columns(
                        pl.col(DATE_COL).str.to_datetime(strict=False).dt.date()
                    )
                except Exception:
                    import pandas as pd

                    parsed_dates = pd.to_datetime(df[DATE_COL].to_pandas(), errors="coerce").dt.date
                    df = df.with_columns(pl.Series(DATE_COL, parsed_dates))
            elif df[DATE_COL].dtype == pl.Datetime:
                df = df.with_columns(pl.col(DATE_COL).dt.date())
    except Exception as e:
        return {"has_error": True, "error_detail": f"Data type cleaning failed: {str(e)}"}, path

    required_to_drop = [
        c
        for c in [DATE_COL, LOC_COL, SKU_COL, "hist_stream", QTY_COL, "dmd_group"]
        if c in df.columns
    ]
    
    print(f"DEBUG: Rows before drop_nulls: {df.height}")
    df_before_dropna = df.height
    df = df.drop_nulls(subset=required_to_drop)
    df_after_dropna = df.height
    dropped_rows = df_before_dropna - df_after_dropna
    print(f"DEBUG: Rows after dropping required_to_drop {required_to_drop}: {df_after_dropna}, Dropped: {dropped_rows}")

    # Obtenemos globales previos a agrupar
    orig_qty = (
        float(df[QTY_COL].sum())
        if QTY_COL in df.columns and df[QTY_COL].dtype in pl.NUMERIC_DTYPES
        else 0.0
    )
    orig_total = float(df["total_price"].sum()) if "total_price" in df.columns and df["total_price"].dtype in pl.NUMERIC_DTYPES else 0.0

    # 6. Agrupación (Sobrescribir start_date in situ)
    # Lunes de la semana o Día 1 del mes
    if process_type == "Weekly":
        df = df.with_columns(pl.col(DATE_COL).dt.truncate("1w"))
    else:
        df = df.with_columns(pl.col(DATE_COL).dt.truncate("1mo"))

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

    print(f"DEBUG: Original df height: {total_rows_original}. Aggregated df height: {agg_df.height}")

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

    consolidated_rows = df_after_dropna - agg_df.height
    compression_factor = round(df_after_dropna / agg_df.height, 2) if agg_df.height > 0 else 0.0

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
    granularity_val = "week" if process_type == "Weekly" else "month"
    original_ext = path.suffix.lower().lstrip(".")
    if original_ext == "parquet":
        original_ext = "csv"

    agg_df = agg_df.with_columns([
        pl.lit(granularity_val).alias("granularity"),
        pl.lit(original_ext).alias("source"),
        pl.lit("SELL_IN").alias("sales_channel")
    ])

    agg_df.write_parquet(output_path)

    preview_data = agg_df.head(20)

    # Cast dates and time for JSON serialization
    try:
        if preview_data.height > 0:
            for col in preview_data.columns:
                if preview_data[col].dtype in [pl.Date, pl.Datetime, pl.Time]:
                    preview_data = preview_data.with_columns(pl.col(col).cast(pl.Utf8))
            preview_dicts = preview_data.to_dicts()
        else:
            preview_dicts = []
    except Exception as e:
        print(f"Error casting preview data types: {e}")
        preview_dicts = []

    return {
        "total_rows": total_rows_original,
        "grouped_rows": grouped_rows,
        "df_before_dropna": df_before_dropna,
        "df_after_dropna": df_after_dropna,
        "dropped_rows": dropped_rows,
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

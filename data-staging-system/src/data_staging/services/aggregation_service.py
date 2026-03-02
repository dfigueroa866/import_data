import polars as pl
from pathlib import Path
from typing import Dict, Any, Tuple
import datetime

# Tolerancia global para diferencias de flotantes (como en weekly.py)
TOTAL_PRICE_TOL = 1e-6

class AggregationError(Exception):
    pass

def process_aggregation(
    file_path: str,
    column_mappings: Dict[str, Dict[str, Any]],
    column_toggles: Dict[str, bool],
    process_type: str,
    encoding: str = "utf-8",
    delimiter: str = ","
) -> Tuple[Dict[str, Any], Path]:
    """
    Procesa el archivo completo agrupándolo semanal o mensualmente, o simplemente retorna 
    estadísticas vacías si el proceso es 'Other'.

    Args:
        file_path: Ruta al archivo CSV original cargado.
        column_mappings: Mapeos desde nombres originales hacia nombres destino.
        column_toggles: Diccionario que indica qué columnas del archivo original se mantienen activas.
        process_type: 'Weekly', 'Monthly' u 'Other'.
        encoding: Codificación del archivo CSV.
        delimiter: Separador del archivo CSV.

    Returns:
        Un diccionario con los stats (filas, qty) y la ruta del archivo ya procesado (si aplica).
    """
    path = Path(file_path)
    if not path.exists():
        raise AggregationError(f"File not found: {file_path}")

    # 1. Preparar lista de columnas a leer y su mapeo al nombre final en db
    rename_mapping = {}
    cols_to_keep = []
    
    # Identificar nombres finales clave según el mapeo que hizo el usuario
    # El usuario mapea en Step 2 (ej: "FECHA" -> "start_date")
    start_date_col = None
    qty_col = None
    total_price_col = None

    # Valores estáticos (fixed/custom)
    static_mappings = {}

    for file_col, config in column_mappings.items():
        if column_toggles.get(file_col, True):
            target = config.get("target")
            if target:
                if file_col.startswith("__custom"):
                    static_mappings[target] = config.get("default_value", "")
                else:
                    cols_to_keep.append(file_col)
                    rename_mapping[file_col] = target
                
                if target == "start_date":
                    start_date_col = target
                elif target == "qty":
                    qty_col = target
                elif target == "total_price":
                    total_price_col = target

    # Verificar existencia mínima de columnas core para Weekly/Monthly
    if not qty_col or not start_date_col:
        # Faltan columnas esenciales para poder agrupar o validar sumas.
        # Fall-back gracioso o lanzar error. En este caso generamos stats de error
        return {
            "has_error": True,
            "error_detail": f"Missing required mapped columns for aggregation (need at least 'start_date' and 'qty'). Found: start_date={start_date_col}, qty={qty_col}"
        }, path

    # 2. Leer archivo en Polars filtrando solo las columnas de interés
    try:
        df = pl.read_csv(
            path, 
            columns=cols_to_keep, 
            separator=delimiter, 
            encoding=encoding,
            ignore_errors=True,
            truncate_ragged_lines=True
        )
    except Exception as e:
        raise AggregationError(f"Failed to read CSV with Polars: {str(e)}")

    # 3. Renombrar columnas a su target e inyectar columnas estáticas
    df = df.rename(rename_mapping)
    for target_col, default_val in static_mappings.items():
        df = df.with_columns(pl.lit(default_val).alias(target_col))

    total_rows_original = df.height

    # 4. Limpieza (Clean + Types) análoga a weekly.py
    # Casteo de fecha
    # Podría venir en distintos formatos, probaremos que pandas o polars la parsen
    try:
        # Reemplazos en strings numéricas
        for numeric_col in ["qty", "unit_price", "total_price"]:
            if numeric_col in df.columns:
                if df[numeric_col].dtype in [pl.Utf8, pl.Object]:
                    df = df.with_columns(
                        pl.col(numeric_col).str.replace_all(",", "").str.strip_chars().cast(pl.Float64, strict=False)
                    )
                else:
                    df = df.with_columns(pl.col(numeric_col).cast(pl.Float64, strict=False))

        # Date cast (intentando Strptime flexible o coerción automatica via read_csv o datetime parsing)
        if df["start_date"].dtype == pl.Utf8:
            try:
                # Intento inicial nativo de Polars
                df = df.with_columns(
                     pl.col("start_date").str.to_datetime(strict=False).dt.date()
                )
            except Exception:
                # Fallback garantizado a Pandas (idéntico a weekly.py)
                import pandas as pd
                parsed_dates = pd.to_datetime(df["start_date"].to_pandas(), errors="coerce").dt.date
                df = df.with_columns(pl.Series("start_date", parsed_dates))
        elif df["start_date"].dtype == pl.Datetime:
             df = df.with_columns(pl.col("start_date").dt.date())
    except Exception as e:
         return {"has_error": True, "error_detail": f"Data type cleaning failed: {str(e)}"}, path

    # 5. Drop NA en columnas restrictas
    # En weekly.py: required = ["start_date", "loc", "dmd_unit", "hist_stream", "qty", "dmd_group"]
    # Dependeremos estrictamente de lo que exista mapeado
    required_to_drop = [c for c in ["start_date", "loc", "dmd_unit", "hist_stream", "qty", "dmd_group"] if c in df.columns]
    
    print(f"DEBUG: Rows before drop_nulls: {df.height}")
    df_before_dropna = df.height
    df = df.drop_nulls(subset=required_to_drop)
    df_after_dropna = df.height
    dropped_rows = df_before_dropna - df_after_dropna
    print(f"DEBUG: Rows after dropping required_to_drop {required_to_drop}: {df_after_dropna}, Dropped: {dropped_rows}")

    # Obtenemos globales previos a agrupar
    print(f"DEBUG: Qty logic check - target exists: {'qty' in df.columns}, dtype: {df['qty'].dtype if 'qty' in df.columns else 'N/A'}")
    
    orig_qty = float(df["qty"].sum()) if "qty" in df.columns and df["qty"].dtype in pl.NUMERIC_DTYPES else 0.0
    orig_total = float(df["total_price"].sum()) if "total_price" in df.columns and df["total_price"].dtype in pl.NUMERIC_DTYPES else 0.0

    # 6. Agrupación (Sobrescribir start_date in situ)
    # Lunes de la semana o Día 1 del mes
    if process_type == "Weekly":
        # Polars: truncate("1w") corta al lunes de la semana
        df = df.with_columns(
            pl.col("start_date").dt.truncate("1w")
        )
    elif process_type == "Monthly":
        # Polars: truncate("1mo") corta al inicio del mes
        df = df.with_columns(
            pl.col("start_date").dt.truncate("1mo")
        )

    # 7. Ejecutar '.agg()' solo si aplica
    if process_type in ["Weekly", "Monthly"]:
        metrics = []
        if "qty" in df.columns:
            metrics.append(pl.col("qty").sum().alias("qty"))
        if "total_price" in df.columns:
            metrics.append(pl.col("total_price").sum().alias("total_price"))
        if "unit_price" in df.columns:
            metrics.append(pl.col("unit_price").mean().alias("unit_price"))

        all_cols = set(df.columns)
        metric_cols = {"qty", "total_price", "unit_price"}
        group_dimensions = list(all_cols - metric_cols)

        agg_df = df.group_by(group_dimensions).agg(metrics)
        
        print(f"DEBUG: Original df height: {total_rows_original}. Aggregated df height: {agg_df.height}")
        
        grouped_rows = agg_df.height
        agg_qty = float(agg_df["qty"].sum()) if "qty" in agg_df.columns else 0.0
        agg_total = float(agg_df["total_price"].sum()) if "total_price" in agg_df.columns else 0.0

        diff_qty = orig_qty - agg_qty
        diff_total = orig_total - agg_total

        has_error = False
        error_detail = None
        # Validations 2 & 3 (Group by LOC and DMD_UNIT logic from weekly.py)
        loc_diff_count = 0
        if "loc" in df.columns and "loc" in agg_df.columns:
            df_loc = df.group_by("loc").agg([
                pl.col("qty").sum().alias("qty_orig"),
                pl.col("total_price").sum().alias("total_orig") if "total_price" in df.columns else pl.lit(0.0).alias("total_orig")
            ])
            agg_loc = agg_df.group_by("loc").agg([
                pl.col("qty").sum().alias("qty_agg"),
                pl.col("total_price").sum().alias("total_agg") if "total_price" in agg_df.columns else pl.lit(0.0).alias("total_agg")
            ])
            chk_loc = df_loc.join(agg_loc, on="loc", how="left").with_columns([
                ((pl.col("qty_orig").fill_null(0.0) - pl.col("qty_agg").fill_null(0.0)).round(4)).alias("diff_qty"),
                ((pl.col("total_orig").fill_null(0.0) - pl.col("total_agg").fill_null(0.0)).round(4)).alias("diff_total")
            ])
            bad_loc = chk_loc.filter((pl.col("diff_qty").abs() > 0.0001) | (pl.col("diff_total").abs() > TOTAL_PRICE_TOL))
            if bad_loc.height > 0:
                print("DEBUG: bad_loc found:", bad_loc.head(20).to_dicts())
            loc_diff_count = bad_loc.height

        dmd_unit_diff_count = 0
        if "dmd_unit" in df.columns and "dmd_unit" in agg_df.columns:
            df_sku = df.group_by("dmd_unit").agg([
                pl.col("qty").sum().alias("qty_orig"),
                pl.col("total_price").sum().alias("total_orig") if "total_price" in df.columns else pl.lit(0.0).alias("total_orig")
            ])
            agg_sku = agg_df.group_by("dmd_unit").agg([
                pl.col("qty").sum().alias("qty_agg"),
                pl.col("total_price").sum().alias("total_agg") if "total_price" in agg_df.columns else pl.lit(0.0).alias("total_agg")
            ])
            chk_sku = df_sku.join(agg_sku, on="dmd_unit", how="left").with_columns([
                ((pl.col("qty_orig").fill_null(0.0) - pl.col("qty_agg").fill_null(0.0)).round(4)).alias("diff_qty"),
                ((pl.col("total_orig").fill_null(0.0) - pl.col("total_agg").fill_null(0.0)).round(4)).alias("diff_total")
            ])
            bad_sku = chk_sku.filter((pl.col("diff_qty").abs() > 0.0001) | (pl.col("diff_total").abs() > TOTAL_PRICE_TOL))
            if bad_sku.height > 0:
                print("DEBUG: bad_sku found:", bad_sku.head(20).to_dicts())
            dmd_unit_diff_count = bad_sku.height

        consolidated_rows = df_after_dropna - agg_df.height
        compression_factor = round(df_after_dropna / agg_df.height, 2) if agg_df.height > 0 else 0.0

        # Tolerancias Globales
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

        # Guardar archivo sobreescrito localmente para el staging insert
        output_path = path.parent / f"{path.stem}_agglomerated.csv"
        agg_df.write_csv(output_path, separator=",")
        
        preview_data = agg_df.head(20)

    else:
        # Modo 'Other'
        grouped_rows = 0
        orig_qty = 0.0
        agg_qty = 0.0
        orig_total = 0.0
        agg_total = 0.0
        diff_qty = 0.0
        diff_total = 0.0
        loc_diff_count = 0
        dmd_unit_diff_count = 0
        consolidated_rows = 0
        compression_factor = 1.0
        has_error = False
        error_detail = None
        output_path = path
        
        preview_data = df.head(20)

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

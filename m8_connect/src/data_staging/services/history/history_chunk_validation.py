"""Pipeline delgado de validación por chunk para historia (paso 2)."""

from __future__ import annotations

import json
from contextlib import nullcontext
from typing import Any, Dict, List, Optional, Tuple

import polars as pl

from data_staging.services.catalog.catalog_transforms import sanitize_row_dict
from data_staging.services.history.history_transforms import apply_history_transforms_polars
from data_staging.utils.mapping_helpers import (
    apply_chunk_column_mapping,
    is_chunk_already_mapped,
)
from data_staging.utils.pipeline_timing import PipelineTimer
from data_staging.utils.vectorized_validation import (
    ChunkValidationResult,
    _append_error,
    _is_empty_expr,
    _source_row_from_mapped,
)

# Solo estas columnas necesitan coerción de tipo en paso 2 (el resto viene tipado o auto-relleno)
_HISTORY_TYPED_COLUMNS = ("period_start", "quantity", "pieces")
_HISTORY_PERIOD_START_FORMAT = "%Y-%m-%d"


def _fk_lookup_list(fk_data: Dict[str, set], set_key: str, list_key: str) -> List[str]:
    cached = fk_data.get(list_key)
    if cached is not None:
        return cached
    return list(fk_data.get(set_key) or set())


def _fk_norm_expr(col: str) -> pl.Expr:
    return (
        pl.col(col)
        .cast(pl.Utf8, strict=False)
        .str.strip_chars()
        .str.replace(r"\.0$", "")
        .str.to_lowercase()
    )


def _apply_error_rule(
    df: pl.DataFrame,
    condition: pl.Expr,
    message: pl.Expr | str,
) -> pl.DataFrame:
    """Materializa _errors tras cada regla (evita árbol expr anidado lento)."""
    return df.with_columns(
        _append_error(pl.col("_errors"), condition, message).alias("_errors")
    )


def _apply_fk_rule_join(
    df: pl.DataFrame,
    col: str,
    valid_values: List[str],
    message: pl.Expr | str,
) -> pl.DataFrame:
    """FK via left join (más rápido que is_in con listas grandes)."""
    if not valid_values:
        fail = ~_is_empty_expr(col)
        return _apply_error_rule(df, fail, message)
    norm_col = f"__fk_{col}"
    val_col = f"__v_{col}"
    hit_col = f"__hit_{col}"
    df = df.with_columns(_fk_norm_expr(col).alias(norm_col))
    lookup = (
        pl.DataFrame({val_col: valid_values})
        .unique()
        .with_columns(pl.lit(True).alias(hit_col))
    )
    df = df.join(lookup, left_on=norm_col, right_on=val_col, how="left")
    fail = ~_is_empty_expr(col) & pl.col(hit_col).is_null()
    df = _apply_error_rule(df, fail, message)
    drop_cols = [c for c in (norm_col, val_col, hit_col) if c in df.columns]
    return df.drop(drop_cols)


def validate_history_chunk(
    chunk_df: pl.DataFrame,
    *,
    batch_id: str,
    chunk_idx: int,
    chunk_size: int,
    column_mapping: Optional[Dict[str, Any]] = None,
    selected_columns: Optional[List[str]] = None,
    target_column_types: Optional[Dict[str, str]] = None,
    not_null_columns: Optional[Dict[str, bool]] = None,
    foreign_keys_data: Optional[Dict[str, set]] = None,
    history_rules: Optional[Dict[str, Any]] = None,
    organization_id: Optional[str] = None,
    process_type: Optional[str] = None,
    source_extension: Optional[str] = None,
    sku_resolver=None,
    resolve_sku_id: bool = False,
    pipeline_timer: Optional[PipelineTimer] = None,
) -> ChunkValidationResult:
    """Mapeo → transforms historia → validación vectorizada (sin ramas catalog/legacy)."""
    if chunk_df.is_empty():
        return ChunkValidationResult(pl.DataFrame(), [], 0.0)

    timer = pipeline_timer
    phase = timer.phase if timer else lambda _n: nullcontext()

    with phase("mapping_ms"):
        if not is_chunk_already_mapped(chunk_df, column_mapping):
            chunk_df = apply_chunk_column_mapping(
                chunk_df,
                column_mapping=column_mapping,
                selected_columns=selected_columns,
            )
        elif column_mapping:
            missing_defaults: List[Tuple[str, Any]] = []
            for target_col, map_info in column_mapping.items():
                if target_col in chunk_df.columns:
                    continue
                default_val = map_info.get("default")
                if (
                    map_info.get("source") is None
                    and default_val is not None
                    and str(default_val).strip() != ""
                ):
                    missing_defaults.append((target_col, default_val))
            if missing_defaults:
                chunk_df = chunk_df.with_columns(
                    [pl.lit(val).alias(col) for col, val in missing_defaults]
                )
            target_cols = [c for c in column_mapping if c in chunk_df.columns]
            if target_cols:
                chunk_df = chunk_df.select(target_cols)

    with phase("transform_ms"):
        chunk_df = apply_history_transforms_polars(
            chunk_df,
            organization_id=organization_id or "",
            process_type=process_type,
            source_extension=source_extension,
            sku_resolver=sku_resolver if resolve_sku_id else None,
            resolve_sku_id=resolve_sku_id,
            history_rules=history_rules,
            fast_validation=True,
        )

    with phase("validate_ms"):
        return validate_history_chunk_vectorized(
            chunk_df,
            batch_id=batch_id,
            chunk_idx=chunk_idx,
            chunk_size=chunk_size,
            column_mapping=column_mapping,
            target_column_types=target_column_types,
            foreign_keys_data=foreign_keys_data,
            history_rules=history_rules,
        )


def _coerce_date_column(
    df: pl.DataFrame,
    col_name: str,
    empty_cond: pl.Expr,
) -> pl.DataFrame:
    """Historia: period_start debe ser YYYY-MM-DD; rechaza solo valores no vacíos inválidos."""
    col_series = df.get_column(col_name)
    if col_series.dtype == pl.Date:
        return df
    if col_series.dtype == pl.Datetime:
        return df.with_columns(pl.col(col_name).dt.date().alias(col_name))

    parsed_col = f"__parsed_{col_name}"
    text = pl.col(col_name).cast(pl.Utf8, strict=False).str.strip_chars()
    parsed_expr = text.str.strptime(pl.Date, _HISTORY_PERIOD_START_FORMAT, strict=False)
    df = df.with_columns(parsed_expr.alias(parsed_col))
    parsed_dt = pl.col(parsed_col)
    date_fail = ~empty_cond & parsed_dt.is_null()
    df = df.with_columns(
        _append_error(
            pl.col("_errors"),
            date_fail,
            pl.format(
                "Invalid date format for '{}': expected YYYY-MM-DD, got '{}'",
                pl.lit(col_name),
                pl.col(col_name),
            ),
        ).alias("_errors")
    )
    normalized = (
        pl.when(empty_cond)
        .then(pl.lit(None, dtype=pl.Date))
        .when(parsed_dt.is_not_null())
        .then(parsed_dt)
        .otherwise(pl.lit(None, dtype=pl.Date))
    )
    return df.with_columns(normalized.alias(col_name)).drop(parsed_col)


def _validate_numeric_column(
    df: pl.DataFrame,
    col_name: str,
    empty_cond: pl.Expr,
) -> pl.DataFrame:
    col_series = df.get_column(col_name)
    if col_series.dtype in pl.NUMERIC_DTYPES:
        num_fail = ~empty_cond & col_series.cast(pl.Float64, strict=False).is_null()
    else:
        numeric = (
            pl.col(col_name)
            .cast(pl.Utf8, strict=False)
            .str.strip_chars()
            .str.replace_all(r"[\$,]", "")
            .str.strip_chars()
        )
        num_fail = ~empty_cond & (
            (numeric.str.len_chars() == 0)
            | numeric.cast(pl.Float64, strict=False).is_null()
        )
    return df.with_columns(
        _append_error(
            pl.col("_errors"),
            num_fail,
            pl.format(
                "Invalid format for '{}': expected number, got '{}'",
                pl.lit(col_name),
                pl.col(col_name),
            ),
        ).alias("_errors")
    )


def validate_history_chunk_vectorized(
    chunk_df: pl.DataFrame,
    *,
    batch_id: str,
    chunk_idx: int,
    chunk_size: int,
    column_mapping: Optional[Dict[str, Any]] = None,
    target_column_types: Optional[Dict[str, str]] = None,
    not_null_columns: Optional[Dict[str, bool]] = None,
    foreign_keys_data: Optional[Dict[str, set]] = None,
    history_rules: Optional[Dict[str, Any]] = None,
) -> ChunkValidationResult:
    """Validación history-only: pocas pasadas Polars, sin checks redundantes del schema completo."""
    if chunk_df.is_empty():
        return ChunkValidationResult(pl.DataFrame(), [], 0.0)

    df = chunk_df.with_row_count("_vec_row_idx").with_columns(
        pl.lit("").alias("_errors")
    )
    total_cols = len([c for c in df.columns if not str(c).startswith("_")])
    start_row_num = (chunk_idx * chunk_size) + 1
    fk_data = foreign_keys_data or {}

    from data_staging.services.history.history_config import (
        resolve_history_rules,
        sku_columns_for_validation,
    )

    rules = history_rules or resolve_history_rules()
    required_cols = list(rules.get("required_mapping_columns") or [])
    sku_check_cols = sku_columns_for_validation(rules)

    type_cols = _HISTORY_TYPED_COLUMNS
    if target_column_types:
        type_cols = tuple(
            c for c in _HISTORY_TYPED_COLUMNS if c in target_column_types and c in df.columns
        )

    for col_name in type_cols:
        if col_name not in df.columns:
            continue
        empty_cond = _is_empty_expr(col_name)
        target_type_l = (target_column_types or {}).get(col_name, "").lower()
        if "date" in target_type_l or col_name == "period_start":
            df = _coerce_date_column(df, col_name, empty_cond)
        elif any(t in target_type_l for t in ("int", "numeric", "float", "double")) or col_name in (
            "quantity",
            "pieces",
        ):
            df = _validate_numeric_column(df, col_name, empty_cond)

    sku_present = [k for k in sku_check_cols if k in df.columns]
    if sku_present:
        has_sku = pl.any_horizontal([~_is_empty_expr(k) for k in sku_present])
        df = _apply_error_rule(
            df,
            ~has_sku,
            "Falta código de producto (mapea sku o sku_code)",
        )

    present_required = [r for r in required_cols if r in df.columns]
    if present_required:
        any_req_empty = pl.any_horizontal([_is_empty_expr(r) for r in present_required])
        req_msg = (
            pl.concat_str(
                [
                    pl.when(_is_empty_expr(r))
                    .then(pl.lit(f"Campo obligatorio vacío: {r}"))
                    .otherwise(pl.lit(""))
                    for r in present_required
                ],
                separator="; ",
            )
            .str.replace_all(r"(?:; )+", "; ")
            .str.strip_chars("; ")
        )
        df = _apply_error_rule(df, any_req_empty, req_msg)

    org_scoped_fk = bool(fk_data.get("__fk_org_scoped__"))
    valid_skus = _fk_lookup_list(fk_data, "__valid_skus__", "__valid_skus_list__")
    if "sku" in df.columns and org_scoped_fk:
        df = _apply_fk_rule_join(
            df,
            "sku",
            valid_skus,
            pl.format(
                "El SKU '{}' no existe en la tabla de productos (skus.code) de la organización",
                pl.col("sku"),
            ),
        )

    valid_locs = _fk_lookup_list(fk_data, "__valid_locations__", "__valid_locations_list__")
    if "location_code" in df.columns and org_scoped_fk:
        df = _apply_fk_rule_join(
            df,
            "location_code",
            valid_locs,
            pl.format(
                "La locación '{}' no existe en la tabla de ubicaciones (locations.code) de la organización",
                pl.col("location_code"),
            ),
        )

    df = df.with_columns((pl.col("_errors").str.len_chars() > 0).alias("_failed"))

    failed_records: List[Dict[str, Any]] = []
    drop_cols = ["_vec_row_idx", "_errors", "_failed"]

    if df["_failed"].any():
        for raw_row in df.filter(pl.col("_failed")).to_dicts():
            vec_idx = int(raw_row.get("_vec_row_idx", 0))
            row = sanitize_row_dict(raw_row)
            for key in drop_cols:
                row.pop(key, None)
            source_file_row = (
                _source_row_from_mapped(row, column_mapping) if column_mapping else {}
            )
            error_text = str(raw_row.get("_errors") or "")
            error_list = (
                [e.strip() for e in error_text.split(";") if e.strip()] if error_text else []
            )
            null_count = sum(1 for v in row.values() if v is None)
            quality_score = 100.0 - (null_count * 100.0 / total_cols) if total_cols > 0 else 100.0
            failed_records.append(
                {
                    "batch_id": batch_id,
                    "source_row_number": start_row_num + vec_idx,
                    "source_file_data": json.dumps(source_file_row, default=str),
                    "raw_data": json.dumps(row, default=str),
                    "processed_data": json.dumps(row, default=str),
                    "validation_status": "FAILED",
                    "data_quality_score": quality_score,
                    "is_duplicate": False,
                    "error_details": json.dumps({"errors": error_list}),
                }
            )

    passed_df = df.filter(~pl.col("_failed")).drop(drop_cols)

    if passed_df.height > 0:
        null_row = passed_df.null_count().row(0)
        null_counts = sum(null_row) if null_row else 0
        avg_quality = 100.0 - (
            null_counts * 100.0 / (passed_df.height * max(total_cols, 1))
        )
    else:
        avg_quality = 0.0

    return ChunkValidationResult(
        passed_df=passed_df,
        failed_records=failed_records,
        avg_quality=float(avg_quality),
    )

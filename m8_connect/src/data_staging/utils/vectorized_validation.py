"""Vectorized validation (Polars) with parity to validate_and_prepare_chunk."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Union

import polars as pl

from data_staging.services.catalog.catalog_transforms import (
    format_date_for_storage,
    is_empty_value,
    parse_flexible_datetime,
    sanitize_row_dict,
)
from data_staging.config import settings

INVALID_CHARS_REGEX = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")


@dataclass
class ChunkValidationResult:
    """Fast-path output: passed rows as DataFrame, failed as legacy record dicts."""

    passed_df: pl.DataFrame
    failed_records: List[Dict[str, Any]]
    avg_quality: float


def use_vectorized_validation() -> bool:
    return bool(getattr(settings, "USE_VECTORIZED_VALIDATION", True))


def _is_empty_expr(col: str) -> pl.Expr:
    c = pl.col(col)
    return c.is_null() | (c.cast(pl.Utf8, strict=False).str.strip_chars() == "")


def _append_error(current: pl.Expr, condition: pl.Expr, message: pl.Expr | str) -> pl.Expr:
    msg = pl.lit(message) if isinstance(message, str) else message
    return (
        pl.when(condition)
        .then(
            pl.when(current.str.len_chars() == 0)
            .then(msg)
            .otherwise(current + pl.lit("; ") + msg)
        )
        .otherwise(current)
    )


def _normalize_fk_series(values: pl.Series) -> pl.Series:
    return (
        values.cast(pl.Utf8, strict=False)
        .str.strip_chars()
        .str.replace(r"\.0$", "")
        .str.to_lowercase()
    )


def _resolve_row_column_name(columns: List[str], col: str) -> Optional[str]:
    if col in columns:
        return col
    lower_map = {str(c).lower(): c for c in columns}
    return lower_map.get(str(col).lower())


def _resolve_composite_key(row: Dict[str, Any], unique_keys: List[str]) -> Optional[tuple]:
    parts: List[str] = []
    for key in unique_keys:
        col = _resolve_row_column_name(list(row.keys()), key)
        if col is None:
            return None
        val = row.get(col)
        if is_empty_value(val):
            return None
        parts.append(str(val).strip())
    return tuple(parts)


def _source_row_from_mapped(
    row: Dict[str, Any], column_mapping: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    if not column_mapping:
        return {}
    source_file_row: Dict[str, Any] = {}
    for target_col, val in row.items():
        mapped_info = column_mapping.get(target_col)
        if mapped_info and mapped_info.get("source"):
            source_file_row[mapped_info["source"]] = val
        else:
            source_file_row[target_col] = val
    return source_file_row


def _normalize_date_column(df: pl.DataFrame, col_name: str, target_type: str) -> pl.DataFrame:
    date_only = target_type.strip() == "date" or (
        "date" in target_type and "timestamp" not in target_type
    )

    def _norm(val: Any) -> Any:
        if is_empty_value(val):
            return val
        parsed = parse_flexible_datetime(val)
        if not parsed:
            return val
        normalized = format_date_for_storage(parsed, date_only=date_only)
        return normalized if normalized is not None else val

    return df.with_columns(
        pl.col(col_name)
        .map_elements(_norm, return_dtype=pl.Utf8)
        .alias(col_name)
    )


def validate_chunk_vectorized(
    chunk_df: pl.DataFrame,
    batch_id: str,
    chunk_idx: int,
    chunk_size: int,
    column_mapping: Optional[Dict] = None,
    target_column_types: Optional[Dict[str, str]] = None,
    not_null_columns: Optional[Dict[str, bool]] = None,
    foreign_keys_data: Optional[Dict[str, set]] = None,
    history_mode: bool = False,
    original_rows: Optional[List[Dict[str, Any]]] = None,
    catalog_table: Optional[str] = None,
    composite_unique_keys: Optional[List[str]] = None,
    seen_composite_keys: Optional[set] = None,
) -> ChunkValidationResult:
    """Vectorized validation for history/catalog chunks."""
    if chunk_df.is_empty():
        return ChunkValidationResult(pl.DataFrame(), [], 0.0)

    df = chunk_df
    total_cols = len(df.columns)
    start_row_num = (chunk_idx * chunk_size) + 1
    fk_data = foreign_keys_data or {}
    valid_skus: Set[str] = fk_data.get("__valid_skus__", set())
    valid_locs: Set[str] = fk_data.get("__valid_locations__", set())

    for col in df.columns:
        if df[col].dtype in (pl.Date, pl.Datetime, pl.Time):
            df = df.with_columns(pl.col(col).cast(pl.Utf8))

    df = df.with_row_count("_vec_row_idx")
    df = df.with_columns(pl.lit("").alias("_errors"))

    if target_column_types:
        for col_name, target_type in target_column_types.items():
            if col_name not in df.columns:
                continue
            target_type_l = target_type.lower()
            is_not_null = (not_null_columns or {}).get(col_name, False)
            has_fk = bool(fk_data and col_name in fk_data)

            empty_cond = _is_empty_expr(col_name)
            if is_not_null or has_fk:
                df = df.with_columns(
                    _append_error(
                        pl.col("_errors"),
                        empty_cond,
                        f"Empty value not allowed for '{col_name}' (Database NOT NULL constraint or Foreign Key)",
                    ).alias("_errors")
                )

            if has_fk:
                fk_set = fk_data[col_name]
                fk_vals = (
                    pl.col(col_name)
                    .cast(pl.Utf8, strict=False)
                    .str.strip_chars()
                    .str.replace(r"\.0$", "")
                )
                fk_fail = ~empty_cond & ~fk_vals.is_in(list(fk_set))
                df = df.with_columns(
                    _append_error(
                        pl.col("_errors"),
                        fk_fail,
                        pl.format(
                            "Foreign Key violation for '{}': '{}' not found in target table lookup",
                            pl.lit(col_name),
                            pl.col(col_name),
                        ),
                    ).alias("_errors")
                )

            if any(t in target_type_l for t in ("int", "numeric", "float", "double")):
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
                df = df.with_columns(
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

            elif "date" in target_type_l or "time" in target_type_l:
                raw_date = pl.col(col_name).cast(pl.Utf8, strict=False).str.strip_chars()
                parsed_dt = raw_date.str.to_datetime(strict=False, time_unit="us")
                date_fail = ~empty_cond & parsed_dt.is_null()
                df = df.with_columns(
                    _append_error(
                        pl.col("_errors"),
                        date_fail,
                        pl.format(
                            "Invalid date format for '{}': got '{}'",
                            pl.lit(col_name),
                            pl.col(col_name),
                        ),
                    ).alias("_errors")
                )
                if target_type_l.strip() == "date" or (
                    "date" in target_type_l and "timestamp" not in target_type_l
                ):
                    normalized = (
                        pl.when(empty_cond)
                        .then(pl.col(col_name))
                        .when(parsed_dt.is_not_null())
                        .then(parsed_dt.dt.strftime("%Y-%m-%d"))
                        .otherwise(pl.col(col_name))
                    )
                else:
                    normalized = (
                        pl.when(empty_cond)
                        .then(pl.col(col_name))
                        .when(parsed_dt.is_not_null())
                        .then(parsed_dt.dt.strftime("%Y-%m-%d %H:%M:%S"))
                        .otherwise(pl.col(col_name))
                    )
                df = df.with_columns(normalized.alias(col_name))

            elif "char" in target_type_l or "text" in target_type_l:
                match = re.search(r"\((\d+)\)", target_type)
                if match:
                    max_len = int(match.group(1))
                    len_fail = ~empty_cond & (
                        pl.col(col_name).cast(pl.Utf8, strict=False).str.len_chars() > max_len
                    )
                    df = df.with_columns(
                        _append_error(
                            pl.col("_errors"),
                            len_fail,
                            pl.format(
                                "String too long for '{}': len={}, max={}",
                                pl.lit(col_name),
                                pl.col(col_name).cast(pl.Utf8, strict=False).str.len_chars(),
                                pl.lit(str(max_len)),
                            ),
                        ).alias("_errors")
                    )

    if history_mode:
        from data_staging.services.history.history_config import (
            HISTORY_REQUIRED_MAPPING_COLUMNS,
            HISTORY_SKU_MAPPING_TARGETS,
            HISTORY_SALES_CHANNEL_VALUE,
        )

        sku_present = [k for k in HISTORY_SKU_MAPPING_TARGETS if k in df.columns]
        if sku_present:
            has_sku = pl.any_horizontal([~_is_empty_expr(k) for k in sku_present])
            df = df.with_columns(
                _append_error(
                    pl.col("_errors"),
                    ~has_sku,
                    "Falta código de producto (mapea sku o sku_code)",
                ).alias("_errors")
            )

        if "sku" in (target_column_types or {}) and "sku" in df.columns:
            df = df.with_columns(
                _append_error(
                    pl.col("_errors"),
                    _is_empty_expr("sku"),
                    "Campo obligatorio vacío: sku",
                ).alias("_errors")
            )

        for req in HISTORY_REQUIRED_MAPPING_COLUMNS:
            if req in (target_column_types or {}) and req in df.columns:
                df = df.with_columns(
                    _append_error(
                        pl.col("_errors"),
                        _is_empty_expr(req),
                        f"Campo obligatorio vacío: {req}",
                    ).alias("_errors")
                )

        if "sku" in df.columns and valid_skus:
            sku_norm = _normalize_fk_series(df["sku"])
            sku_fail = ~_is_empty_expr("sku") & ~sku_norm.is_in(list(valid_skus))
            df = df.with_columns(
                _append_error(
                    pl.col("_errors"),
                    sku_fail,
                    pl.format(
                        "El SKU '{}' no existe en la tabla de productos (skus.code) de la organización",
                        pl.col("sku"),
                    ),
                ).alias("_errors")
            )

        if "location_code" in df.columns and valid_locs:
            loc_norm = _normalize_fk_series(df["location_code"])
            loc_fail = ~_is_empty_expr("location_code") & ~loc_norm.is_in(list(valid_locs))
            df = df.with_columns(
                _append_error(
                    pl.col("_errors"),
                    loc_fail,
                    pl.format(
                        "La locación '{}' no existe en la tabla de ubicaciones (locations.code) de la organización",
                        pl.col("location_code"),
                    ),
                ).alias("_errors")
                )

        if "granularity" in (target_column_types or {}) and "granularity" in df.columns:
            df = df.with_columns(
                _append_error(
                    pl.col("_errors"),
                    _is_empty_expr("granularity"),
                    "Campo obligatorio vacío: granularity",
                ).alias("_errors")
            )

        if "_sales_channel_invalid" in df.columns:
            invalid = ~pl.col("_sales_channel_invalid").is_null()
            df = df.with_columns(
                _append_error(
                    pl.col("_errors"),
                    invalid,
                    pl.format(
                        f"sales_channel debe ser '{HISTORY_SALES_CHANNEL_VALUE}' (valor en archivo: {{}})",
                        pl.col("_sales_channel_invalid"),
                    ),
                ).alias("_errors")
            )

    if catalog_table:
        from data_staging.services.catalog.catalog_registry import get_catalog_table
        from data_staging.services.catalog.catalog_transforms import validate_catalog_row_enums

        catalog_def = get_catalog_table(catalog_table)
        if catalog_def:
            for col in catalog_def.get("required_columns") or []:
                if not col or col == "organization_id":
                    continue
                resolved = _resolve_row_column_name(df.columns, col)
                if not resolved:
                    df = df.with_columns(
                        _append_error(
                            pl.col("_errors"),
                            pl.lit(True),
                            f"Columna requerida no mapeada o ausente: '{col}'",
                        ).alias("_errors")
                    )
                elif resolved in df.columns:
                    df = df.with_columns(
                        _append_error(
                            pl.col("_errors"),
                            _is_empty_expr(resolved),
                            f"Valor vacío no permitido en columna requerida '{col}'",
                        ).alias("_errors")
                    )

        rows_for_enum = df.to_dicts()
        enum_errors_col: List[str] = [""] * df.height
        for i, raw in enumerate(rows_for_enum):
            row = sanitize_row_dict(raw)
            enum_errs = validate_catalog_row_enums(row, catalog_table)
            if enum_errs:
                prefix = "; ".join(enum_errs)
                existing = enum_errors_col[i]
                enum_errors_col[i] = prefix if not existing else f"{existing}; {prefix}"
        df = df.with_columns(pl.Series("_enum_errors", enum_errors_col))
        df = df.with_columns(
            _append_error(
                pl.col("_errors"),
                pl.col("_enum_errors").str.len_chars() > 0,
                pl.col("_enum_errors"),
            ).alias("_errors")
        ).drop("_enum_errors")

    string_cols = [
        c for c in df.columns if df[c].dtype == pl.Utf8 and not str(c).startswith("_")
    ]
    if string_cols:
        for col_name in string_cols:
            if col_name == "_errors":
                continue
            bad = pl.col(col_name).str.contains(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", literal=False)
            df = df.with_columns(
                _append_error(
                    pl.col("_errors"),
                    bad,
                    f"Invalid control characters detected in '{col_name}'",
                ).alias("_errors")
            )

    df = df.with_columns((pl.col("_errors").str.len_chars() > 0).alias("_failed"))

    failed_records: List[Dict[str, Any]] = []
    drop_cols = ["_vec_row_idx", "_errors", "_failed"]
    passed_indices: Optional[List[int]] = None

    def _append_failed_record(
        raw_row: Dict[str, Any],
        vec_idx: int,
        error_list: List[str],
    ) -> None:
        row = sanitize_row_dict(raw_row)
        row.pop("_vec_row_idx", None)
        row.pop("_errors", None)
        row.pop("_failed", None)
        if "_sales_channel_invalid" in row and row.get("_sales_channel_invalid") is None:
            row.pop("_sales_channel_invalid", None)
        if original_rows is not None and vec_idx < len(original_rows):
            source_file_row = original_rows[vec_idx]
        elif column_mapping:
            source_file_row = _source_row_from_mapped(row, column_mapping)
        else:
            source_file_row = {}
        null_count = sum(1 for v in row.values() if v is None)
        quality_score = 100.0 - (null_count * 100.0 / total_cols) if total_cols > 0 else 100.0
        failed_records.append(
            {
                "batch_id": batch_id,
                "source_row_number": start_row_num + vec_idx,
                "source_file_data": json.dumps(source_file_row, default=str),
                "raw_data": json.dumps(row),
                "processed_data": json.dumps(row),
                "validation_status": "FAILED",
                "data_quality_score": quality_score,
                "is_duplicate": False,
                "error_details": json.dumps({"errors": error_list}),
            }
        )

    if composite_unique_keys and seen_composite_keys is not None:
        passed_indices = []
        for i, raw_row in enumerate(df.filter(~pl.col("_failed")).to_dicts()):
            row = sanitize_row_dict(raw_row)
            vec_idx = int(raw_row.get("_vec_row_idx", i))
            key_tuple = _resolve_composite_key(row, composite_unique_keys)
            if key_tuple is None:
                _append_failed_record(
                    raw_row,
                    vec_idx,
                    [f"Faltan columnas para clave única: {', '.join(composite_unique_keys)}"],
                )
            elif key_tuple in seen_composite_keys:
                _append_failed_record(
                    raw_row,
                    vec_idx,
                    [f"Clave duplicada en archivo ({', '.join(composite_unique_keys)})"],
                )
            else:
                seen_composite_keys.add(key_tuple)
                passed_indices.append(vec_idx)
        passed_df = df.filter(pl.col("_vec_row_idx").is_in(passed_indices))
    else:
        passed_df = df.filter(~pl.col("_failed"))

    for i, raw_row in enumerate(df.filter(pl.col("_failed")).to_dicts()):
        vec_idx = int(raw_row.get("_vec_row_idx", i))
        error_text = str(raw_row.get("_errors") or "")
        error_list = [e.strip() for e in error_text.split(";") if e.strip()] if error_text else []
        _append_failed_record(raw_row, vec_idx, error_list)

    extra_drop = [c for c in ("_sales_channel_invalid",) if c in passed_df.columns]
    passed_df = passed_df.drop(drop_cols + extra_drop)

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

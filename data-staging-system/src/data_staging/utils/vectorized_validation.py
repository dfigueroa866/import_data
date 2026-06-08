"""Vectorized validation (Polars) with parity to validate_and_prepare_chunk."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Set

import polars as pl

from data_staging.catalog.catalog_transforms import (
    format_date_for_storage,
    is_empty_value,
    parse_flexible_datetime,
    sanitize_row_dict,
)
from data_staging.config import settings

INVALID_CHARS_REGEX = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")


def use_vectorized_validation() -> bool:
    return bool(getattr(settings, "USE_VECTORIZED_VALIDATION", False))


def _is_empty_expr(col: str) -> pl.Expr:
    c = pl.col(col)
    return c.is_null() | (c.cast(pl.Utf8, strict=False).str.strip_chars() == "")


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
) -> List[Dict[str, Any]]:
    """
    Vectorized validation for history/catalog chunks.
    Returns same record dict structure as validate_and_prepare_chunk.
    """
    if chunk_df.is_empty():
        return []

    rows = chunk_df.to_dicts()
    total_cols = len(chunk_df.columns)
    start_row_num = (chunk_idx * chunk_size) + 1
    records: List[Dict[str, Any]] = []

    fk_data = foreign_keys_data or {}
    valid_skus: Set[str] = fk_data.get("__valid_skus__", set())
    valid_locs: Set[str] = fk_data.get("__valid_locations__", set())

    for i, raw_row in enumerate(rows):
        row = sanitize_row_dict(raw_row)
        source_file_row = original_rows[i] if original_rows and i < len(original_rows) else {}
        error_list: List[str] = []
        validation_status = "PASSED"

        if target_column_types:
            for col_name, value in row.items():
                if col_name not in target_column_types:
                    continue
                target_type = target_column_types[col_name].lower()
                is_not_null = (not_null_columns or {}).get(col_name, False)
                has_foreign_key = bool(fk_data and col_name in fk_data)
                is_empty = is_empty_value(value)

                if is_empty:
                    if is_not_null or has_foreign_key:
                        validation_status = "FAILED"
                        error_list.append(
                            f"Empty value not allowed for '{col_name}' (Database NOT NULL constraint or Foreign Key)"
                        )
                    continue

                if has_foreign_key:
                    val_str = str(value).strip()
                    if val_str.endswith(".0"):
                        val_str = val_str[:-2]
                    if val_str not in fk_data[col_name]:
                        validation_status = "FAILED"
                        error_list.append(
                            f"Foreign Key violation for '{col_name}': '{value}' not found in target table lookup"
                        )
                        continue

                if any(t in target_type for t in ("int", "numeric", "float", "double")):
                    try:
                        clean_val = str(value).strip().replace("$", "").replace(",", "").strip()
                        if not clean_val:
                            raise ValueError("Empty")
                        float(clean_val)
                    except (ValueError, TypeError):
                        validation_status = "FAILED"
                        error_list.append(
                            f"Invalid format for '{col_name}': expected number, got '{value}'"
                        )

                elif "date" in target_type or "time" in target_type:
                    parsed_dt = parse_flexible_datetime(value)
                    if not parsed_dt:
                        validation_status = "FAILED"
                        error_list.append(
                            f"Invalid date format for '{col_name}': got '{value}'"
                        )
                    else:
                        date_only = target_type.strip() == "date" or (
                            "date" in target_type and "timestamp" not in target_type
                        )
                        normalized = format_date_for_storage(parsed_dt, date_only=date_only)
                        if normalized is not None:
                            row[col_name] = normalized

                elif "char" in target_type or "text" in target_type:
                    match = re.search(r"\((\d+)\)", target_type)
                    if match and len(str(value)) > int(match.group(1)):
                        validation_status = "FAILED"
                        error_list.append(
                            f"String too long for '{col_name}': len={len(str(value))}, max={match.group(1)}"
                        )

        if history_mode:
            from data_staging.history.history_config import (
                HISTORY_REQUIRED_MAPPING_COLUMNS,
                HISTORY_SKU_MAPPING_TARGETS,
                HISTORY_SALES_CHANNEL_VALUE,
            )

            has_sku = any(not is_empty_value(row.get(k)) for k in HISTORY_SKU_MAPPING_TARGETS)
            if not has_sku:
                validation_status = "FAILED"
                error_list.append("Falta código de producto (mapea sku o sku_code)")
            elif "sku" in (target_column_types or {}) and is_empty_value(row.get("sku")):
                validation_status = "FAILED"
                error_list.append("Campo obligatorio vacío: sku")

            for req in HISTORY_REQUIRED_MAPPING_COLUMNS:
                if req in (target_column_types or {}) and is_empty_value(row.get(req)):
                    validation_status = "FAILED"
                    error_list.append(f"Campo obligatorio vacío: {req}")

            sku_val = row.get("sku")
            if not is_empty_value(sku_val) and valid_skus:
                sku_str = str(sku_val).strip().lower()
                if sku_str.endswith(".0"):
                    sku_str = sku_str[:-2]
                if sku_str not in valid_skus:
                    validation_status = "FAILED"
                    error_list.append(
                        f"El SKU '{sku_val}' no existe en la tabla de productos (skus.code) de la organización"
                    )

            loc_val = row.get("location_code")
            if not is_empty_value(loc_val) and valid_locs:
                loc_str = str(loc_val).strip().lower()
                if loc_str.endswith(".0"):
                    loc_str = loc_str[:-2]
                if loc_str not in valid_locs:
                    validation_status = "FAILED"
                    error_list.append(
                        f"La locación '{loc_val}' no existe en la tabla de ubicaciones (locations.code) de la organización"
                    )

            if "granularity" in (target_column_types or {}) and is_empty_value(row.get("granularity")):
                validation_status = "FAILED"
                error_list.append("Campo obligatorio vacío: granularity")

            invalid_channel = row.pop("_sales_channel_invalid", None)
            if invalid_channel is not None:
                validation_status = "FAILED"
                error_list.append(
                    f"sales_channel debe ser '{HISTORY_SALES_CHANNEL_VALUE}' "
                    f"(valor en archivo: {invalid_channel!r})"
                )

        for col_name, value in row.items():
            if isinstance(value, str) and INVALID_CHARS_REGEX.search(value):
                validation_status = "FAILED"
                error_list.append(f"Invalid control characters detected in '{col_name}'")

        null_count = sum(1 for v in row.values() if v is None)
        quality_score = 100.0 - (null_count * 100.0 / total_cols) if total_cols > 0 else 100.0
        error_details_json = json.dumps({"errors": error_list}) if error_list else None

        records.append(
            {
                "batch_id": batch_id,
                "source_row_number": start_row_num + i,
                "source_file_data": json.dumps(source_file_row, default=str),
                "raw_data": json.dumps(row),
                "processed_data": json.dumps(row),
                "validation_status": validation_status,
                "data_quality_score": quality_score,
                "is_duplicate": False,
                "error_details": error_details_json,
            }
        )

    return records

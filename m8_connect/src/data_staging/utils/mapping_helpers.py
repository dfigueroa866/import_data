"""Helpers for wizard column mapping keys (file vs virtual/fixed columns)."""

from __future__ import annotations

from typing import Any, Dict, Optional

import polars as pl


def is_virtual_mapping_key(file_col: str) -> bool:
    """True when the mapping key is not a real CSV column (custom/fixed values)."""
    if not file_col:
        return False
    return file_col.startswith("__fixed_") or file_col.startswith("__manual__")


def is_wizard_virtual_mapping(
    file_col: str,
    mapping_config: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    True for wizard rows that inject a constant target column (manual/fixed values).
    """
    if is_virtual_mapping_key(file_col):
        return True
    cfg = mapping_config if isinstance(mapping_config, dict) else {}
    if cfg.get("is_manual") or cfg.get("is_fixed"):
        return True
    default_val = cfg.get("default_value")
    if default_val is None or str(default_val).strip() == "":
        return False
    source = cfg.get("source")
    return source is None or str(source).strip() == ""


def apply_worker_mapping_defaults(
    df: pl.DataFrame,
    column_mapping: Optional[Dict[str, Dict[str, Any]]],
) -> pl.DataFrame:
    """Fill target columns from worker mapping defaults (source=None)."""
    if df.is_empty() or not column_mapping:
        return df
    out = df
    for target_col, map_info in column_mapping.items():
        if target_col in out.columns:
            continue
        if map_info.get("source") is not None:
            continue
        default_val = map_info.get("default")
        if default_val is None or str(default_val).strip() == "":
            continue
        out = out.with_columns(pl.lit(default_val).alias(target_col))
    return out


def is_chunk_already_mapped(
    chunk_df: pl.DataFrame,
    column_mapping: Optional[Dict[str, Dict[str, Any]]],
) -> bool:
    """
    True only when target column names are in place and no source file column
    still needs renaming (e.g. location -> location_code).
    """
    if not column_mapping:
        return False

    columns = set(chunk_df.columns)
    for target_col, map_info in column_mapping.items():
        source_col = map_info.get("source")
        default_val = map_info.get("default")
        has_default = default_val is not None and str(default_val).strip() != ""

        if has_default:
            continue

        if source_col and source_col in columns:
            if target_col not in columns or source_col != target_col:
                return False
        elif target_col not in columns:
            return False

    return any(target in columns for target in column_mapping)

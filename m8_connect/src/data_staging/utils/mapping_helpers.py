"""Helpers for wizard column mapping keys (file vs virtual/fixed columns)."""

from __future__ import annotations

from typing import Any, Dict, Optional

import polars as pl


def is_virtual_mapping_key(file_col: str) -> bool:
    """True when the key is not a real CSV column (custom/fixed values)."""
    if not file_col:
        return False
    return file_col.startswith("__custom") or file_col.startswith("__fixed_")


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

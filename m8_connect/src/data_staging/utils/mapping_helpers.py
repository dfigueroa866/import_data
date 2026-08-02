"""Helpers for wizard column mapping keys (file vs virtual/fixed columns)."""

from __future__ import annotations

from typing import Any, Dict, Optional

import polars as pl


METADATA_DRIVEN_FIXED_KEYS = frozenset(
    {
        "__fixed_organization_id__",
        "__fixed_granularity__",
        "__fixed_source__",
    },
)


def is_virtual_mapping_key(file_col: str) -> bool:
    """True when the mapping key is not a real CSV column (custom/fixed values)."""
    if not file_col:
        return False
    return file_col.startswith("__fixed_") or file_col.startswith("__manual__")


def is_metadata_driven_fixed_key(file_col: str) -> bool:
    """Fixed columns from login / batch metadata, not mapping default_value."""
    return file_col in METADATA_DRIVEN_FIXED_KEYS


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


def inject_session_organization_id(
    column_mapping: Optional[Dict[str, Dict[str, Any]]],
    organization_id: Optional[str],
) -> Dict[str, Dict[str, Any]]:
    """Ensure organization_id is always populated from the authenticated user's org."""
    out = dict(column_mapping or {})
    if organization_id:
        out["organization_id"] = {"source": None, "default": organization_id}
    return out


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


def apply_chunk_column_mapping(
    chunk_df: pl.DataFrame,
    *,
    column_mapping: Optional[Dict[str, Dict[str, Any]]] = None,
    selected_columns: Optional[list] = None,
) -> pl.DataFrame:
    """Filtra selected_columns y aplica column_mapping al chunk."""
    import logging

    logger = logging.getLogger(__name__)

    if chunk_df.is_empty():
        return chunk_df

    is_already_mapped = is_chunk_already_mapped(chunk_df, column_mapping)

    if selected_columns and not is_already_mapped:
        available_cols = [c for c in selected_columns if c in chunk_df.columns]
        if available_cols:
            chunk_df = chunk_df.select(available_cols)
        else:
            logger.warning("None of selected columns %s found in dataframe", selected_columns)

    if not column_mapping:
        return chunk_df

    if is_already_mapped:
        for target_col, map_info in column_mapping.items():
            if target_col not in chunk_df.columns:
                default_val = map_info.get("default")
                if (
                    map_info.get("source") is None
                    and default_val is not None
                    and str(default_val).strip() != ""
                ):
                    chunk_df = chunk_df.with_columns(pl.lit(default_val).alias(target_col))
    else:
        for target_col, map_info in column_mapping.items():
            source_col = map_info.get("source")
            default_val = map_info.get("default")

            if (
                source_col is None
                and default_val is not None
                and str(default_val).strip() != ""
            ):
                chunk_df = chunk_df.with_columns(pl.lit(default_val).alias(target_col))
            elif source_col and source_col in chunk_df.columns:
                chunk_df = chunk_df.rename({source_col: target_col})
            elif target_col in chunk_df.columns:
                pass
            elif target_col == "organization_id":
                logger.warning(
                    "organization_id has no source/default in mapping; "
                    "omitting null column (expected session injection upstream)"
                )
            else:
                # Omit unmapped targets so DB defaults can apply; do not force NULL.
                logger.debug(
                    "Omitting target column %s (no source/default in mapping)",
                    target_col,
                )

    target_cols = list(column_mapping.keys())
    available_targets = [c for c in target_cols if c in chunk_df.columns]
    if available_targets:
        chunk_df = chunk_df.select(available_targets)
    else:
        logger.error("No target columns found after mapping")

    return chunk_df

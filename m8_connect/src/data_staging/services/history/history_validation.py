"""Shared history validation context for PROCESS_FILE worker and Step 3 preview pipeline."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from data_staging.utils.mapping_helpers import (
    is_metadata_driven_fixed_key,
    is_wizard_virtual_mapping,
)

logger = logging.getLogger(__name__)


@dataclass
class HistoryValidationContext:
    column_mapping: Dict[str, Dict[str, Any]]
    selected_columns: List[str]
    source_file_columns: List[str]
    target_schema: str
    target_table: str
    target_column_types: Dict[str, str]
    not_null_columns: Dict[str, bool]
    foreign_keys_data: Dict[str, set]
    process_type: Optional[str]
    organization_id: Optional[str]
    source_extension: Optional[str]
    sku_resolver: Any = None
    resolve_sku_id: bool = False


def convert_wizard_column_mapping(
    wizard_column_mappings: Dict[str, Dict[str, Any]],
    wizard_column_toggles: Optional[Dict[str, bool]] = None,
) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    """Wizard file_col -> target format to worker target -> {source, default}."""
    column_mapping: Dict[str, Dict[str, Any]] = {}
    selected_columns: List[str] = []
    toggles = wizard_column_toggles or {}

    if wizard_column_mappings and any(
        isinstance(v, dict) and "target" in v for v in wizard_column_mappings.values()
    ):
        for file_col, mapping_config in wizard_column_mappings.items():
            if not toggles.get(file_col, True):
                continue
            target = mapping_config.get("target")
            if not target or target == "__new__":
                continue
            default_val = mapping_config.get("default_value", "")
            if is_wizard_virtual_mapping(file_col, mapping_config):
                if is_metadata_driven_fixed_key(file_col):
                    continue
                column_mapping[target] = {"source": None, "default": default_val}
            else:
                selected_columns.append(file_col)
                column_mapping[target] = {"source": file_col, "default": default_val}
    elif wizard_column_mappings:
        column_mapping = dict(wizard_column_mappings)
        selected_columns = [m.get("source") for m in column_mapping.values() if m.get("source")]

    return column_mapping, selected_columns


def build_history_validation_context(
    cursor,
    *,
    metadata: Dict[str, Any],
    file_path: Path,
    file_name: str,
    organization_id: str,
    target_column_types: Optional[Dict[str, str]] = None,
) -> HistoryValidationContext:
    """Load schema, FK sets and mapping context (same rules as process_file_job)."""
    wizard_column_mappings = metadata.get("column_mappings") or metadata.get("column_mapping") or {}
    wizard_column_toggles = metadata.get("column_toggles") or {}
    column_mapping, selected_columns = convert_wizard_column_mapping(
        wizard_column_mappings,
        wizard_column_toggles,
    )

    target_schema = metadata.get("target_schema") or "public"
    target_table = metadata.get("target_table") or "sales_history"
    process_type = metadata.get("process_type")
    source_extension = metadata.get("source_extension")

    if not source_extension:
        from data_staging.services.history.history_config import source_from_filename

        source_extension = source_from_filename(file_name or "")
        if not source_extension or source_extension == "unknown":
            source_extension = file_path.suffix.lower().lstrip(".") or "unknown"

    types = dict(target_column_types or {})
    not_null_columns: Dict[str, bool] = {}

    try:
        cursor.execute(
            """
            SELECT column_name, data_type, character_maximum_length, is_nullable
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            """,
            (target_schema, target_table),
        )
        for c_name, c_type, c_len, is_nullable in cursor.fetchall():
            full_type = f"{c_type}({c_len})" if c_len else c_type
            if c_name not in types:
                types[c_name] = full_type
            not_null_columns[c_name] = is_nullable == "NO"
    except Exception as exc:
        logger.error("Failed to query schema info: %s", exc)

    foreign_keys_data: Dict[str, set] = {}

    sku_resolver = None
    resolve_sku_id = False
    resolved_org = str(organization_id or metadata.get("organization_id") or "").strip()
    if resolved_org:
        from data_staging.services.history.history_schema import (
            create_sku_resolver,
            sales_history_needs_sku_id_resolution,
        )
        from data_staging.services.history.org_reference_data import load_org_scoped_fk_sets

        resolve_sku_id = sales_history_needs_sku_id_resolution(types, column_mapping)
        sku_resolver = create_sku_resolver(
            cursor,
            resolved_org,
            types,
            column_mapping,
        )
        if sku_resolver is not None:
            sku_resolver.preload()

        fk_sets = load_org_scoped_fk_sets(cursor, resolved_org)
        foreign_keys_data.update(fk_sets)
    else:
        logger.error("organization_id missing; SKU/location FK validation will be skipped")

    source_file_columns = list(selected_columns)
    if not source_file_columns and file_path.suffix.lower() == ".parquet":
        try:
            from data_staging.utils.chunk_iterators import parquet_column_names

            source_file_columns = parquet_column_names(file_path)
        except Exception as exc:
            logger.warning("Could not read Parquet columns for rejected export: %s", exc)

    return HistoryValidationContext(
        column_mapping=column_mapping,
        selected_columns=selected_columns,
        source_file_columns=source_file_columns,
        target_schema=target_schema,
        target_table=target_table,
        target_column_types=types,
        not_null_columns=not_null_columns,
        foreign_keys_data=foreign_keys_data,
        process_type=process_type,
        organization_id=resolved_org or organization_id,
        source_extension=source_extension,
        sku_resolver=sku_resolver,
        resolve_sku_id=resolve_sku_id,
    )


def identity_wizard_mappings_for_columns(
    columns: List[str],
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, bool]]:
    """Build wizard-style mappings when Parquet columns are already target names."""
    mappings = {col: {"target": col} for col in columns}
    toggles = {col: True for col in columns}
    return mappings, toggles

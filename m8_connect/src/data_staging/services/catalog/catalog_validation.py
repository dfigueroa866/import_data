"""Shared catalog validation context for PROCESS_FILE worker and wizard pipeline."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from data_staging.services.history.history_validation import convert_wizard_column_mapping
from data_staging.utils.mapping_helpers import inject_session_organization_id

logger = logging.getLogger(__name__)


@dataclass
class CatalogValidationContext:
    column_mapping: Dict[str, Dict[str, Any]]
    selected_columns: List[str]
    source_file_columns: List[str]
    target_schema: str
    target_table: str
    catalog_slug: str
    target_column_types: Dict[str, str]
    not_null_columns: Dict[str, bool]
    foreign_keys_data: Dict[str, set]
    organization_id: Optional[str]
    composite_unique_keys: List[str]
    config_required_columns: List[str] = field(default_factory=list)
    seen_composite_keys: Set[tuple] = field(default_factory=set)


def _resolve_catalog_db_target(metadata: Dict[str, Any]) -> Tuple[str, str, str]:
    """Return (catalog_slug, target_schema, production_table)."""
    catalog_slug = (
        metadata.get("catalog_name")
        or metadata.get("target_table")
        or ""
    )
    catalog_slug = str(catalog_slug).strip()
    target_schema = metadata.get("target_schema") or "public"
    production_table = metadata.get("production_table")
    if production_table:
        return catalog_slug, target_schema, str(production_table)

    if catalog_slug:
        from data_staging.services.catalog.catalog_registry import resolve_catalog_db_target

        schema, table = resolve_catalog_db_target(catalog_slug, target_schema)
        return catalog_slug, schema, table

    return catalog_slug, target_schema, str(metadata.get("target_table") or "")


def build_catalog_validation_context(
    cursor,
    *,
    metadata: Dict[str, Any],
    file_path: Path,
    organization_id: str,
    target_column_types: Optional[Dict[str, str]] = None,
) -> CatalogValidationContext:
    """Load schema, FK sets and mapping context (same rules as process_file_job for catalogs)."""
    wizard_column_mappings = metadata.get("column_mappings") or metadata.get("column_mapping") or {}
    wizard_column_toggles = metadata.get("column_toggles") or {}
    column_mapping, selected_columns = convert_wizard_column_mapping(
        wizard_column_mappings,
        wizard_column_toggles,
    )

    resolved_org = str(organization_id or metadata.get("organization_id") or "").strip() or None
    column_mapping = inject_session_organization_id(column_mapping, resolved_org)

    catalog_slug, target_schema, target_table = _resolve_catalog_db_target(metadata)

    types = dict(target_column_types or metadata.get("target_column_types") or {})
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
        logger.error("Failed to query catalog schema info: %s", exc)

    if target_schema and target_table:
        from data_staging.services.catalog.catalog_transforms import (
            load_db_system_managed_columns_psycopg2,
            load_db_validation_excluded_columns_psycopg2,
        )

        validation_excluded = load_db_validation_excluded_columns_psycopg2(
            cursor, target_schema, target_table
        )
        for col in validation_excluded:
            if col in not_null_columns:
                not_null_columns[col] = False

    composite_unique_keys: List[str] = []
    config_required_columns: List[str] = []
    if catalog_slug:
        from data_staging.services.catalog.catalog_registry import (
            catalog_required_targets,
            get_catalog_table,
        )

        catalog_entry = get_catalog_table(catalog_slug)
        if catalog_entry:
            composite_unique_keys = list(catalog_entry.get("unique_keys") or [])
            config_required_columns = catalog_required_targets(catalog_entry)
            # Config is the bible for null rejection (even if DB has a default).
            for col in config_required_columns:
                not_null_columns[col] = True

    foreign_keys_data: Dict[str, set] = {}
    if target_schema and target_table:
        from data_staging.services.history.org_reference_data import load_generic_fk_values

        try:
            cursor.execute(
                """
                SELECT
                    kcu.column_name,
                    ccu.table_schema AS foreign_table_schema,
                    ccu.table_name AS foreign_table_name,
                    ccu.column_name AS foreign_column_name
                FROM
                    information_schema.table_constraints AS tc
                    JOIN information_schema.key_column_usage AS kcu
                      ON tc.constraint_name = kcu.constraint_name
                     AND tc.table_schema = kcu.table_schema
                    JOIN information_schema.constraint_column_usage AS ccu
                      ON ccu.constraint_name = tc.constraint_name
                     AND ccu.table_schema = tc.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND tc.table_name = %s
                  AND tc.table_schema = %s
                """,
                (target_table, target_schema),
            )
            for col_name, f_schema, f_table, f_col in cursor.fetchall():
                try:
                    foreign_keys_data[col_name] = load_generic_fk_values(
                        cursor,
                        schema=f_schema,
                        table=f_table,
                        column=f_col,
                        organization_id=resolved_org,
                    )
                except Exception as sub_exc:
                    logger.warning("Failed to load FK values for %s: %s", col_name, sub_exc)
        except Exception as exc:
            logger.error("Failed to query foreign keys for catalog: %s", exc)

    source_file_columns = list(selected_columns)
    if not source_file_columns and file_path.suffix.lower() == ".parquet":
        try:
            from data_staging.utils.chunk_iterators import parquet_column_names

            source_file_columns = parquet_column_names(file_path)
        except Exception as exc:
            logger.warning("Could not read Parquet columns for rejected export: %s", exc)

    return CatalogValidationContext(
        column_mapping=column_mapping,
        selected_columns=selected_columns,
        source_file_columns=source_file_columns,
        target_schema=target_schema,
        target_table=target_table,
        catalog_slug=catalog_slug,
        target_column_types=types,
        not_null_columns=not_null_columns,
        foreign_keys_data=foreign_keys_data,
        organization_id=resolved_org,
        composite_unique_keys=composite_unique_keys,
        config_required_columns=config_required_columns,
    )

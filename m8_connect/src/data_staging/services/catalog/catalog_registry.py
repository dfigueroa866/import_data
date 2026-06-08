"""
Registry of catalog tables for the catalog upload flow.
Definitions are loaded from catalog_store (editable via admin UI).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from data_staging.services.catalog import catalog_store

_CONFIG_ROOT = Path(__file__).resolve().parents[3] / "config" / "catalog"


def list_catalog_tables() -> List[Dict[str, Any]]:
    """Return active catalog definitions for API and upload wizard."""
    return catalog_store.list_all_catalogs(active_only=True)


def get_catalog_table(table_name: str) -> Optional[Dict[str, Any]]:
    """Get a single catalog definition by name."""
    entry = catalog_store.get_catalog_by_name(table_name)
    if not entry or not entry.get("is_active"):
        return None
    return entry


def resolve_catalog_db_target(
    catalog_slug: str,
    target_schema: Optional[str] = None,
) -> tuple[str, str]:
    """
    Resolve physical schema/table in the database for a catalog slug.
    Falls back to catalog_slug as table name when the definition is missing.
    """
    entry = get_catalog_table(catalog_slug)
    if not entry:
        return (target_schema or "public", catalog_slug)
    schema = entry.get("target_schema") or target_schema or "public"
    table = entry.get("target_table") or catalog_slug
    return schema, table


def load_validation_rules(table_name: str) -> Dict[str, Any]:
    """Load validation_rules from the JSON config for a catalog table."""
    entry = get_catalog_table(table_name)
    if not entry:
        raise ValueError(f"Unknown catalog table: {table_name}")
    config_path = _CONFIG_ROOT / entry["config_file"]
    if not config_path.exists():
        raise FileNotFoundError(f"Catalog config not found: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    return config.get("validation_rules", {})


def load_full_config(table_name: str) -> Dict[str, Any]:
    """Load the full JSON config for a catalog table."""
    entry = get_catalog_table(table_name)
    if not entry:
        raise ValueError(f"Unknown catalog table: {table_name}")
    config_path = _CONFIG_ROOT / entry["config_file"]
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_config_path(table_name: str) -> Path:
    entry = get_catalog_table(table_name)
    if not entry:
        raise ValueError(f"Unknown catalog table: {table_name}")
    return _CONFIG_ROOT / entry["config_file"]

"""
Registry of catalog tables for the catalog upload flow.
Definitions are loaded from catalog_store (editable via admin UI).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from data_staging.services.catalog import catalog_store

_CATALOG_CONFIG_MARKER = Path("config") / "catalog"


def resolve_catalog_config_root() -> Path:
    """
    Locate project config/catalog/ (not src/config/catalog).
    Walks up from this module until a catalog config directory with JSON files exists.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / _CATALOG_CONFIG_MARKER
        if candidate.is_dir() and any(candidate.glob("*_config.json")):
            return candidate
    raise FileNotFoundError(
        f"Could not locate config/catalog directory (searched upward from {here})"
    )


_CONFIG_ROOT = resolve_catalog_config_root()


def list_catalog_tables() -> List[Dict[str, Any]]:
    """Return active catalog definitions for API and upload wizard."""
    return catalog_store.list_all_catalogs(active_only=True)


def get_catalog_table(table_name: str) -> Optional[Dict[str, Any]]:
    """Get a single catalog definition by name."""
    entry = catalog_store.get_catalog_by_name(table_name)
    if not entry or not entry.get("is_active"):
        return None
    return entry


def catalog_required_targets(entry: Optional[Dict[str, Any]]) -> List[str]:
    """
    Columns that must be mapped and non-empty for a catalog load.

    Union of required_columns + required_mapping_columns from catalog config,
    excluding organization_id (session-injected) and non_mappable_targets.
    """
    if not entry:
        return []
    skip = set(entry.get("non_mappable_targets") or [])
    skip.add("organization_id")
    seen: set[str] = set()
    out: List[str] = []
    for col in list(entry.get("required_columns") or []) + list(
        entry.get("required_mapping_columns") or []
    ):
        name = str(col or "").strip()
        if not name or name in skip or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def catalog_column_defaults(entry: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """
    Configured fill defaults for mappable catalog columns.

    Excludes organization_id and non_mappable_targets; ignores empty values.
    """
    if not entry:
        return {}
    skip = set(entry.get("non_mappable_targets") or [])
    skip.add("organization_id")
    out: Dict[str, str] = {}
    raw = entry.get("defaults") or {}
    if not isinstance(raw, dict):
        return {}
    for key, value in raw.items():
        name = str(key or "").strip()
        if not name or name in skip:
            continue
        text = "" if value is None else str(value).strip()
        if not text:
            continue
        out[name] = text
    return out


def catalog_required_targets_needing_mapping(entry: Optional[Dict[str, Any]]) -> List[str]:
    """Required targets that still need a wizard mapping (no config default)."""
    defaults = catalog_column_defaults(entry)
    return [c for c in catalog_required_targets(entry) if c not in defaults]


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
    """
    Load validation_rules from the JSON config for a catalog table.

    Overlay not_null.columns from catalog store required targets so the admin
    definition remains the source of truth for null rejection.
    """
    entry = get_catalog_table(table_name)
    if not entry:
        raise ValueError(f"Unknown catalog table: {table_name}")
    config_path = _CONFIG_ROOT / entry["config_file"]
    if not config_path.is_file():
        raise FileNotFoundError(f"Catalog config not found: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    rules = dict(config.get("validation_rules") or {})
    required = catalog_required_targets(entry)
    if required:
        not_null = dict(rules.get("not_null") or {})
        # Keep organization_id in not_null if the JSON listed it; always include config requireds.
        existing = [str(c) for c in (not_null.get("columns") or []) if str(c).strip()]
        merged: List[str] = []
        seen: set[str] = set()
        for col in existing + required:
            if col in seen:
                continue
            seen.add(col)
            merged.append(col)
        not_null["columns"] = merged
        not_null.setdefault("severity", "critical")
        rules["not_null"] = not_null
    return rules


def load_full_config(table_name: str) -> Dict[str, Any]:
    """Load the full JSON config for a catalog table."""
    entry = get_catalog_table(table_name)
    if not entry:
        raise ValueError(f"Unknown catalog table: {table_name}")
    config_path = _CONFIG_ROOT / entry["config_file"]
    if not config_path.is_file():
        raise FileNotFoundError(f"Catalog config not found: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_config_path(table_name: str) -> Path:
    entry = get_catalog_table(table_name)
    if not entry:
        raise ValueError(f"Unknown catalog table: {table_name}")
    return _CONFIG_ROOT / entry["config_file"]

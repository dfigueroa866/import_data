"""Registry for history load targets (sales_history, inventory_snapshot, …)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from data_staging.services.history import history_store


def list_history_tables(*, active_only: bool = True) -> List[Dict[str, Any]]:
    """Public view for wizard / API."""
    return history_store.list_all_tables(active_only=active_only)


def get_history_table(table_name: str) -> Optional[Dict[str, Any]]:
    """Resolve history table config by logical name (e.g. inventory_snapshot)."""
    return history_store.get_table_by_name(table_name)


def history_required_targets(entry: Optional[Dict[str, Any]]) -> List[str]:
    """Columns that must be present for a history load (from required_mapping_columns)."""
    if not entry:
        return []
    skip = set(entry.get("non_mappable_targets") or [])
    skip.add("organization_id")
    seen: set[str] = set()
    out: List[str] = []
    for col in list(entry.get("required_mapping_columns") or []):
        name = str(col or "").strip()
        if not name or name in skip or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def history_column_defaults(entry: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """Configured fill defaults for mappable history columns."""
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


def history_required_targets_needing_mapping(entry: Optional[Dict[str, Any]]) -> List[str]:
    """Required targets that still need a wizard mapping (no config default)."""
    defaults = history_column_defaults(entry)
    return [c for c in history_required_targets(entry) if c not in defaults]


def resolve_history_db_target(
    table_name: str,
    target_schema: Optional[str] = None,
) -> tuple[str, str]:
    """Return (schema, physical_table) for promotion."""
    entry = get_history_table(table_name)
    if not entry:
        raise ValueError(f"Tabla de historia desconocida o inactiva: {table_name}")
    schema = target_schema or entry.get("target_schema") or "public"
    physical = entry.get("target_table") or table_name
    return schema, physical

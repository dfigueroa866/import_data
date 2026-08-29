"""Persistent history table definitions (editable from admin UI)."""

from __future__ import annotations

import json
import re
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

_STORE_PATH = Path(__file__).resolve().parents[3] / "data" / "history_definition.json"
_LOCK = threading.Lock()

_TRUNCATE_RE = re.compile(r"^\d+(?:ns|us|µs|ms|mo|q|s|m|h|d|w|y)$", re.IGNORECASE)

_DEFAULT_FEATURES: Dict[str, bool] = {
    "auto_granularity": True,
    "auto_source": True,
    "auto_sales_channel": True,
    "derived_iso_flags": True,
}

_BUILTIN_PROCESS_TYPES: List[Dict[str, str]] = [
    {
        "key": "Weekly",
        "label": "Weekly (agrupa por semana)",
        "granularity": "week",
        "date_truncate": "1w",
    },
    {
        "key": "Monthly",
        "label": "Monthly (agrupa por mes)",
        "granularity": "month",
        "date_truncate": "1mo",
    },
]

_BUILTIN_SALES_HISTORY: Dict[str, Any] = {
    "name": "sales_history",
    "label": "Historial de ventas",
    "target_schema": "public",
    "target_table": "sales_history",
    "is_active": True,
    "supports_aggregation": True,
    "period_column": "period_start",
    "unique_keys": [
        "organization_id",
        "location_code",
        "sku",
        "period_start",
        "granularity",
    ],
    "upsert_update_columns": [
        "quantity",
        "pieces",
        "imported_at",
        "iso_year",
        "iso_week",
        "stockout_flag",
        "markdown_pct",
        "promo_flag",
    ],
    "required_mapping_columns": [
        "sku",
        "location_code",
        "period_start",
        "quantity",
        "pieces",
    ],
    "optional_columns": [],
    "non_mappable_targets": [
        "granularity",
        "source",
        "sales_channel",
        "iso_year",
        "iso_week",
        "stockout_flag",
        "markdown_pct",
        "promo_flag",
    ],
    "ignored_file_headers": ["id", "organization_id"],
    "sku_mapping_targets": ["sku"],
    "logical_columns": ["sku_code"],
    "sales_channel_default": "SELL_IN",
    "features": dict(_DEFAULT_FEATURES),
    "process_types": deepcopy(_BUILTIN_PROCESS_TYPES),
    "validation_hints": [
        "Destino fijo: public.sales_history",
        "Mapea location_code, sku (o sku_code lógico) y period_start, quantity, pieces",
        "UPSERT por: organization_id + location_code + sku + period_start + granularity",
        "sales_channel se aplica automáticamente como SELL_IN",
        "granularity: del campo Granularidad / tipo de proceso del paso 1 (Weekly→week, Monthly→month)",
        "source: extensión del archivo subido",
        "organization_id se aplica automáticamente del usuario",
        "iso_year e iso_week se derivan de period_start (tras agregación)",
        "stockout_flag=false, markdown_pct=0, promo_flag=false (automáticos)",
    ],
}

_BUILTIN_INVENTORY_SNAPSHOT: Dict[str, Any] = {
    "name": "inventory_snapshot",
    "label": "Inventario (snapshot)",
    "target_schema": "public",
    "target_table": "inventory_snapshot",
    "is_active": True,
    "supports_aggregation": False,
    "period_column": "snapshot_date",
    "unique_keys": [
        "organization_id",
        "sku",
        "location_code",
        "snapshot_date",
    ],
    "upsert_update_columns": [
        "on_hand_qty",
        "allocated_qty",
        "reserved_qty",
        "blocked_qty",
        "quarantine_qty",
        "supplier_id",
        "lead_time_days",
        "review_period_days",
        "moq",
        "lot_multiple",
        "unit_cost",
        "currency",
    ],
    "required_mapping_columns": [
        "snapshot_date",
        "sku",
        "location_code",
        "on_hand_qty",
    ],
    "optional_columns": [
        "allocated_qty",
        "reserved_qty",
        "blocked_qty",
        "quarantine_qty",
        "supplier_id",
        "lead_time_days",
        "review_period_days",
        "moq",
        "lot_multiple",
        "unit_cost",
        "currency",
    ],
    "non_mappable_targets": [
        "organization_id",
        "snapshot_id",
        "created_at",
    ],
    "ignored_file_headers": ["snapshot_id", "organization_id", "created_at"],
    "sku_mapping_targets": ["sku"],
    "logical_columns": ["sku_code"],
    "sales_channel_default": "SELL_IN",
    "features": {
        "auto_granularity": False,
        "auto_source": False,
        "auto_sales_channel": False,
        "derived_iso_flags": False,
    },
    "process_types": [
        {
            "key": "Snapshot",
            "label": "Snapshot (sin agregación)",
            "granularity": "snapshot",
            "date_truncate": "1d",
        }
    ],
    "validation_hints": [
        "Destino: public.inventory_snapshot",
        "Mapea snapshot_date, sku, location_code y on_hand_qty como mínimo",
        "Clave natural sugerida: organization_id + sku + location_code + snapshot_date",
        "snapshot_id y created_at los genera la base de datos",
        "organization_id se aplica automáticamente del usuario",
        "Sin agregación semanal/mensual: cada fila del archivo es un snapshot",
    ],
}

_BUILTIN_TABLES: List[Dict[str, Any]] = [
    deepcopy(_BUILTIN_SALES_HISTORY),
    deepcopy(_BUILTIN_INVENTORY_SNAPSHOT),
]


def _public_view(entry: Dict[str, Any]) -> Dict[str, Any]:
    return deepcopy(entry)


def _ensure_store_file() -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _STORE_PATH.exists():
        payload = {"version": 2, "tables": deepcopy(_BUILTIN_TABLES)}
        _STORE_PATH.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def _migrate_legacy_format(data: Dict[str, Any]) -> Dict[str, Any]:
    if data.get("tables"):
        return data
    legacy = data.get("definition")
    if legacy:
        return {"version": 2, "tables": [legacy]}
    return {"version": 2, "tables": deepcopy(_BUILTIN_TABLES)}


def _merge_missing_builtin_tables(tables: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ensure built-in tables (e.g. inventory_snapshot) exist after upgrades."""
    by_name = {t.get("name"): t for t in tables if t.get("name")}
    changed = False
    for builtin in _BUILTIN_TABLES:
        name = builtin["name"]
        if name not in by_name:
            by_name[name] = deepcopy(builtin)
            changed = True
    merged = sorted(by_name.values(), key=lambda t: t["name"])
    return merged, changed


def _load_raw() -> Dict[str, Any]:
    _ensure_store_file()
    with _STORE_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    data = _migrate_legacy_format(data)
    tables = data.get("tables") or []
    tables, changed = _merge_missing_builtin_tables(tables)
    if changed or not data.get("tables"):
        data = {"version": 2, "tables": tables}
        _save_raw(data)
    elif data.get("version") != 2:
        data["version"] = 2
        _save_raw(data)
    return data


def _save_raw(data: Dict[str, Any]) -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STORE_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _normalize_process_type(entry: Dict[str, Any]) -> Dict[str, str]:
    key = str(entry.get("key") or "").strip()
    label = str(entry.get("label") or "").strip()
    granularity = str(entry.get("granularity") or "").strip()
    date_truncate = str(entry.get("date_truncate") or "").strip()

    if not key:
        raise ValueError("Cada tipo de proceso debe tener un identificador (key).")
    if not label:
        raise ValueError(f"El tipo de proceso '{key}' debe tener etiqueta (label).")
    if not granularity:
        raise ValueError(f"El tipo de proceso '{key}' debe tener valor de granularity.")
    if not date_truncate or not _TRUNCATE_RE.match(date_truncate):
        raise ValueError(
            f"date_truncate inválido para '{key}': use formato Polars (p. ej. 1w, 1mo, 1d)."
        )
    return {
        "key": key,
        "label": label,
        "granularity": granularity,
        "date_truncate": date_truncate,
    }


def _normalize_features(raw: Optional[Dict[str, Any]]) -> Dict[str, bool]:
    merged = dict(_DEFAULT_FEATURES)
    if raw:
        for key, value in raw.items():
            if key in merged:
                merged[key] = bool(value)
    return merged


def _normalize_table(payload: Dict[str, Any], *, fallback: Dict[str, Any]) -> Dict[str, Any]:
    base = deepcopy(fallback)
    merged = {**base, **(payload or {})}

    name = str(merged.get("name") or base["name"]).strip()
    if not name:
        raise ValueError("Cada tabla de historia debe tener name.")

    process_types_raw = merged.get("process_types") or []
    if not process_types_raw:
        raise ValueError(f"Debe existir al menos un tipo de proceso para '{name}'.")

    process_types = [_normalize_process_type(pt) for pt in process_types_raw]
    keys = [pt["key"] for pt in process_types]
    if len(keys) != len(set(keys)):
        raise ValueError(f"Los identificadores (key) de tipos de proceso deben ser únicos en '{name}'.")

    sales_channel_default = str(merged.get("sales_channel_default") or "SELL_IN").strip()
    if not sales_channel_default:
        raise ValueError("sales_channel_default no puede estar vacío.")

    target_schema = str(merged.get("target_schema") or "public").strip() or "public"
    target_table = str(merged.get("target_table") or name).strip() or name

    return {
        "name": name,
        "label": str(merged.get("label") or base.get("label") or name).strip(),
        "target_schema": target_schema,
        "target_table": target_table,
        "is_active": bool(merged.get("is_active", True)),
        "supports_aggregation": bool(merged.get("supports_aggregation", True)),
        "period_column": str(merged.get("period_column") or base.get("period_column") or "period_start"),
        "unique_keys": list(merged.get("unique_keys") or base["unique_keys"]),
        "upsert_update_columns": list(
            merged.get("upsert_update_columns") or base.get("upsert_update_columns") or []
        ),
        "required_mapping_columns": list(
            merged.get("required_mapping_columns") or base["required_mapping_columns"]
        ),
        "optional_columns": list(merged.get("optional_columns") or []),
        "non_mappable_targets": list(
            merged.get("non_mappable_targets") or base["non_mappable_targets"]
        ),
        "ignored_file_headers": list(
            merged.get("ignored_file_headers") or base["ignored_file_headers"]
        ),
        "sku_mapping_targets": list(
            merged.get("sku_mapping_targets") or base["sku_mapping_targets"]
        ),
        "logical_columns": list(merged.get("logical_columns") or base["logical_columns"]),
        "sales_channel_default": sales_channel_default,
        "features": _normalize_features(merged.get("features") or base.get("features")),
        "process_types": process_types,
        "validation_hints": list(merged.get("validation_hints") or base["validation_hints"]),
        "defaults": dict(merged.get("defaults") or base.get("defaults") or {}),
    }


def _builtin_for_name(name: str) -> Dict[str, Any]:
    for entry in _BUILTIN_TABLES:
        if entry["name"] == name:
            return entry
    return _BUILTIN_SALES_HISTORY


def list_all_tables(*, active_only: bool = False) -> List[Dict[str, Any]]:
    with _LOCK:
        tables = [_public_view(t) for t in _load_raw().get("tables", [])]
    if active_only:
        tables = [t for t in tables if t.get("is_active", True)]
    return sorted(tables, key=lambda t: t["name"])


def get_table_by_name(name: str) -> Optional[Dict[str, Any]]:
    key = (name or "").strip()
    if not key:
        return None
    with _LOCK:
        for entry in _load_raw().get("tables", []):
            if entry.get("name") == key:
                return _public_view(entry)
    return None


def get_definition(table_name: Optional[str] = None) -> Dict[str, Any]:
    """Backward-compatible: returns one table definition (default sales_history)."""
    name = (table_name or "sales_history").strip() or "sales_history"
    entry = get_table_by_name(name)
    if entry:
        return entry
    return _public_view(_BUILTIN_SALES_HISTORY)


def update_definition(payload: Dict[str, Any], *, table_name: Optional[str] = None) -> Dict[str, Any]:
    name = (table_name or payload.get("name") or "sales_history").strip()
    fallback = _builtin_for_name(name)
    entry = _normalize_table({**payload, "name": name}, fallback=fallback)
    with _LOCK:
        data = _load_raw()
        tables = data.setdefault("tables", [])
        for idx, existing in enumerate(tables):
            if existing.get("name") == name:
                tables[idx] = entry
                _save_raw(data)
                return deepcopy(entry)
        tables.append(entry)
        _save_raw(data)
    return deepcopy(entry)


def get_process_types(table_name: Optional[str] = None) -> List[Dict[str, str]]:
    return list(get_definition(table_name).get("process_types") or [])


def get_process_type_config(
    process_type: Optional[str],
    table_name: Optional[str] = None,
) -> Optional[Dict[str, str]]:
    key = (process_type or "").strip()
    if not key:
        return None
    for pt in get_process_types(table_name):
        if pt.get("key") == key:
            return dict(pt)
    return None


def is_valid_process_type(
    process_type: Optional[str],
    table_name: Optional[str] = None,
) -> bool:
    return get_process_type_config(process_type, table_name) is not None


def valid_process_type_keys(table_name: Optional[str] = None) -> tuple:
    return tuple(pt["key"] for pt in get_process_types(table_name))

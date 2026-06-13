"""
Persistent catalog definitions (editable from admin UI).
Stored in data/catalog_definitions.json; seeded with built-in catalogs on first run.
"""

from __future__ import annotations

import json
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

_STORE_PATH = Path(__file__).resolve().parents[3] / "data" / "catalog_definitions.json"
_LOCK = threading.Lock()

_BUILTIN_CATALOGS: List[Dict[str, Any]] = [
    {
        "name": "skus",
        "label": "Productos (SKUs)",
        "target_schema": "public",
        "target_table": "skus",
        "config_file": "skus_config.json",
        "is_active": True,
        "required_columns": ["organization_id", "code", "name", "status"],
        "optional_columns": ["category", "family", "brand", "attributes"],
        "required_mapping_columns": ["status"],
        "unique_keys": ["organization_id", "code"],
        "ignored_file_headers": ["sku_id", "organization_id", "created_at", "updated_at", "imported_at"],
        "non_mappable_targets": [
            "sku_id",
            "id",
            "organization_id",
            "created_at",
            "updated_at",
            "imported_at",
        ],
        "column_aliases": {
            "organization_id": ["organization_id", "org_id", "organization"],
            "code": ["code", "sku_code", "sku", "product_code"],
            "name": ["name", "sku_name", "product_name", "description"],
            "category": ["category", "categoria"],
            "family": ["family", "familia"],
            "brand": ["brand", "marca"],
            "status": ["status", "estado"],
            "attributes": ["attributes", "attrs", "json_attributes"],
        },
        "enums": {"status": ["active", "discontinued", "new_launch"]},
        "validation_hints": [
            "Clave única: (organization_id, code)",
            "code es el SKU del producto (no uses la columna de archivo sku_id; es el UUID de la BD)",
            "sku_id, created_at y updated_at los genera la base de datos",
            "status es obligatorio en el mapping (active, discontinued o new_launch)",
            "organization_id se asigna automáticamente del usuario",
        ],
    },
    {
        "name": "location",
        "label": "Ubicaciones",
        "target_schema": "public",
        "target_table": "location",
        "config_file": "location_config.json",
        "is_active": True,
        "required_columns": ["organization_id", "location_code", "location_name"],
        "optional_columns": ["country", "city", "timezone", "is_active", "location_type"],
        "required_mapping_columns": [],
        "unique_keys": ["organization_id", "code"],
        "ignored_file_headers": [
            "location_id",
            "organization_id",
            "created_at",
            "updated_at",
            "imported_at",
        ],
        "non_mappable_targets": [
            "location_id",
            "id",
            "organization_id",
            "created_at",
            "updated_at",
            "imported_at",
        ],
        "column_aliases": {
            "organization_id": ["organization_id", "org_id", "organization"],
            "location_code": ["location_code", "code", "loc_code"],
            "location_name": ["location_name", "name", "location", "store_name"],
            "country": ["country", "pais", "país"],
            "city": ["city", "ciudad"],
            "timezone": ["timezone", "tz"],
            "is_active": ["is_active", "active", "status"],
            "location_type": ["location_type", "loc_type", "loc_tyoe", "type"],
        },
        "enums": {},
        "validation_hints": [
            "Clave única: (organization_id, location_code)",
            "location_code es el código de negocio (no uses location_id del archivo; es el UUID de la BD)",
            "location_id, organization_id, created_at y updated_at los genera o asigna el sistema",
        ],
    },
]


def _normalize_table_name(table: str) -> str:
    name = (table or "").strip().lower()
    if not name:
        raise ValueError("La tabla destino es obligatoria")
    return name


def _ensure_store_file() -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _STORE_PATH.exists():
        payload = {"version": 1, "catalogs": deepcopy(_BUILTIN_CATALOGS)}
        _STORE_PATH.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def _load_raw() -> Dict[str, Any]:
    _ensure_store_file()
    with _STORE_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not data.get("catalogs"):
        data = {"version": 1, "catalogs": deepcopy(_BUILTIN_CATALOGS)}
        _save_raw(data)
    return data


def _save_raw(data: Dict[str, Any]) -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STORE_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _public_view(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": entry["name"],
        "label": entry.get("label", entry["name"]),
        "target_schema": entry.get("target_schema", "public"),
        "target_table": entry.get("target_table", entry["name"]),
        "config_file": entry.get("config_file"),
        "is_active": bool(entry.get("is_active", True)),
        "required_columns": list(entry.get("required_columns") or []),
        "optional_columns": list(entry.get("optional_columns") or []),
        "required_mapping_columns": list(entry.get("required_mapping_columns") or []),
        "unique_keys": list(entry.get("unique_keys") or []),
        "ignored_file_headers": list(entry.get("ignored_file_headers") or []),
        "non_mappable_targets": list(entry.get("non_mappable_targets") or []),
        "enums": dict(entry.get("enums") or {}),
        "defaults": dict(entry.get("defaults") or {}),
        "validation_hints": list(entry.get("validation_hints") or []),
        "column_aliases": dict(entry.get("column_aliases") or {}),
    }


def list_all_catalogs(*, active_only: bool = False) -> List[Dict[str, Any]]:
    with _LOCK:
        data = _load_raw()
        catalogs = [_public_view(c) for c in data.get("catalogs", [])]
    if active_only:
        catalogs = [c for c in catalogs if c.get("is_active")]
    return sorted(catalogs, key=lambda c: c["name"])


def get_catalog_by_name(name: str) -> Optional[Dict[str, Any]]:
    key = (name or "").lower().strip()
    with _LOCK:
        for entry in _load_raw().get("catalogs", []):
            if entry.get("name", "").lower() == key:
                return _public_view(entry)
    return None


def create_catalog(payload: Dict[str, Any]) -> Dict[str, Any]:
    entry = _normalize_payload(payload)
    with _LOCK:
        data = _load_raw()
        catalogs = data.setdefault("catalogs", [])
        if any(c.get("name") == entry["name"] for c in catalogs):
            raise ValueError(f"Ya existe un catálogo para la tabla '{entry['name']}'")
        catalogs.append(entry)
        _save_raw(data)
    return _public_view(entry)


def update_catalog(name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    key = (name or "").lower().strip()
    with _LOCK:
        data = _load_raw()
        catalogs = data.setdefault("catalogs", [])
        for idx, existing in enumerate(catalogs):
            if existing.get("name", "").lower() != key:
                continue
            merged = {**existing, **payload}
            entry = _normalize_payload(merged, catalog_name=existing["name"])
            catalogs[idx] = entry
            _save_raw(data)
            return _public_view(entry)
    raise ValueError(f"Catálogo no encontrado: {name}")


def delete_catalog(name: str, *, hard: bool = False) -> None:
    key = (name or "").lower().strip()
    with _LOCK:
        data = _load_raw()
        catalogs = data.get("catalogs", [])
        for idx, entry in enumerate(catalogs):
            if entry.get("name", "").lower() != key:
                continue
            if hard:
                catalogs.pop(idx)
            else:
                entry["is_active"] = False
            _save_raw(data)
            return
    raise ValueError(f"Catálogo no encontrado: {name}")


def _normalize_payload(payload: Dict[str, Any], *, catalog_name: Optional[str] = None) -> Dict[str, Any]:
    target_table = _normalize_table_name(payload.get("target_table") or payload.get("name") or "")
    name = catalog_name or target_table
    config_file = payload.get("config_file") or f"{target_table}_config.json"

    return {
        "name": name,
        "label": (payload.get("label") or name).strip(),
        "target_schema": (payload.get("target_schema") or "public").strip(),
        "target_table": target_table,
        "config_file": config_file,
        "is_active": bool(payload.get("is_active", True)),
        "required_columns": _as_db_column_list(payload.get("required_columns")),
        "optional_columns": _as_db_column_list(payload.get("optional_columns")),
        "required_mapping_columns": _as_db_column_list(payload.get("required_mapping_columns")),
        "unique_keys": _as_db_column_list(payload.get("unique_keys")),
        "ignored_file_headers": _as_str_list(payload.get("ignored_file_headers")),
        "non_mappable_targets": _as_db_column_list(payload.get("non_mappable_targets")),
        "column_aliases": dict(payload.get("column_aliases") or {}),
        "enums": dict(payload.get("enums") or {}),
        "defaults": dict(payload.get("defaults") or {}),
        "validation_hints": _as_str_list(payload.get("validation_hints")),
    }


def _as_str_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [s.strip() for s in value.split(",") if s.strip()]
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def _as_db_column_list(value: Any) -> List[str]:
    """Normalize column names to lowercase DB identifiers."""
    return [s.strip().lower() for s in _as_str_list(value)]

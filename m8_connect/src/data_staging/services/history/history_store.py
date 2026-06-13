"""Persistent history definition (editable from admin UI)."""

from __future__ import annotations

import json
import re
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

_STORE_PATH = Path(__file__).resolve().parents[3] / "data" / "history_definition.json"
_LOCK = threading.Lock()

# Polars dt.truncate: 1w, 1mo, 1d, 1ms, etc. (sufijos de varios caracteres primero)
_TRUNCATE_RE = re.compile(r"^\d+(?:ns|us|µs|ms|mo|q|s|m|h|d|w|y)$", re.IGNORECASE)

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

_BUILTIN_DEFINITION: Dict[str, Any] = {
    "name": "sales_history",
    "label": "Historial de ventas",
    "target_schema": "public",
    "target_table": "sales_history",
    "unique_keys": [
        "organization_id",
        "location_code",
        "sku",
        "period_start",
        "granularity",
    ],
    "required_mapping_columns": [
        "sku",
        "location_code",
        "period_start",
        "quantity",
        "pieces",
    ],
    "optional_columns": [],
    "non_mappable_targets": ["granularity", "source", "sales_channel"],
    "ignored_file_headers": ["id", "organization_id"],
    "sku_mapping_targets": ["sku"],
    "logical_columns": ["sku_code"],
    "sales_channel_default": "SELL_IN",
    "process_types": deepcopy(_BUILTIN_PROCESS_TYPES),
    "validation_hints": [
        "Destino fijo: public.sales_history",
        "Mapea location_code, sku (o sku_code lógico) y period_start, quantity, pieces",
        "UPSERT por: organization_id + location_code + sku + period_start + granularity",
        "sales_channel se aplica automáticamente como SELL_IN",
        "granularity: del tipo de proceso seleccionado en el paso 1",
        "source: extensión del archivo subido",
        "organization_id se aplica automáticamente del usuario",
    ],
}


def _ensure_store_file() -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _STORE_PATH.exists():
        payload = {"version": 1, "definition": deepcopy(_BUILTIN_DEFINITION)}
        _STORE_PATH.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def _load_raw() -> Dict[str, Any]:
    _ensure_store_file()
    with _STORE_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not data.get("definition"):
        data = {"version": 1, "definition": deepcopy(_BUILTIN_DEFINITION)}
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


def _normalize_definition(payload: Dict[str, Any]) -> Dict[str, Any]:
    base = deepcopy(_BUILTIN_DEFINITION)
    merged = {**base, **(payload or {})}

    process_types_raw = merged.get("process_types") or []
    if not process_types_raw:
        raise ValueError("Debe existir al menos un tipo de proceso (granularity).")

    process_types = [_normalize_process_type(pt) for pt in process_types_raw]
    keys = [pt["key"] for pt in process_types]
    if len(keys) != len(set(keys)):
        raise ValueError("Los identificadores (key) de tipos de proceso deben ser únicos.")

    sales_channel_default = str(merged.get("sales_channel_default") or "SELL_IN").strip()
    if not sales_channel_default:
        raise ValueError("sales_channel_default no puede estar vacío.")

    return {
        "name": "sales_history",
        "label": str(merged.get("label") or base["label"]).strip(),
        "target_schema": "public",
        "target_table": "sales_history",
        "unique_keys": list(merged.get("unique_keys") or base["unique_keys"]),
        "required_mapping_columns": list(
            merged.get("required_mapping_columns") or base["required_mapping_columns"]
        ),
        "optional_columns": list(merged.get("optional_columns") or []),
        "non_mappable_targets": list(
            merged.get("non_mappable_targets") or base["non_mappable_targets"]
        ),
        "ignored_file_headers": list(merged.get("ignored_file_headers") or base["ignored_file_headers"]),
        "sku_mapping_targets": list(merged.get("sku_mapping_targets") or base["sku_mapping_targets"]),
        "logical_columns": list(merged.get("logical_columns") or base["logical_columns"]),
        "sales_channel_default": sales_channel_default,
        "process_types": process_types,
        "validation_hints": list(merged.get("validation_hints") or base["validation_hints"]),
    }


def get_definition() -> Dict[str, Any]:
    with _LOCK:
        return deepcopy(_load_raw().get("definition") or _BUILTIN_DEFINITION)


def update_definition(payload: Dict[str, Any]) -> Dict[str, Any]:
    entry = _normalize_definition(payload)
    with _LOCK:
        data = _load_raw()
        data["definition"] = entry
        _save_raw(data)
    return deepcopy(entry)


def get_process_types() -> List[Dict[str, str]]:
    return list(get_definition().get("process_types") or [])


def get_process_type_config(process_type: Optional[str]) -> Optional[Dict[str, str]]:
    key = (process_type or "").strip()
    if not key:
        return None
    for pt in get_process_types():
        if pt.get("key") == key:
            return dict(pt)
    return None


def is_valid_process_type(process_type: Optional[str]) -> bool:
    return get_process_type_config(process_type) is not None


def valid_process_type_keys() -> tuple:
    return tuple(pt["key"] for pt in get_process_types())

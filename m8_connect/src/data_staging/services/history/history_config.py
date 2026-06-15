"""Configuración única para carga de historia → public.sales_history."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

HISTORY_TARGET_SCHEMA = "public"
HISTORY_TARGET_TABLE = "sales_history"
HISTORY_SOURCE_NAME = "sales_history"

# Columnas actualizadas en ON CONFLICT DO UPDATE (promoción fase 2)
HISTORY_UPSERT_UPDATE_COLUMNS = ["quantity", "pieces", "imported_at"]

# Clave natural en BD (índice único) — UPSERT en promoción
HISTORY_UNIQUE_KEYS = [
    "organization_id",
    "location_code",
    "sku",
    "period_start",
    "granularity",
]

# Columnas NOT NULL en sales_history
HISTORY_REQUIRED_COLUMNS = [
    "organization_id",
    "location_code",
    "sku",
    "period_start",
    "granularity",
    "quantity",
    "source",
    "pieces"
]

# Obligatorias en paso 2 (mapeo desde archivo)
HISTORY_SKU_MAPPING_TARGETS = ["sku"]

HISTORY_SALES_CHANNEL_VALUE = "SELL_IN"

HISTORY_REQUIRED_MAPPING_COLUMNS = [
    "sku",
    "location_code",
    "period_start",
    "quantity",
    "pieces",
]

# sku_code solo si la tabla no tiene columna «sku»
HISTORY_LOGICAL_COLUMNS = ["sku_code"]

# Campos generados por el sistema (no mapear desde archivo)
HISTORY_NON_MAPPABLE_TARGETS = ["granularity", "source", "sales_channel"]

# Columnas inyectadas por el sistema en promoción aunque no estén en el mapeo del wizard
HISTORY_AUTO_PROMOTION_COLUMNS = ["organization_id", "granularity", "source", "sales_channel"]


def is_sales_history_target(target_schema: str, target_table: str) -> bool:
    """True si el destino físico es public.sales_history."""
    return (
        (target_table or "").lower() == HISTORY_TARGET_TABLE.lower()
        and (target_schema or "").lower() == HISTORY_TARGET_SCHEMA.lower()
    )

HISTORY_IGNORED_FILE_HEADERS = ["id"]

#HISTORY_COLUMN_ALIASES: Dict[str, List[str]] = {
#    "period_start": [
#        "period_start",
#        "start_date",
#        "fecha",
#        "date",
#        "week_monday",
#    ],
#    "quantity": ["quantity", "qty", "cantidad", "amount"],
#    "location_code": ["location_code", "loc", "location", "store", "tienda"],
#    "sku_code": [
#        "sku_code",
#        "dmd_unit",
#        "sku",
#        "product_code",
#        "code",
#        "item",
#    ],
#    "granularity": ["granularity", "gran", "period_type"],
#    "sales_channel": ["sales_channel", "channel", "canal", "sales channel"],
#    "pieces": ["pieces", "piezas", "units", "unidades"],
#}

HISTORY_VALID_PROCESS_TYPES = ("Weekly", "Monthly")

PROCESS_TYPE_GRANULARITY = {
    "Weekly": "week",
    "Monthly": "month",
}


def _definition_from_store() -> Dict[str, Any]:
    try:
        from data_staging.services.history.history_store import get_definition

        return get_definition()
    except Exception:
        return {}


def get_process_types() -> List[Dict[str, str]]:
    """Tipos de proceso / granularity configurables (desde store o builtin)."""
    stored = _definition_from_store().get("process_types")
    if stored:
        return list(stored)
    return [
        {"key": k, "label": k, "granularity": v, "date_truncate": "1w" if k == "Weekly" else "1mo"}
        for k, v in PROCESS_TYPE_GRANULARITY.items()
    ]


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


def date_truncate_for_process_type(process_type: Optional[str]) -> str:
    pt = get_process_type_config(process_type)
    if not pt:
        valid = ", ".join(valid_process_type_keys()) or "Weekly, Monthly"
        raise ValueError(f"process_type inválido: {process_type!r}. Use: {valid}")
    return pt["date_truncate"]


def get_sales_channel_default() -> str:
    stored = _definition_from_store().get("sales_channel_default")
    if stored:
        return str(stored).strip()
    return HISTORY_SALES_CHANNEL_VALUE


def get_auto_promotion_columns(rules: Optional[Dict[str, Any]] = None) -> List[str]:
    """Columnas inyectadas en promoción (sesión + wizard), derivadas de la config."""
    src = rules or {}
    non_map = list(src.get("non_mappable_targets") or HISTORY_NON_MAPPABLE_TARGETS)
    auto: List[str] = []
    for col in non_map:
        if col not in auto:
            auto.append(col)
    if "organization_id" not in auto:
        auto.insert(0, "organization_id")
    for col in HISTORY_AUTO_PROMOTION_COLUMNS:
        if col not in auto:
            auto.append(col)
    return auto


def resolve_history_rules(metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Reglas efectivas para validación/transformación/promoción.
    Prioridad: snapshot metadata['history_config'] → store vivo → builtins.
    """
    snapshot = (metadata or {}).get("history_config")
    if isinstance(snapshot, dict) and snapshot.get("required_mapping_columns") is not None:
        base = dict(snapshot)
    else:
        base = get_history_table_meta()

    sales_channel_default = str(
        base.get("sales_channel_default") or get_sales_channel_default()
    ).strip() or HISTORY_SALES_CHANNEL_VALUE

    rules = {
        "required_mapping_columns": list(
            base.get("required_mapping_columns") or HISTORY_REQUIRED_MAPPING_COLUMNS
        ),
        "optional_columns": list(base.get("optional_columns") or []),
        "sku_mapping_targets": list(
            base.get("sku_mapping_targets") or HISTORY_SKU_MAPPING_TARGETS
        ),
        "logical_columns": list(base.get("logical_columns") or HISTORY_LOGICAL_COLUMNS),
        "unique_keys": list(base.get("unique_keys") or HISTORY_UNIQUE_KEYS),
        "ignored_file_headers": list(
            base.get("ignored_file_headers") or HISTORY_IGNORED_FILE_HEADERS
        ),
        "non_mappable_targets": list(
            base.get("non_mappable_targets") or HISTORY_NON_MAPPABLE_TARGETS
        ),
        "sales_channel_default": sales_channel_default,
        "process_types": list(base.get("process_types") or get_process_types()),
    }
    rules["auto_promotion_columns"] = get_auto_promotion_columns(rules)
    return rules


def sku_columns_for_validation(rules: Dict[str, Any]) -> List[str]:
    """Columnas a comprobar para presencia de código de producto."""
    cols = list(rules.get("sku_mapping_targets") or HISTORY_SKU_MAPPING_TARGETS)
    for name in rules.get("logical_columns") or []:
        if name not in cols:
            cols.append(name)
    return cols


def source_from_filename(filename: str) -> str:
    """Extensión del archivo sin punto (p. ej. csv, xlsx)."""
    from pathlib import Path

    ext = Path(filename or "").suffix.lower().lstrip(".")
    return ext or "unknown"


def normalize_sales_channel(
    value: Any,
    default: Optional[str] = None,
) -> Optional[str]:
    """Normaliza al default configurado si el valor es equivalente; None si vacío."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    default_val = (default or get_sales_channel_default()).strip()
    if text.upper().replace("-", "_") == default_val.upper().replace("-", "_"):
        return default_val
    return text


def is_valid_sales_channel(value: Any, default: Optional[str] = None) -> bool:
    default_val = default or get_sales_channel_default()
    return normalize_sales_channel(value, default_val) == default_val


def enrich_history_preview_rows(
    rows: List[Dict[str, Any]],
    *,
    process_type: Optional[str] = None,
    source_extension: Optional[str] = None,
    organization_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Añade columnas automáticas de historia a cada fila de vista previa."""
    try:
        preview_granularity = granularity_for_process_type(process_type)
    except ValueError:
        preview_granularity = None
    preview_source = (source_extension or "").strip().lower() or None
    enriched: List[Dict[str, Any]] = []
    for row in rows:
        out = dict(row)
        out["sales_channel"] = get_sales_channel_default()
        if preview_granularity:
            out["granularity"] = preview_granularity
        if preview_source:
            out["source"] = preview_source
        if organization_id:
            out["organization_id"] = organization_id
        enriched.append(out)
    return enriched


def granularity_for_process_type(process_type: Optional[str]) -> str:
    pt = get_process_type_config(process_type)
    if pt and pt.get("granularity"):
        return pt["granularity"]
    gran = PROCESS_TYPE_GRANULARITY.get(process_type or "")
    if not gran:
        valid = ", ".join(valid_process_type_keys()) or "Weekly, Monthly"
        raise ValueError(f"process_type inválido: {process_type!r}. Use: {valid}")
    return gran


def get_history_table_meta() -> Dict[str, Any]:
    """Metadatos para wizard/API (misma forma que catálogos)."""
    stored = _definition_from_store()
    if stored:
        meta = {
            "name": stored.get("name", HISTORY_TARGET_TABLE),
            "label": stored.get("label", "Historial de ventas"),
            "target_schema": stored.get("target_schema", HISTORY_TARGET_SCHEMA),
            "target_table": stored.get("target_table", HISTORY_TARGET_TABLE),
            "required_columns": list(HISTORY_REQUIRED_COLUMNS),
            "optional_columns": list(stored.get("optional_columns") or []),
            "required_mapping_columns": list(stored.get("required_mapping_columns") or HISTORY_REQUIRED_MAPPING_COLUMNS),
            "sku_mapping_targets": list(stored.get("sku_mapping_targets") or HISTORY_SKU_MAPPING_TARGETS),
            "logical_columns": list(stored.get("logical_columns") or HISTORY_LOGICAL_COLUMNS),
            "unique_keys": list(stored.get("unique_keys") or HISTORY_UNIQUE_KEYS),
            "ignored_file_headers": list(stored.get("ignored_file_headers") or HISTORY_IGNORED_FILE_HEADERS),
            "non_mappable_targets": list(stored.get("non_mappable_targets") or HISTORY_NON_MAPPABLE_TARGETS),
            "sales_channel_default": get_sales_channel_default(),
            "process_types": get_process_types(),
            "validation_hints": list(stored.get("validation_hints") or []),
        }
        return meta

    return {
        "name": HISTORY_TARGET_TABLE,
        "label": "Historial de ventas",
        "target_schema": HISTORY_TARGET_SCHEMA,
        "target_table": HISTORY_TARGET_TABLE,
        "required_columns": list(HISTORY_REQUIRED_COLUMNS),
        "optional_columns": ["sales_channel", "pieces", "source"],
        "required_mapping_columns": list(HISTORY_REQUIRED_MAPPING_COLUMNS),
        "sku_mapping_targets": list(HISTORY_SKU_MAPPING_TARGETS),
        "logical_columns": list(HISTORY_LOGICAL_COLUMNS),
        "unique_keys": list(HISTORY_UNIQUE_KEYS),
        "ignored_file_headers": list(HISTORY_IGNORED_FILE_HEADERS),
        "non_mappable_targets": list(HISTORY_NON_MAPPABLE_TARGETS),
        "sales_channel_default": HISTORY_SALES_CHANNEL_VALUE,
        "process_types": get_process_types(),
        "validation_hints": [
            "Destino fijo: public.sales_history",
            "Mapea location_code, sku (o sku_code lógico) y period_start, quantity, pieces",
            "UPSERT por: organization_id + location_code + sku + period_start + granularity",
            "sales_channel se aplica automáticamente como SELL_IN",
            "granularity: del tipo de proceso seleccionado en el paso 1",
            "source: extensión del archivo subido (paso 1)",
            "organization_id se aplica automáticamente del usuario",
        ],
    }

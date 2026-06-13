"""Configuración única para carga de historia → public.sales_history."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

HISTORY_TARGET_SCHEMA = "public"
HISTORY_TARGET_TABLE = "sales_history"
HISTORY_SOURCE_NAME = "sales_history"

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
    "id",
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

# Solo PK / campos generados por el sistema
HISTORY_NON_MAPPABLE_TARGETS = ["id", "granularity", "source", "sales_channel"]

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


def source_from_filename(filename: str) -> str:
    """Extensión del archivo sin punto (p. ej. csv, xlsx)."""
    from pathlib import Path

    ext = Path(filename or "").suffix.lower().lstrip(".")
    return ext or "unknown"


def normalize_sales_channel(value: Any) -> Optional[str]:
    """Normaliza a SELL_IN si el valor es equivalente; None si vacío."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.upper().replace("-", "_") == "SELL_IN":
        return HISTORY_SALES_CHANNEL_VALUE
    return text


def is_valid_sales_channel(value: Any) -> bool:
    return normalize_sales_channel(value) == HISTORY_SALES_CHANNEL_VALUE


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
        out["sales_channel"] = HISTORY_SALES_CHANNEL_VALUE
        if preview_granularity:
            out["granularity"] = preview_granularity
        if preview_source:
            out["source"] = preview_source
        if organization_id:
            out["organization_id"] = organization_id
        enriched.append(out)
    return enriched


def granularity_for_process_type(process_type: Optional[str]) -> str:
    gran = PROCESS_TYPE_GRANULARITY.get(process_type or "")
    if not gran:
        raise ValueError(
            f"process_type inválido: {process_type!r}. Use Weekly o Monthly."
        )
    return gran


def get_history_table_meta() -> Dict[str, Any]:
    """Metadatos para wizard/API (misma forma que catálogos)."""
    return {
        "name": HISTORY_TARGET_TABLE,
        "label": "Historial de ventas",
        "target_schema": HISTORY_TARGET_SCHEMA,
        "target_table": HISTORY_TARGET_TABLE,
        "required_columns": list(HISTORY_REQUIRED_COLUMNS),
        "optional_columns": [
            "sales_channel",
            "pieces",
            "source",
        ],
        "required_mapping_columns": list(HISTORY_REQUIRED_MAPPING_COLUMNS),
        "sku_mapping_targets": list(HISTORY_SKU_MAPPING_TARGETS),
        "logical_columns": list(HISTORY_LOGICAL_COLUMNS),
        "unique_keys": list(HISTORY_UNIQUE_KEYS),
        "ignored_file_headers": list(HISTORY_IGNORED_FILE_HEADERS),
        "non_mappable_targets": list(HISTORY_NON_MAPPABLE_TARGETS),
#        "column_aliases": dict(HISTORY_COLUMN_ALIASES),
        "validation_hints": [
            "Destino fijo: public.sales_history",
            "Mapea location_code, sku (o sku_code lógico) y period_start, quantity, pieces",
            f"UPSERT por: organization_id + location_code + sku + period_start + granularity",
            "sales_channel se aplica automáticamente como SELL_IN",
            "granularity: week (Weekly) o month (Monthly) — del tipo de proceso (paso 1)",
            "source: extensión del archivo subido (paso 1)",
            "organization_id se aplica automáticamente del usuario",
        ],
    }

"""Transformaciones y resolución SKU para public.sales_history."""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import polars as pl

from data_staging.catalog.catalog_transforms import (
    format_date_for_storage,
    is_empty_value,
    parse_flexible_datetime,
)
from data_staging.history.history_config import (
    HISTORY_SALES_CHANNEL_VALUE,
    HISTORY_SKU_MAPPING_TARGETS,
    granularity_for_process_type,
    is_valid_sales_channel,
    source_from_filename,
)

logger = logging.getLogger(__name__)


def _normalize_period_start(value: Any) -> Optional[str]:
    """Devuelve period_start como YYYY-MM-DD para validación y carga."""
    return format_date_for_storage(value, date_only=True)


def build_sales_history_id(
    organization_id: str,
    location_code: str,
    sku_key: str,
    period_start: Any,
    granularity: str,
) -> str:
    if isinstance(period_start, datetime):
        period_key = period_start.isoformat()
    elif isinstance(period_start, date):
        period_key = datetime.combine(period_start, datetime.min.time()).isoformat()
    else:
        period_key = str(period_start)
    raw = f"{organization_id}|{location_code}|{sku_key}|{period_key}|{granularity}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    return str(uuid.UUID(digest))


class SkuCodeResolver:
    """Cache organization_id + código SKU → identificador en public.skus (PK dinámica)."""

    def __init__(
        self,
        cursor,
        organization_id: str,
        *,
        pk_column: str = "id",
        code_column: str = "code",
        schema: str = "public",
        table: str = "skus",
    ):
        self._cursor = cursor
        self._organization_id = organization_id
        self._pk_column = pk_column
        self._code_column = code_column
        self._schema = schema
        self._table = table
        self._cache: Dict[str, Optional[str]] = {}

    def resolve(self, sku_code: Any) -> Optional[str]:
        if is_empty_value(sku_code):
            return None
        key = str(sku_code).strip()
        if not key:
            return None
        cache_key = key.lower()
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Identificadores SQL validados por introspección (no input de usuario)
        query = (
            f'SELECT "{self._pk_column}"::text FROM "{self._schema}"."{self._table}" '
            f'WHERE organization_id = %s AND LOWER("{self._code_column}") = LOWER(%s) '
            f"LIMIT 1"
        )
        try:
            self._cursor.execute(query, (self._organization_id, key))
            row = self._cursor.fetchone()
            sku_id = row[0] if row else None
        except Exception as exc:
            logger.error(
                "SKU lookup failed on %s.%s (%s): %s",
                self._schema,
                self._table,
                self._pk_column,
                exc,
            )
            raise
        self._cache[cache_key] = sku_id
        return sku_id


def _resolve_sku_id_from_row(
    record: Dict[str, Any],
    sku_resolver: Optional[SkuCodeResolver],
    *,
    resolve_sku_id: bool,
) -> Optional[str]:
    if not resolve_sku_id:
        return None

    if not is_empty_value(record.get("sku_id")):
        return str(record["sku_id"])

    for key in HISTORY_SKU_MAPPING_TARGETS:
        if key in ("sku_id", "sku"):
            continue
        val = record.get(key)
        if is_empty_value(val) or not sku_resolver:
            continue
        if key == "sku_code":
            resolved = sku_resolver.resolve(val)
            if resolved:
                return resolved

    # Mapeo a columna «sku» en sales_history pero tabla con sku_id: resolver vía catálogo
    if sku_resolver and not is_empty_value(record.get("sku")):
        resolved = sku_resolver.resolve(record.get("sku"))
        if resolved:
            return resolved

    return None


def apply_history_transforms_polars(
    df: pl.DataFrame,
    *,
    organization_id: str,
    process_type: Optional[str] = None,
    source_extension: Optional[str] = None,
    sku_resolver: Optional[SkuCodeResolver] = None,
    resolve_sku_id: bool = False,
) -> pl.DataFrame:
    """
    Enriquece filas mapeadas: conserva columnas mapeadas y rellena id, granularity,
    source, organization_id cuando aplica. No escribe sku_id (columna retirada).
    """
    if df.is_empty():
        return df

    pdf = df.to_pandas()
    rows_out: List[Dict[str, Any]] = []
    default_granularity = (
        granularity_for_process_type(process_type) if process_type else None
    )
    default_source = (source_extension or "").strip().lower() or None

    for row in pdf.to_dict(orient="records"):
        record = dict(row)

        # Normalizar sku_code lógico → columna sku si aplica
        if is_empty_value(record.get("sku")) and not is_empty_value(record.get("sku_code")):
            record["sku"] = record.get("sku_code")

        period_str = _normalize_period_start(record.get("period_start"))
        record["period_start"] = period_str
        period_dt = parse_flexible_datetime(period_str) if period_str else None

        if default_granularity:
            record["granularity"] = default_granularity

        org_id = record.get("organization_id") or organization_id
        if org_id:
            record["organization_id"] = str(org_id)

        if default_source:
            record["source"] = default_source

        # sales_channel fijo SELL_IN (validar antes si venía mapeado desde archivo)
        if "sales_channel" in record and not is_empty_value(record.get("sales_channel")):
            if not is_valid_sales_channel(record.get("sales_channel")):
                record["_sales_channel_invalid"] = record.get("sales_channel")
        record["sales_channel"] = HISTORY_SALES_CHANNEL_VALUE

        sku_key = str(record.get("sku") or record.get("sku_code") or "")
        location_key = str(record.get("location_code") or "")
        if (
            is_empty_value(record.get("id"))
            and period_dt
            and sku_key
            and location_key
            and record.get("granularity")
        ):
            record["id"] = build_sales_history_id(
                str(org_id or organization_id),
                location_key,
                sku_key,
                period_dt,
                str(record["granularity"]),
            )

        rows_out.append(record)

    import pandas as pd

    return pl.from_pandas(pd.DataFrame(rows_out))

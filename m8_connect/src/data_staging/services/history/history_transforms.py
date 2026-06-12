"""Transformaciones y resolución SKU para public.sales_history."""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import polars as pl

from data_staging.services.catalog.catalog_transforms import (
    format_date_for_storage,
    is_empty_value,
    parse_flexible_datetime,
)
from data_staging.services.history.history_config import (
    HISTORY_SALES_CHANNEL_VALUE,
    HISTORY_SKU_MAPPING_TARGETS,
    granularity_for_process_type,
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


def _is_empty_expr(col: str) -> pl.Expr:
    c = pl.col(col)
    return c.is_null() | (c.cast(pl.Utf8, strict=False).str.strip_chars() == "")


def _normalize_period_start_value(value: Any) -> Optional[str]:
    normalized = format_date_for_storage(value, date_only=True)
    if normalized:
        return normalized
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _period_key_for_id_value(value: Any) -> Optional[str]:
    parsed = parse_flexible_datetime(value)
    if parsed:
        return parsed.strftime("%Y-%m-%dT%H:%M:%S")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_period_start_expr(col: str = "period_start") -> pl.Expr:
    return pl.col(col).map_elements(_normalize_period_start_value, return_dtype=pl.Utf8).alias(col)


def _hash_id_batch(batch: pl.Series) -> pl.Series:
    out: List[Optional[str]] = []
    for item in batch.to_list():
        if is_empty_value(item):
            out.append(None)
            continue
        digest = hashlib.sha256(str(item).encode("utf-8")).hexdigest()[:32]
        out.append(str(uuid.UUID(digest)))
    return pl.Series(out, dtype=pl.Utf8)


def _build_id_raw_expr(
    organization_id: str,
    *,
    has_sku_code: bool,
) -> pl.Expr:
    org_expr = (
        pl.when(_is_empty_expr("organization_id"))
        .then(pl.lit(str(organization_id)))
        .otherwise(pl.col("organization_id").cast(pl.Utf8))
    )
    if has_sku_code:
        sku_expr = (
            pl.when(_is_empty_expr("sku"))
            .then(pl.col("sku_code").cast(pl.Utf8, strict=False))
            .otherwise(pl.col("sku").cast(pl.Utf8, strict=False))
        )
    else:
        sku_expr = pl.col("sku").cast(pl.Utf8, strict=False)
    period_key = pl.col("period_start").map_elements(
        _period_key_for_id_value,
        return_dtype=pl.Utf8,
    )
    parts = [
        org_expr,
        pl.col("location_code").cast(pl.Utf8, strict=False),
        sku_expr,
        period_key,
        pl.col("granularity").cast(pl.Utf8, strict=False),
    ]
    return pl.concat_str(parts, separator="|")


def _build_id_from_fields(
    org_id: Any,
    location_code: Any,
    sku: Any,
    sku_code: Any,
    period_start: Any,
    granularity: Any,
    existing_id: Any,
    fallback_org: str,
) -> Optional[str]:
    if not is_empty_value(existing_id):
        return str(existing_id)

    sku_key = str(sku or sku_code or "")
    location_key = str(location_code or "")
    org = str(org_id or fallback_org or "")
    period_str = _normalize_period_start(period_start)
    period_dt = parse_flexible_datetime(period_str) if period_str else None
    gran = str(granularity or "")

    if not period_dt or not sku_key or not location_key or not gran:
        return None
    return build_sales_history_id(org, location_key, sku_key, period_dt, gran)


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
        self._preloaded = False

    def preload(self) -> None:
        """Carga todos los SKUs de la organización en memoria (misma semántica que resolve())."""
        if self._preloaded:
            return
        query = (
            f'SELECT LOWER("{self._code_column}"), "{self._pk_column}"::text '
            f'FROM "{self._schema}"."{self._table}" '
            f"WHERE organization_id = %s"
        )
        try:
            self._cursor.execute(query, (self._organization_id,))
            for code_key, pk_val in self._cursor.fetchall():
                if code_key is None:
                    continue
                normalized = str(code_key).strip().lower()
                if normalized:
                    self._cache[normalized] = pk_val
        except Exception as exc:
            logger.error(
                "SKU preload failed on %s.%s (%s): %s",
                self._schema,
                self._table,
                self._pk_column,
                exc,
            )
            raise
        self._preloaded = True

    def _lookup_cached(self, sku_code: Any) -> Optional[str]:
        if is_empty_value(sku_code):
            return None
        key = str(sku_code).strip()
        if not key:
            return None
        return self._cache.get(key.lower())

    def resolve(self, sku_code: Any) -> Optional[str]:
        if is_empty_value(sku_code):
            return None
        key = str(sku_code).strip()
        if not key:
            return None
        cache_key = key.lower()
        if cache_key in self._cache:
            return self._cache[cache_key]

        if self._preloaded:
            self._cache[cache_key] = None
            return None

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

    def _lookup_batch(self, codes: pl.Series) -> pl.Series:
        cache = self._cache
        out: List[Optional[str]] = []
        for item in codes.to_list():
            if is_empty_value(item):
                out.append(None)
            else:
                out.append(cache.get(str(item).strip().lower()))
        return pl.Series(out, dtype=pl.Utf8)

    def resolve_sku_id_series(
        self,
        df: pl.DataFrame,
        *,
        resolve_sku_id: bool = True,
    ) -> pl.Series:
        """Replica _resolve_sku_id_from_row fila a fila usando cache precargado."""
        if not resolve_sku_id or df.is_empty():
            return pl.Series([None] * df.height, dtype=pl.Utf8)

        self.preload()

        code_lookup: Optional[pl.Expr] = None
        if "sku_code" in df.columns:
            code_lookup = (
                pl.when(_is_empty_expr("sku_code"))
                .then(None)
                .otherwise(pl.col("sku_code").map_batches(self._lookup_batch, return_dtype=pl.Utf8))
            )

        sku_lookup: Optional[pl.Expr] = None
        if "sku" in df.columns:
            sku_lookup = (
                pl.when(_is_empty_expr("sku"))
                .then(None)
                .otherwise(pl.col("sku").map_batches(self._lookup_batch, return_dtype=pl.Utf8))
            )

        candidates = [e for e in (code_lookup, sku_lookup) if e is not None]
        if candidates:
            resolved = pl.coalesce(candidates)
        else:
            resolved = pl.lit(None).cast(pl.Utf8)

        if "sku_id" in df.columns:
            resolved = (
                pl.when(~_is_empty_expr("sku_id"))
                .then(pl.col("sku_id").cast(pl.Utf8, strict=False))
                .otherwise(resolved)
            )

        return df.select(resolved.alias("_sku_id"))["_sku_id"]


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
    aggregated_mode: bool = False,
) -> pl.DataFrame:
    """
    Enriquece filas mapeadas con expresiones Polars (sin bucle pandas).
    aggregated_mode: tras agregación; omite literals ya aplicados por aggregation_service.
    """
    if df.is_empty():
        return df

    default_granularity = (
        granularity_for_process_type(process_type) if process_type else None
    )
    default_source = (source_extension or "").strip().lower() or None
    out = df

    if aggregated_mode:
        if "period_start" in out.columns:
            out = out.with_columns(_normalize_period_start_expr("period_start"))
        id_cols = [
            "organization_id",
            "location_code",
            "sku",
            "sku_code",
            "period_start",
            "granularity",
            "id",
        ]
        present = [c for c in id_cols if c in out.columns]
        if len(present) >= 4:
            from data_staging.config import settings

            vectorized_id_min = int(getattr(settings, "VECTORIZED_ID_MIN_ROWS", 10_000))
            has_existing_id = "id" in out.columns
            if out.height >= vectorized_id_min:
                id_raw = _build_id_raw_expr(
                    organization_id, has_sku_code="sku_code" in out.columns
                )
                out = out.with_columns(id_raw.alias("_id_raw"))
                generated_id = pl.col("_id_raw").map_batches(
                    _hash_id_batch, return_dtype=pl.Utf8
                )
                if has_existing_id:
                    out = out.with_columns(
                        pl.when(_is_empty_expr("id"))
                        .then(generated_id)
                        .otherwise(pl.col("id").cast(pl.Utf8))
                        .alias("id")
                    )
                else:
                    out = out.with_columns(generated_id.alias("id"))
                out = out.drop("_id_raw")
            else:
                out = out.with_columns(
                    pl.struct(present).map_elements(
                        lambda row: _build_id_from_fields(
                            row.get("organization_id"),
                            row.get("location_code"),
                            row.get("sku"),
                            row.get("sku_code"),
                            row.get("period_start"),
                            row.get("granularity"),
                            row.get("id"),
                            organization_id,
                        ),
                        return_dtype=pl.Utf8,
                    ).alias("id")
                )
        if resolve_sku_id and sku_resolver:
            out = out.with_columns(
                sku_resolver.resolve_sku_id_series(out, resolve_sku_id=resolve_sku_id).alias(
                    "sku_id"
                )
            )
        return out

    if "sku_code" in out.columns:
        if "sku" in out.columns:
            out = out.with_columns(
                pl.when(_is_empty_expr("sku"))
                .then(pl.col("sku_code"))
                .otherwise(pl.col("sku"))
                .alias("sku")
            )
        else:
            out = out.with_columns(pl.col("sku_code").alias("sku"))

    if "period_start" in out.columns:
        out = out.with_columns(_normalize_period_start_expr("period_start"))

    if default_granularity:
        out = out.with_columns(pl.lit(default_granularity).alias("granularity"))

    if organization_id:
        if "organization_id" in out.columns:
            out = out.with_columns(
                pl.when(_is_empty_expr("organization_id"))
                .then(pl.lit(str(organization_id)))
                .otherwise(pl.col("organization_id").cast(pl.Utf8))
                .alias("organization_id")
            )
        else:
            out = out.with_columns(pl.lit(str(organization_id)).alias("organization_id"))

    if default_source:
        out = out.with_columns(pl.lit(default_source).alias("source"))

    if "sales_channel" in out.columns:
        normalized_channel = (
            pl.col("sales_channel")
            .cast(pl.Utf8, strict=False)
            .str.strip_chars()
            .str.to_uppercase()
            .str.replace_all("-", "_")
        )
        out = out.with_columns(
            pl.when(~_is_empty_expr("sales_channel") & (normalized_channel != "SELL_IN"))
            .then(pl.col("sales_channel"))
            .otherwise(None)
            .alias("_sales_channel_invalid")
        )
    out = out.with_columns(pl.lit(HISTORY_SALES_CHANNEL_VALUE).alias("sales_channel"))

    id_cols = ["organization_id", "location_code", "sku", "sku_code", "period_start", "granularity", "id"]
    present = [c for c in id_cols if c in out.columns]
    if len(present) >= 4:
        from data_staging.config import settings

        vectorized_id_min = int(getattr(settings, "VECTORIZED_ID_MIN_ROWS", 10_000))
        has_existing_id = "id" in out.columns
        if out.height >= vectorized_id_min:
            id_raw = _build_id_raw_expr(organization_id, has_sku_code="sku_code" in out.columns)
            out = out.with_columns(id_raw.alias("_id_raw"))
            generated_id = pl.col("_id_raw").map_batches(_hash_id_batch, return_dtype=pl.Utf8)
            if has_existing_id:
                out = out.with_columns(
                    pl.when(_is_empty_expr("id"))
                    .then(generated_id)
                    .otherwise(pl.col("id").cast(pl.Utf8))
                    .alias("id")
                )
            else:
                out = out.with_columns(generated_id.alias("id"))
            out = out.drop("_id_raw")
        else:
            out = out.with_columns(
                pl.struct(present).map_elements(
                    lambda row: _build_id_from_fields(
                        row.get("organization_id"),
                        row.get("location_code"),
                        row.get("sku"),
                        row.get("sku_code"),
                        row.get("period_start"),
                        row.get("granularity"),
                        row.get("id"),
                        organization_id,
                    ),
                    return_dtype=pl.Utf8,
                ).alias("id")
            )

    if resolve_sku_id and sku_resolver:
        out = out.with_columns(
            sku_resolver.resolve_sku_id_series(out, resolve_sku_id=resolve_sku_id).alias(
                "sku_id"
            )
        )

    return out

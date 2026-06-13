"""Transformaciones y resolución SKU para public.sales_history."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import polars as pl

from data_staging.services.catalog.catalog_transforms import (
    format_date_for_storage,
    is_empty_value,
)
from data_staging.services.history.history_config import (
    HISTORY_SALES_CHANNEL_VALUE,
    HISTORY_SKU_MAPPING_TARGETS,
)

logger = logging.getLogger(__name__)


def _is_empty_expr(col: str) -> pl.Expr:
    c = pl.col(col)
    return c.is_null() | (c.cast(pl.Utf8, strict=False).str.strip_chars() == "")


def _apply_sales_channel_polars(
    df: pl.DataFrame,
    *,
    validate: bool = True,
    sales_channel_default: Optional[str] = None,
) -> pl.DataFrame:
    """Default configurable cuando falta o viene vacío; rechaza otros valores si validate=True."""
    if df.is_empty():
        return df

    default_val = (sales_channel_default or HISTORY_SALES_CHANNEL_VALUE).strip()
    default_norm = default_val.upper().replace("-", "_")
    out = df
    if validate and "sales_channel" in out.columns:
        normalized_channel = (
            pl.col("sales_channel")
            .cast(pl.Utf8, strict=False)
            .str.strip_chars()
            .str.to_uppercase()
            .str.replace_all("-", "_")
        )
        out = out.with_columns(
            pl.when(~_is_empty_expr("sales_channel") & (normalized_channel != default_norm))
            .then(pl.col("sales_channel"))
            .otherwise(None)
            .alias("_sales_channel_invalid")
        )

    if "sales_channel" in out.columns:
        out = out.with_columns(
            pl.when(_is_empty_expr("sales_channel"))
            .then(pl.lit(default_val))
            .otherwise(pl.col("sales_channel").cast(pl.Utf8, strict=False))
            .alias("sales_channel")
        )
    else:
        out = out.with_columns(pl.lit(default_val).alias("sales_channel"))

    return out


def _normalize_period_start_value(value: Any) -> Optional[str]:
    normalized = format_date_for_storage(value, date_only=True)
    if normalized:
        return normalized
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_period_start_expr(col: str = "period_start") -> pl.Expr:
    return pl.col(col).map_elements(_normalize_period_start_value, return_dtype=pl.Utf8).alias(col)


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
    history_rules: Optional[Dict[str, Any]] = None,
) -> pl.DataFrame:
    """
    Enriquece filas mapeadas con expresiones Polars (sin bucle pandas).
    aggregated_mode: tras agregación; omite literals ya aplicados por aggregation_service.
    """
    if df.is_empty():
        return df

    from data_staging.services.history.history_config import resolve_history_rules

    rules = history_rules or resolve_history_rules()
    sales_channel_default = rules.get("sales_channel_default") or HISTORY_SALES_CHANNEL_VALUE

    out = df

    if aggregated_mode:
        if "period_start" in out.columns:
            out = out.with_columns(_normalize_period_start_expr("period_start"))
        if resolve_sku_id and sku_resolver:
            out = out.with_columns(
                sku_resolver.resolve_sku_id_series(out, resolve_sku_id=resolve_sku_id).alias(
                    "sku_id"
                )
            )
        return _apply_sales_channel_polars(
            out, validate=False, sales_channel_default=sales_channel_default
        )

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

    if process_type:
        from data_staging.services.history.history_config import granularity_for_process_type

        try:
            gran = granularity_for_process_type(process_type)
            if "granularity" in out.columns:
                out = out.with_columns(
                    pl.when(_is_empty_expr("granularity"))
                    .then(pl.lit(gran))
                    .otherwise(pl.col("granularity").cast(pl.Utf8, strict=False))
                    .alias("granularity")
                )
            else:
                out = out.with_columns(pl.lit(gran).alias("granularity"))
        except ValueError:
            pass

    if source_extension:
        src = str(source_extension).strip().lower()
        if src == "parquet":
            src = "csv"
        if "source" in out.columns:
            out = out.with_columns(
                pl.when(_is_empty_expr("source"))
                .then(pl.lit(src))
                .otherwise(pl.col("source").cast(pl.Utf8, strict=False))
                .alias("source")
            )
        else:
            out = out.with_columns(pl.lit(src).alias("source"))

    out = _apply_sales_channel_polars(
        out, validate=True, sales_channel_default=sales_channel_default
    )

    if resolve_sku_id and sku_resolver:
        out = out.with_columns(
            sku_resolver.resolve_sku_id_series(out, resolve_sku_id=resolve_sku_id).alias(
                "sku_id"
            )
        )

    return out

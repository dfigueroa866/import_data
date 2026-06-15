"""Cast Polars columns to PostgreSQL target types for typed Parquet pipelines."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

import polars as pl


def pg_type_category(pg_type: str) -> str:
    """Normalize information_schema data_type to a coarse category."""
    base = (pg_type or "text").lower().split("(")[0].strip()
    if base in ("integer", "bigint", "smallint"):
        return "int"
    if base in ("numeric", "decimal", "real", "double precision"):
        return "float"
    if base == "date":
        return "date"
    if "timestamp" in base:
        return "timestamp"
    if base == "boolean":
        return "bool"
    if base == "uuid":
        return "uuid"
    return "string"


def map_file_headers_to_target_types(
    file_headers: List[str],
    target_column_types: Mapping[str, str],
) -> Dict[str, str]:
    """Map each uploaded file column to a PG type (exact / case-insensitive match, else text)."""
    lower_map = {name.lower(): pg_type for name, pg_type in target_column_types.items()}
    mapped: Dict[str, str] = {}
    for header in file_headers:
        if header in target_column_types:
            mapped[header] = target_column_types[header]
        elif header.lower() in lower_map:
            mapped[header] = lower_map[header.lower()]
        else:
            mapped[header] = "text"
    return mapped


def cast_dataframe_to_target_types(
    df: pl.DataFrame,
    target_column_types: Mapping[str, str],
    *,
    skip_already_typed: bool = False,
) -> pl.DataFrame:
    """Cast present columns to types matching the target table."""
    if df.is_empty() or not target_column_types:
        return df

    out = df
    for col_name, pg_type in target_column_types.items():
        if col_name not in out.columns:
            continue
        if skip_already_typed and _column_matches_target_type(out.get_column(col_name), pg_type):
            continue
        out = _cast_column(out, col_name, pg_type)
    return out


def _column_matches_target_type(series: pl.Series, pg_type: str) -> bool:
    category = pg_type_category(pg_type)
    dtype = series.dtype
    if category == "date":
        return dtype == pl.Date
    if category == "timestamp":
        return dtype in (pl.Datetime, pl.Date)
    if category == "float":
        return dtype in pl.NUMERIC_DTYPES and dtype != pl.Int64
    if category == "int":
        return dtype in (pl.Int64, pl.Int32, pl.Int16, pl.Int8, pl.UInt64, pl.UInt32)
    if category == "bool":
        return dtype == pl.Boolean
    if category == "uuid":
        return dtype == pl.Utf8
    return dtype == pl.Utf8


def _cast_column(df: pl.DataFrame, col: str, pg_type: str) -> pl.DataFrame:
    category = pg_type_category(pg_type)
    series = df.get_column(col)

    if category == "date":
        from data_staging.services.catalog.catalog_transforms import coerce_period_start_to_date

        return coerce_period_start_to_date(df, col)

    if category == "timestamp":
        from data_staging.services.catalog.catalog_transforms import parse_dates_polars_series

        parsed = parse_dates_polars_series(series)
        return df.with_columns(parsed.alias(col))

    if category == "float":
        if series.dtype in pl.NUMERIC_DTYPES:
            return df.with_columns(pl.col(col).cast(pl.Float64, strict=False).alias(col))
        return df.with_columns(
            pl.col(col)
            .cast(pl.Utf8, strict=False)
            .str.strip_chars()
            .str.replace_all(r"[\$,]", "")
            .str.strip_chars()
            .cast(pl.Float64, strict=False)
            .alias(col)
        )

    if category == "int":
        if series.dtype in pl.NUMERIC_DTYPES:
            return df.with_columns(pl.col(col).cast(pl.Int64, strict=False).alias(col))
        return df.with_columns(
            pl.col(col)
            .cast(pl.Utf8, strict=False)
            .str.strip_chars()
            .str.replace_all(r"[\$,]", "")
            .cast(pl.Int64, strict=False)
            .alias(col)
        )

    if category == "bool":
        return df.with_columns(pl.col(col).cast(pl.Boolean, strict=False).alias(col))

    if category == "uuid":
        return df.with_columns(pl.col(col).cast(pl.Utf8, strict=False).alias(col))

    return df.with_columns(pl.col(col).cast(pl.Utf8, strict=False).alias(col))


def fetch_target_column_types_sql(
    conn: Any,
    schema: str,
    table: str,
) -> Dict[str, str]:
    """Load column_name → data_type from information_schema (psycopg2 or SQLAlchemy)."""
    query = """
        SELECT column_name, data_type, character_maximum_length
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position
    """
    cursor = conn.cursor() if hasattr(conn, "cursor") and not hasattr(conn, "execute") else None
    rows = []
    if cursor is not None:
        cursor.execute(query, (schema, table))
        rows = cursor.fetchall()
        cursor.close()
    else:
        from sqlalchemy import text as sa_text

        result = conn.execute(sa_text("""
            SELECT column_name, data_type, character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = :schema AND table_name = :table
            ORDER BY ordinal_position
        """), {"schema": schema, "table": table})
        rows = result.fetchall()

    types: Dict[str, str] = {}
    for row in rows:
        col_name = row[0] if not hasattr(row, "column_name") else row.column_name
        dtype = row[1] if not hasattr(row, "data_type") else row.data_type
        length = row[2] if not hasattr(row, "character_maximum_length") else row.character_maximum_length
        full_type = str(dtype)
        if length:
            full_type = f"{full_type}({length})"
        types[str(col_name)] = full_type
    return types


def sanitize_frame_for_copy(df) -> Any:
    """Prepare a pandas DataFrame for PostgreSQL COPY (safe string serialization)."""
    import pandas as pd

    if df.empty:
        return df
    sub = df.copy()
    for col in sub.columns:
        dtype = sub[col].dtype
        if pd.api.types.is_datetime64_any_dtype(dtype):
            formatted = sub[col].dt.strftime("%Y-%m-%d %H:%M:%S")
            sub[col] = formatted.where(sub[col].notna(), None)
        elif pd.api.types.is_object_dtype(dtype):
            series = sub[col].replace("", None)
            mask = series.notna()
            as_str = series.astype(str)
            as_str = (
                as_str.str.replace("\t", " ", regex=False)
                .str.replace("\n", " ", regex=False)
                .str.replace("\r", " ", regex=False)
            )
            sub[col] = as_str.where(mask, None)
    return sub

"""Bulk promotion helpers: temp staging + COPY + aggregated UPSERT counts."""

from __future__ import annotations

import io
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import pandas as pd
import psycopg2.extensions

from data_staging.services.catalog.catalog_transforms import coalesce_empty_to_none, is_empty_value

_STAGING_TABLE = "batch_promo_staging"


def staging_select_expr(
    column: str,
    data_type: Optional[str],
    *,
    udt_name: Optional[str] = None,
) -> str:
    """Cast a text staging column to the target PostgreSQL column type."""
    raw = f's."{column}"'
    base = f"NULLIF({raw}, '')"
    dt = (data_type or "text").lower().strip()

    if dt in ("text", "character varying", "varchar", "character", "char"):
        return raw
    if dt == "uuid":
        return f"{base}::uuid"
    if dt == "integer":
        return f"{base}::numeric::integer"
    if dt == "bigint":
        return f"{base}::numeric::bigint"
    if dt == "smallint":
        return f"{base}::numeric::smallint"
    if dt == "double precision":
        return f"{base}::double precision"
    if dt == "real":
        return f"{base}::real"
    if dt in ("numeric", "decimal"):
        return f"{base}::numeric"
    if "timestamp" in dt:
        return f"{base}::timestamp"
    if dt == "date":
        return f"{base}::date"
    if dt == "boolean":
        return f"{base}::boolean"
    if dt == "json" or dt == "jsonb":
        return f"{base}::jsonb"
    if dt == "user-defined" and udt_name:
        return f'{base}::"{udt_name}"'
    return raw


def frame_to_tuples(frame: pd.DataFrame, data_cols: Sequence[str]) -> List[tuple]:
    """Build insert tuples from a DataFrame (itertuples, not iterrows)."""
    if frame.empty:
        return []
    sub = frame[list(data_cols)]
    rows: List[tuple] = []
    for row in sub.itertuples(index=False, name=None):
        rows.append(tuple(coalesce_empty_to_none(v) for v in row))
    return rows


def _pg_text_value(val: Any) -> str:
    if is_empty_value(val):
        return "\\N"
    s = str(val).replace("\t", " ").replace("\n", " ").replace("\r", " ")
    return s


def copy_frame_to_staging(
    cursor: psycopg2.extensions.cursor,
    frame: pd.DataFrame,
    data_cols: Sequence[str],
    staging_cols: Sequence[str],
) -> int:
    """COPY chunk rows into the temp staging table."""
    buffer = io.StringIO()
    count = 0
    for row in frame[list(data_cols)].itertuples(index=False, name=None):
        cells = [_pg_text_value(v) for v in row]
        buffer.write("\t".join(cells) + "\n")
        count += 1
    if count == 0:
        return 0
    buffer.seek(0)
    cols_str = ", ".join(f'"{c}"' for c in staging_cols)
    cursor.copy_expert(
        f'COPY {_STAGING_TABLE} ({cols_str}) FROM STDIN WITH (FORMAT text, NULL \'\\N\')',
        buffer,
    )
    return count


def ensure_staging_table(
    cursor: psycopg2.extensions.cursor,
    staging_cols: Sequence[str],
) -> None:
    col_defs = ", ".join(f'"{c}" text' for c in staging_cols)
    cursor.execute(
        f"""
        CREATE TEMP TABLE IF NOT EXISTS {_STAGING_TABLE} (
            {col_defs}
        ) ON COMMIT DELETE ROWS
        """
    )
    cursor.execute(f"TRUNCATE {_STAGING_TABLE}")


def build_upsert_from_staging_sql(
    target_schema: str,
    target_table: str,
    insert_cols: List[str],
    staging_cols: Sequence[str],
    conflict_clause: str,
    *,
    include_imported_at: bool,
    db_columns: Optional[Mapping[str, str]] = None,
    db_udt_names: Optional[Mapping[str, str]] = None,
) -> str:
    """INSERT ... SELECT from staging with optional UPSERT and aggregated RETURNING."""
    db_columns = db_columns or {}
    db_udt_names = db_udt_names or {}
    select_parts = [
        staging_select_expr(
            col,
            db_columns.get(col),
            udt_name=db_udt_names.get(col),
        )
        for col in staging_cols
    ]
    if include_imported_at:
        select_parts.append("NOW()")

    insert_cols_str = ", ".join(insert_cols)
    select_str = ", ".join(select_parts)

    base = f"""
        INSERT INTO {target_schema}.{target_table} ({insert_cols_str})
        SELECT {select_str}
        FROM {_STAGING_TABLE} s
        {conflict_clause}
    """.strip()

    upper = (conflict_clause or "").upper()
    if "DO UPDATE" in upper:
        return f"""
        WITH upserted AS (
            {base}
            RETURNING (xmax = 0) AS is_insert
        )
        SELECT
            COUNT(*)::int,
            COUNT(*) FILTER (WHERE is_insert)::int,
            COUNT(*) FILTER (WHERE NOT is_insert)::int
        FROM upserted
        """
    if conflict_clause and "DO NOTHING" in upper:
        return f"""
        WITH upserted AS (
            {base}
            RETURNING true AS is_insert
        )
        SELECT
            COUNT(*)::int,
            COUNT(*)::int,
            0::int
        FROM upserted
        """
    return f"""
    WITH inserted AS (
        {base}
        RETURNING 1
    )
    SELECT COUNT(*)::int, COUNT(*)::int, 0::int FROM inserted
    """


def build_values_upsert_sql(
    insert_query: str,
    conflict_clause: str,
) -> str:
    """Wrap execute_values INSERT with aggregated RETURNING counts."""
    inner = insert_query.rstrip()
    upper = (conflict_clause or "").upper()
    if "DO UPDATE" in upper:
        return f"""
        WITH upserted AS (
            {inner}
            RETURNING (xmax = 0) AS is_insert
        )
        SELECT
            COUNT(*)::int,
            COUNT(*) FILTER (WHERE is_insert)::int,
            COUNT(*) FILTER (WHERE NOT is_insert)::int
        FROM upserted
        """
    if conflict_clause and "DO NOTHING" in upper:
        return f"""
        WITH upserted AS (
            {inner}
            RETURNING true AS is_insert
        )
        SELECT
            COUNT(*)::int,
            COUNT(*)::int,
            0::int
        FROM upserted
        """
    return f"""
    WITH inserted AS (
        {inner}
        RETURNING 1
    )
    SELECT COUNT(*)::int, COUNT(*)::int, 0::int FROM inserted
    """

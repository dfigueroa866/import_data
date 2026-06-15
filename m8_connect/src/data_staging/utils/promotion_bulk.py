"""Bulk promotion helpers: temp staging + COPY + aggregated UPSERT counts."""

from __future__ import annotations

import io
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import pandas as pd
import psycopg2.extensions

try:
    import pyarrow as pa
except ImportError:  # pragma: no cover
    pa = None  # type: ignore[assignment]

from data_staging.services.catalog.catalog_transforms import coalesce_empty_to_none, is_empty_value

_STAGING_TABLE = "batch_promo_staging"
_STAGING_TABLE_PERSISTENT = "batch_promo_staging_acc"


def staging_select_expr(
    column: str,
    data_type: Optional[str],
    *,
    udt_name: Optional[str] = None,
    source_alias: str = "s",
) -> str:
    """Cast a text staging column to the target PostgreSQL column type."""
    raw = f'{source_alias}."{column}"'
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


def _write_copy_buffer(
    cursor: psycopg2.extensions.cursor,
    buffer: io.StringIO,
    staging_cols: Sequence[str],
    *,
    table: str = _STAGING_TABLE,
) -> int:
    payload = buffer.getvalue()
    if not payload:
        return 0
    buffer.seek(0)
    cols_str = ", ".join(f'"{c}"' for c in staging_cols)
    cursor.copy_expert(
        f'COPY {table} ({cols_str}) FROM STDIN WITH (FORMAT text, NULL \'\\N\')',
        buffer,
    )
    return payload.count("\n")


def copy_arrow_batch_to_staging(
    cursor: psycopg2.extensions.cursor,
    batch: "pa.RecordBatch",
    data_cols: Sequence[str],
    staging_cols: Sequence[str],
    *,
    table: str = _STAGING_TABLE,
) -> int:
    """COPY PyArrow RecordBatch rows into the temp staging table via pandas vectorized path."""
    if pa is None or batch is None or batch.num_rows == 0:
        return 0
    cols_in_batch = [c for c in data_cols if batch.schema.get_field_index(c) >= 0]
    if not cols_in_batch:
        raise ValueError(f"None of {list(data_cols)} found in Parquet batch schema")
    frame = batch.select(cols_in_batch).to_pandas()
    return copy_frame_to_staging(cursor, frame, cols_in_batch, staging_cols, table=table)


def copy_frame_to_staging(
    cursor: psycopg2.extensions.cursor,
    frame: pd.DataFrame,
    data_cols: Sequence[str],
    staging_cols: Sequence[str],
    *,
    table: str = _STAGING_TABLE,
) -> int:
    """COPY pandas chunk rows into the temp staging table (vectorized via to_csv)."""
    if frame.empty:
        return 0
    from data_staging.utils.parquet_typing import sanitize_frame_for_copy

    sub = sanitize_frame_for_copy(frame[list(data_cols)].copy())
    buffer = io.StringIO()
    sub.to_csv(buffer, sep="\t", index=False, header=False, na_rep="\\N")
    return _write_copy_buffer(cursor, buffer, staging_cols, table=table)


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


def ensure_staging_table_persistent(
    cursor: psycopg2.extensions.cursor,
    staging_cols: Sequence[str],
) -> None:
    """Create accumulator staging table that survives commits (no ON COMMIT DELETE ROWS)."""
    col_defs = ", ".join(f'"{c}" text' for c in staging_cols)
    cursor.execute(
        f"""
        CREATE TEMP TABLE IF NOT EXISTS {_STAGING_TABLE_PERSISTENT} (
            {col_defs}
        )
        """
    )
    cursor.execute(f"TRUNCATE {_STAGING_TABLE_PERSISTENT}")


def parse_conflict_cols(conflict_clause: str) -> List[str]:
    """Extract conflict column names from an ON CONFLICT (...) clause."""
    m = re.search(r'ON\s+CONFLICT\s*\(([^)]+)\)', conflict_clause, re.IGNORECASE)
    if not m:
        return []
    return [c.strip().strip('"') for c in m.group(1).split(',')]


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
    staging_table: str = _STAGING_TABLE,
    order_by_cols: Optional[List[str]] = None,
    count_split: bool = True,
) -> str:
    """INSERT ... SELECT from staging with optional UPSERT and aggregated RETURNING.

    order_by_cols: sort staging rows by these columns before insert so B-tree
                   leaf pages are accessed sequentially (major I/O saving on large tables).
    count_split:   when False, omit the RETURNING CTE — caller reads cursor.rowcount.
    """
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

    # ORDER BY conflict key → sequential B-tree access instead of random lookups
    order_clause = ""
    if order_by_cols:
        order_clause = "ORDER BY " + ", ".join(f's."{c}"' for c in order_by_cols)

    base = f"""
        INSERT INTO {target_schema}.{target_table} ({insert_cols_str})
        SELECT {select_str}
        FROM {staging_table} s
        {order_clause}
        {conflict_clause}
    """.strip()

    if not count_split:
        return base

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


def build_upsert_from_staging_batch_sql(
    target_schema: str,
    target_table: str,
    insert_cols: List[str],
    staging_cols: Sequence[str],
    conflict_clause: str,
    *,
    batch_limit: int,
    include_imported_at: bool,
    db_columns: Optional[Mapping[str, str]] = None,
    db_udt_names: Optional[Mapping[str, str]] = None,
    staging_table: str = _STAGING_TABLE_PERSISTENT,
    order_by_cols: Optional[List[str]] = None,
    count_split: bool = True,
) -> str:
    """UPSERT a limited batch from persistent staging, then delete processed rows.

    Uses ctid to select and remove rows so the staging table shrinks incrementally.
    """
    if batch_limit <= 0:
        raise ValueError("batch_limit must be positive")

    db_columns = db_columns or {}
    db_udt_names = db_udt_names or {}
    order_cols = order_by_cols or parse_conflict_cols(conflict_clause)
    order_clause = ""
    if order_cols:
        order_clause = "ORDER BY " + ", ".join(f's."{c}"' for c in order_cols)

    staging_col_list = ", ".join(f's."{c}"' for c in staging_cols)
    select_parts = [
        staging_select_expr(
            col,
            db_columns.get(col),
            udt_name=db_udt_names.get(col),
            source_alias="b",
        )
        for col in staging_cols
    ]
    if include_imported_at:
        select_parts.append("NOW()")

    insert_cols_str = ", ".join(insert_cols)
    select_str = ", ".join(select_parts)

    insert_body = f"""
        INSERT INTO {target_schema}.{target_table} ({insert_cols_str})
        SELECT {select_str}
        FROM batch b
        {conflict_clause}
    """.strip()

    if not count_split:
        return f"""
        WITH batch AS (
            SELECT ctid, {staging_col_list}
            FROM {staging_table} s
            {order_clause}
            LIMIT {int(batch_limit)}
        ),
        upserted AS (
            {insert_body}
        ),
        deleted AS (
            DELETE FROM {staging_table} d
            USING batch b
            WHERE d.ctid = b.ctid
        )
        SELECT
            (SELECT COUNT(*)::int FROM batch),
            (SELECT COUNT(*)::int FROM batch),
            0::int
        """

    upper = (conflict_clause or "").upper()
    if "DO UPDATE" in upper:
        return f"""
        WITH batch AS (
            SELECT ctid, {staging_col_list}
            FROM {staging_table} s
            {order_clause}
            LIMIT {int(batch_limit)}
        ),
        upserted AS (
            {insert_body}
            RETURNING (xmax = 0) AS is_insert
        ),
        deleted AS (
            DELETE FROM {staging_table} d
            USING batch b
            WHERE d.ctid = b.ctid
        )
        SELECT
            COUNT(*)::int,
            COUNT(*) FILTER (WHERE is_insert)::int,
            COUNT(*) FILTER (WHERE NOT is_insert)::int
        FROM upserted
        """
    if conflict_clause and "DO NOTHING" in upper:
        return f"""
        WITH batch AS (
            SELECT ctid, {staging_col_list}
            FROM {staging_table} s
            {order_clause}
            LIMIT {int(batch_limit)}
        ),
        upserted AS (
            {insert_body}
            RETURNING true AS is_insert
        ),
        deleted AS (
            DELETE FROM {staging_table} d
            USING batch b
            WHERE d.ctid = b.ctid
        )
        SELECT
            COUNT(*)::int,
            COUNT(*)::int,
            0::int
        FROM upserted
        """
    return f"""
    WITH batch AS (
        SELECT ctid, {staging_col_list}
        FROM {staging_table} s
        {order_clause}
        LIMIT {int(batch_limit)}
    ),
    upserted AS (
        {insert_body}
        RETURNING 1
    ),
    deleted AS (
        DELETE FROM {staging_table} d
        USING batch b
        WHERE d.ctid = b.ctid
    )
    SELECT COUNT(*)::int, COUNT(*)::int, 0::int FROM upserted
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

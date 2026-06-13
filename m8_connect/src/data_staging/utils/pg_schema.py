"""PostgreSQL schema introspection (columns, primary keys)."""

from __future__ import annotations

from typing import Any, Dict, List, Set

from sqlalchemy import text
from sqlalchemy.orm import Session

_TABLE_COLUMNS_SQL = text("""
    SELECT column_name, data_type, is_nullable, column_default
    FROM information_schema.columns
    WHERE table_schema = :schema AND table_name = :table
    ORDER BY ordinal_position
""")

_PG_PRIMARY_KEY_COLUMNS_SQL = text("""
    SELECT a.attname AS column_name
    FROM pg_index i
    JOIN pg_class c ON c.oid = i.indrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
    WHERE i.indisprimary
      AND n.nspname = :schema
      AND c.relname = :table
      AND a.attnum > 0
      AND NOT a.attisdropped
""")

_INFO_SCHEMA_PK_SQL = text("""
    SELECT kcu.column_name
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON tc.constraint_catalog = kcu.constraint_catalog
     AND tc.constraint_schema = kcu.constraint_schema
     AND tc.constraint_name = kcu.constraint_name
    WHERE tc.constraint_type = 'PRIMARY KEY'
      AND tc.table_schema = :schema
      AND tc.table_name = :table
""")


def fetch_primary_key_column_names(db: Session, schema: str, table: str) -> Set[str]:
    """Primary key column names from pg_catalog (fallback: information_schema)."""
    pk_rows = db.execute(
        _PG_PRIMARY_KEY_COLUMNS_SQL,
        {"schema": schema, "table": table},
    ).fetchall()
    if pk_rows:
        return {str(r.column_name) for r in pk_rows}

    fallback = db.execute(
        _INFO_SCHEMA_PK_SQL,
        {"schema": schema, "table": table},
    ).fetchall()
    return {str(r.column_name) for r in fallback}


def fetch_table_columns(db: Session, schema: str, table: str) -> List[Dict[str, Any]]:
    """Column metadata for a table, including is_primary_key from the live DB."""
    rows = db.execute(_TABLE_COLUMNS_SQL, {"schema": schema, "table": table}).fetchall()
    if not rows:
        return []

    pk_names = fetch_primary_key_column_names(db, schema, table)
    return [
        {
            "name": r.column_name,
            "type": r.data_type,
            "nullable": r.is_nullable == "YES",
            "default": r.column_default,
            "is_primary_key": r.column_name in pk_names,
        }
        for r in rows
    ]

"""Tests for PostgreSQL schema introspection helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

from data_staging.utils.pg_schema import fetch_primary_key_column_names, fetch_table_columns


def test_fetch_primary_key_column_names_uses_pg_catalog_first():
    db = MagicMock()
    db.execute.side_effect = [
        MagicMock(fetchall=lambda: [MagicMock(column_name="location_id")]),
    ]
    pk = fetch_primary_key_column_names(db, "public", "locations")
    assert pk == {"location_id"}
    assert db.execute.call_count == 1


def test_fetch_primary_key_column_names_falls_back_to_information_schema():
    db = MagicMock()
    db.execute.side_effect = [
        MagicMock(fetchall=lambda: []),
        MagicMock(fetchall=lambda: [MagicMock(column_name="sku_id")]),
    ]
    pk = fetch_primary_key_column_names(db, "public", "skus")
    assert pk == {"sku_id"}
    assert db.execute.call_count == 2


def test_fetch_table_columns_marks_primary_key():
    db = MagicMock()
    db.execute.side_effect = [
        MagicMock(
            fetchall=lambda: [
                MagicMock(
                    column_name="location_id",
                    data_type="uuid",
                    is_nullable="NO",
                    column_default="gen_random_uuid()",
                ),
                MagicMock(
                    column_name="code",
                    data_type="character varying",
                    is_nullable="NO",
                    column_default=None,
                ),
            ]
        ),
        MagicMock(fetchall=lambda: [MagicMock(column_name="location_id")]),
    ]
    cols = fetch_table_columns(db, "public", "locations")
    assert cols[0]["name"] == "location_id"
    assert cols[0]["is_primary_key"] is True
    assert cols[1]["is_primary_key"] is False

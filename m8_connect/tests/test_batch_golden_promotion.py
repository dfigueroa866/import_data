"""Promotion UPSERT clause regression (offline)."""

from __future__ import annotations

from data_staging.workers.promotion_worker import _catalog_upsert_clause


def test_history_upsert_updates_quantity_not_keys():
    conflict = [
        "organization_id",
        "location_code",
        "sku",
        "period_start",
        "granularity",
    ]
    insert_cols = conflict + ["quantity", "pieces", "source", "sales_channel", "id"]
    clause = _catalog_upsert_clause("history", insert_cols, conflict)
    assert "ON CONFLICT" in clause
    assert '"sku"' in clause
    assert "quantity" in clause
    assert "pieces" in clause
    update_part = clause.split("DO UPDATE SET")[-1]
    assert "organization_id" not in update_part
    assert '"sku"' not in update_part

"""Regression: UPSERT insert/update counts must use xmax split on every batch."""

from __future__ import annotations

from data_staging.workers.promotion_worker import _uses_upsert_update


def test_upsert_update_clause_enables_per_batch_count_split():
    clause = (
        'ON CONFLICT ("organization_id", "location_code", "sku", "period_start", "granularity") '
        'DO UPDATE SET "quantity" = EXCLUDED."quantity"'
    )
    assert _uses_upsert_update(clause) is True


def test_plain_insert_does_not_use_count_split():
    assert _uses_upsert_update("") is False
    assert _uses_upsert_update("ON CONFLICT DO NOTHING") is False

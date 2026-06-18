"""Tests for organization-scoped SKU/location FK validation in history loads."""

from __future__ import annotations

import json

import polars as pl


def test_org_scoped_fk_rejects_sku_from_other_organization():
    from data_staging.services.history.history_chunk_validation import (
        validate_history_chunk_vectorized,
    )

    df = pl.DataFrame(
        {
            "period_start": ["2024-01-15", "2024-01-16"],
            "quantity": [1.0, 2.0],
            "pieces": [0, 0],
            "location_code": ["LOC-A", "LOC-B"],
            "sku": ["sku-org-b", "sku-org-a"],
        }
    )
    fk = {
        "__valid_skus__": {"sku-org-a"},
        "__valid_locations__": {"loc-a", "loc-b"},
        "__fk_org_scoped__": True,
    }
    result = validate_history_chunk_vectorized(
        df,
        batch_id="batch-org-a",
        chunk_idx=0,
        chunk_size=1000,
        foreign_keys_data=fk,
    )

    assert result.passed_df.height == 1
    assert result.passed_df["sku"][0] == "sku-org-a"
    assert len(result.failed_records) == 1
    errors = json.loads(result.failed_records[0]["error_details"])["errors"]
    assert any("no existe en la tabla de productos" in e for e in errors)


def test_org_scoped_fk_rejects_all_skus_when_org_catalog_empty():
    from data_staging.services.history.history_chunk_validation import (
        validate_history_chunk_vectorized,
    )

    df = pl.DataFrame(
        {
            "period_start": ["2024-01-15"],
            "quantity": [1.0],
            "pieces": [0],
            "location_code": ["LOC-A"],
            "sku": ["any-sku"],
        }
    )
    fk = {
        "__valid_skus__": set(),
        "__valid_locations__": set(),
        "__fk_org_scoped__": True,
    }
    result = validate_history_chunk_vectorized(
        df,
        batch_id="batch-new-org",
        chunk_idx=0,
        chunk_size=1000,
        foreign_keys_data=fk,
    )

    assert result.passed_df.is_empty()
    assert len(result.failed_records) == 1
    errors = json.loads(result.failed_records[0]["error_details"])["errors"]
    assert any("no existe en la tabla de productos" in e for e in errors)
    assert any("no existe en la tabla de ubicaciones" in e for e in errors)


def test_load_org_scoped_fk_sets_filters_by_organization():
    from data_staging.services.history.org_reference_data import load_org_scoped_fk_sets

    class FakeCursor:
        def __init__(self):
            self.queries = []

        def execute(self, query, params=None):
            self.queries.append((query, params))
            if "public.skus" in query:
                org = params[0]
                rows = {
                    "org-a": [("sku-a",)],
                    "org-b": [("sku-b",)],
                }
                self._rows = rows.get(org, [])
            elif "location" in query.lower():
                org = params[0]
                rows = {
                    "org-a": [("loc-a",)],
                    "org-b": [("loc-b",)],
                }
                self._rows = rows.get(org, [])

        def fetchall(self):
            return self._rows

    cursor = FakeCursor()
    cursor._sku_code_col = "code"

    from data_staging.services.history import org_reference_data as mod

    original_detect = mod.detect_skus_code_column
    original_cols = mod.table_columns
    mod.detect_skus_code_column = lambda c, s, t: "code"
    mod.table_columns = lambda c, s, t: {"organization_id", "code"}
    try:
        result = load_org_scoped_fk_sets(cursor, "org-a")
    finally:
        mod.detect_skus_code_column = original_detect
        mod.table_columns = original_cols

    assert result["__fk_org_scoped__"] is True
    assert result["__valid_skus__"] == {"sku-a"}
    assert result["__valid_locations__"] == {"loc-a"}
    org_filters = [params for query, params in cursor.queries if params]
    assert all(params[0] == "org-a" for params in org_filters)

"""Config-driven catalog required targets and promotion preflight."""

from __future__ import annotations

import pytest
import polars as pl

from data_staging.services.catalog.catalog_registry import catalog_required_targets
from data_staging.utils.mapping_helpers import apply_chunk_column_mapping
from data_staging.utils.vectorized_validation import validate_chunk_vectorized
from data_staging.workers.promotion_worker import (
    _assert_catalog_required_columns_present,
    _parquet_promotion_columns,
    _resolve_catalog_conflict_columns,
    catalog_targets_from_validated_file,
)


def test_catalog_required_targets_unions_and_excludes_system():
    entry = {
        "required_columns": ["organization_id", "foo", "bar"],
        "required_mapping_columns": ["bar", "baz"],
        "non_mappable_targets": ["sku_id"],
    }
    assert catalog_required_targets(entry) == ["foo", "bar", "baz"]


def test_catalog_required_targets_empty_entry():
    assert catalog_required_targets(None) == []
    assert catalog_required_targets({}) == []


def test_apply_chunk_omits_target_without_source_or_default():
    df = pl.DataFrame({"code": ["A"]})
    mapping = {
        "code": {"source": "code"},
        "state": {"source": None, "default": ""},
        "city": {"source": "missing_col"},
    }
    out = apply_chunk_column_mapping(df, column_mapping=mapping)
    assert "code" in out.columns
    assert "state" not in out.columns
    assert "city" not in out.columns


def test_validate_chunk_rejects_missing_config_required(monkeypatch):
    fake_entry = {
        "name": "demo",
        "required_columns": ["foo", "bar"],
        "required_mapping_columns": [],
        "non_mappable_targets": [],
        "enums": {},
    }

    monkeypatch.setattr(
        "data_staging.services.catalog.catalog_registry.get_catalog_table",
        lambda name: fake_entry if name == "demo" else None,
    )
    monkeypatch.setattr(
        "data_staging.services.catalog.catalog_transforms.validate_catalog_row_enums",
        lambda row, table: [],
    )

    df = pl.DataFrame({"foo": ["x"], "other": ["y"]})
    result = validate_chunk_vectorized(
        df,
        batch_id="b1",
        chunk_idx=0,
        chunk_size=100,
        catalog_table="demo",
    )
    assert result.passed_df.is_empty()
    assert len(result.failed_records) == 1
    errors = str(result.failed_records[0].get("error_details") or "")
    assert "bar" in errors


def test_catalog_targets_from_validated_file_excludes_batch_columns():
    cols = catalog_targets_from_validated_file(
        [
            "sku",
            "brand",
            "attr_1",
            "_batch_id_",
            "_source_row_number_",
            "sku",  # duplicate
        ]
    )
    assert cols == ["sku", "brand", "attr_1"]
    assert not any(c.startswith("_") for c in cols)


def test_parquet_promotion_includes_default_filled_columns():
    """Validated file columns (incl. defaults) promote when allowlisted; batch cols skipped."""
    file_cols = [
        "sku",
        "name",
        "brand",
        "attr_1",
        "_batch_id_",
        "_source_row_number_",
    ]
    allow = ["sku", "name", "brand", "attr_1", "organization_id"]
    assert _parquet_promotion_columns(file_cols, allow) == [
        "sku",
        "name",
        "brand",
        "attr_1",
    ]


def test_assert_catalog_required_columns_present(monkeypatch):
    monkeypatch.setattr(
        "data_staging.services.catalog.catalog_registry.get_catalog_table",
        lambda name: {
            "required_columns": ["code", "state"],
            "required_mapping_columns": [],
            "non_mappable_targets": [],
        },
    )
    _assert_catalog_required_columns_present("location", {"code", "state", "name"})
    with pytest.raises(ValueError, match="state"):
        _assert_catalog_required_columns_present("location", {"code", "name"})


def test_resolve_catalog_conflict_requires_unique_keys(monkeypatch):
    monkeypatch.setattr(
        "data_staging.services.catalog.catalog_registry.get_catalog_table",
        lambda name: {"unique_keys": []},
    )
    with pytest.raises(ValueError, match="unique_keys"):
        _resolve_catalog_conflict_columns(
            "location",
            {},
            {"organization_id": "uuid", "code": "text"},
            {"organization_id": "organization_id", "code": "code"},
            {"organization_id", "code"},
            [["organization_id", "code"]],
        )


def test_resolve_catalog_conflict_uses_config_unique_keys(monkeypatch):
    monkeypatch.setattr(
        "data_staging.services.catalog.catalog_registry.get_catalog_table",
        lambda name: {"unique_keys": ["organization_id", "code"]},
    )
    picked = _resolve_catalog_conflict_columns(
        "location",
        {},
        {"organization_id": "uuid", "code": "text"},
        {"organization_id": "organization_id", "code": "code"},
        {"organization_id", "code", "name"},
        [["organization_id", "code"]],
    )
    assert picked == ["organization_id", "code"]


def test_pick_upsert_prefers_exact_sku_pk_over_composite():
    """unique_keys=['sku'] must bind ON CONFLICT to skus_pk, not (organization_id, sku)."""
    from data_staging.services.history.history_schema import pick_upsert_conflict_columns

    db = {"organization_id": "organization_id", "sku": "sku", "name": "name"}
    picked = pick_upsert_conflict_columns(
        ["sku"],
        {"organization_id", "sku", "name"},
        [["sku"], ["organization_id", "sku"]],
        lambda key: db.get(key),
    )
    assert picked == ["sku"]

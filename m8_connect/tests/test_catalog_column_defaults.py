"""Catalog configurable column defaults."""

from __future__ import annotations

import pandas as pd

from data_staging.services.catalog.catalog_registry import (
    catalog_column_defaults,
    catalog_required_targets,
    catalog_required_targets_needing_mapping,
)


def test_catalog_column_defaults_excludes_system_and_empty():
    entry = {
        "non_mappable_targets": ["sku_id", "created_at"],
        "defaults": {
            "attr_1": "N/A",
            "organization_id": "should-skip",
            "sku_id": "should-skip",
            "brand": "  ",
            "vendor_id": "NONE",
        },
    }
    assert catalog_column_defaults(entry) == {"attr_1": "N/A", "vendor_id": "NONE"}


def test_catalog_required_targets_needing_mapping_skips_defaulted():
    entry = {
        "required_columns": ["sku", "name", "attr_1"],
        "required_mapping_columns": ["status"],
        "non_mappable_targets": [],
        "defaults": {"attr_1": "N/A"},
    }
    assert catalog_required_targets(entry) == ["sku", "name", "attr_1", "status"]
    assert catalog_required_targets_needing_mapping(entry) == ["sku", "name", "status"]


def test_apply_catalog_transforms_fills_missing_and_empty(monkeypatch):
    from data_staging.services.catalog import catalog_transforms as ct

    fake = {
        "name": "demo",
        "defaults": {"attr_1": "N/A", "attr_2": "X"},
        "non_mappable_targets": [],
        "enums": {},
    }

    monkeypatch.setattr(ct, "get_catalog_table", lambda name: fake)
    monkeypatch.setattr(ct, "load_full_config", lambda name: {"transformation_rules": []})
    monkeypatch.setattr(ct, "catalog_column_defaults", lambda entry: {"attr_1": "N/A", "attr_2": "X"})

    pdf = pd.DataFrame({"sku": ["A", "B"], "attr_1": ["keep", None]})
    out = ct.apply_catalog_transforms(pdf, "demo")
    assert list(out["attr_1"]) == ["keep", "N/A"]
    assert list(out["attr_2"]) == ["X", "X"]
    assert list(out["sku"]) == ["A", "B"]

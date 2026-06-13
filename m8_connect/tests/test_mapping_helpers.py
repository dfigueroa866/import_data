"""Tests for wizard virtual mapping key helpers."""

from __future__ import annotations

from data_staging.services.history.history_validation import convert_wizard_column_mapping
from data_staging.utils.mapping_helpers import (
    apply_worker_mapping_defaults,
    is_virtual_mapping_key,
    is_wizard_virtual_mapping,
)
import polars as pl


def test_is_virtual_mapping_key_fixed_prefix():
    assert is_virtual_mapping_key("__fixed_organization_id__")
    assert is_virtual_mapping_key("__fixed_granularity__")


def test_is_virtual_mapping_key_manual_prefix():
    assert is_virtual_mapping_key("__manual__1700000000_abc__")


def test_is_virtual_mapping_key_rejects_file_columns():
    assert not is_virtual_mapping_key("sku")
    assert not is_virtual_mapping_key("")
    assert not is_virtual_mapping_key(None)


def test_is_wizard_virtual_mapping_manual_flag():
    assert is_wizard_virtual_mapping(
        "custom_key",
        {"target": "pieces", "default_value": "1", "is_manual": True},
    )


def test_convert_wizard_column_mapping_manual_pieces():
    wizard = {
        "location": {"target": "location_code"},
        "sku_col": {"target": "sku"},
        "date_col": {"target": "period_start"},
        "qty_col": {"target": "quantity"},
        "__manual__abc__": {
            "target": "pieces",
            "default_value": "1",
            "is_manual": True,
        },
    }
    toggles = {k: True for k in wizard}

    column_mapping, selected = convert_wizard_column_mapping(wizard, toggles)

    assert selected == ["location", "sku_col", "date_col", "qty_col"]
    assert column_mapping["pieces"] == {"source": None, "default": "1"}


def test_apply_worker_mapping_defaults_fills_missing_column():
    df = pl.DataFrame({"sku": ["A"], "quantity": [2.0]})
    mapping = {"pieces": {"source": None, "default": "1"}}

    out = apply_worker_mapping_defaults(df, mapping)

    assert "pieces" in out.columns
    assert out["pieces"].to_list() == ["1"]

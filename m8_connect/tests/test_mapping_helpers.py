"""Tests for wizard virtual mapping key helpers."""

from __future__ import annotations

import json
from datetime import date

from data_staging.services.history.history_validation import convert_wizard_column_mapping
from data_staging.utils.mapping_helpers import (
    apply_worker_mapping_defaults,
    is_metadata_driven_fixed_key,
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


def test_is_metadata_driven_fixed_key():
    assert is_metadata_driven_fixed_key("__fixed_organization_id__")
    assert is_metadata_driven_fixed_key("__fixed_granularity__")
    assert is_metadata_driven_fixed_key("__fixed_source__")
    assert not is_metadata_driven_fixed_key("__fixed_sales_channel__")


def test_convert_wizard_column_mapping_skips_metadata_driven_fixed():
    wizard = {
        "qty_col": {"target": "quantity"},
        "__fixed_granularity__": {
            "target": "granularity",
            "is_fixed": True,
            "from_process_type": True,
        },
        "__fixed_source__": {
            "target": "source",
            "is_fixed": True,
            "from_source_file": True,
        },
        "__fixed_organization_id__": {
            "target": "organization_id",
            "is_fixed": True,
            "from_organization_id": True,
        },
        "__fixed_sales_channel__": {
            "target": "sales_channel",
            "default_value": "SELL_IN",
            "is_fixed": True,
        },
    }
    toggles = {k: True for k in wizard}

    column_mapping, selected = convert_wizard_column_mapping(wizard, toggles)

    assert selected == ["qty_col"]
    assert "granularity" not in column_mapping
    assert "source" not in column_mapping
    assert "organization_id" not in column_mapping
    assert column_mapping["sales_channel"] == {"source": None, "default": "SELL_IN"}


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


def test_history_period_start_accepts_iso_date_only():
    from data_staging.services.history.history_chunk_validation import (
        validate_history_chunk_vectorized,
    )

    df = pl.DataFrame(
        {
            "period_start": ["2024-01-15", "20240115", "2024-13-40"],
            "quantity": [1.0, 2.0, 3.0],
            "pieces": [0, 0, 0],
            "location_code": ["A", "B", "C"],
            "sku": ["s1", "s2", "s3"],
        }
    )
    fk = {
        "__valid_skus__": {"s1", "s2", "s3"},
        "__valid_locations__": {"a", "b", "c"},
    }
    result = validate_history_chunk_vectorized(
        df,
        batch_id="b",
        chunk_idx=0,
        chunk_size=1000,
        foreign_keys_data=fk,
    )

    assert result.passed_df.height == 1
    assert result.passed_df["period_start"].dtype == pl.Date
    assert result.passed_df["period_start"][0] == date(2024, 1, 15)
    assert len(result.failed_records) == 2
    errors = " ".join(
        json.loads(r["error_details"])["errors"][0] for r in result.failed_records
    )
    assert "expected YYYY-MM-DD" in errors


def test_history_period_start_empty_skips_format_error():
    from data_staging.services.history.history_chunk_validation import (
        validate_history_chunk_vectorized,
    )

    df = pl.DataFrame(
        {
            "period_start": [""],
            "quantity": [1.0],
            "pieces": [0],
            "location_code": ["A"],
            "sku": ["s1"],
        }
    )
    fk = {"__valid_skus__": {"s1"}, "__valid_locations__": {"a"}}
    result = validate_history_chunk_vectorized(
        df,
        batch_id="b",
        chunk_idx=0,
        chunk_size=1000,
        foreign_keys_data=fk,
    )

    assert result.passed_df.is_empty()
    assert len(result.failed_records) == 1
    errors = json.loads(result.failed_records[0]["error_details"])["errors"]
    assert any("Campo obligatorio vacío: period_start" in e for e in errors)
    assert not any("YYYY-MM-DD" in e for e in errors)


def test_apply_history_transforms_sets_granularity_and_source_from_metadata():
    from data_staging.services.history.history_transforms import apply_history_transforms_polars

    df = pl.DataFrame({"sku": ["A"], "quantity": [1.0]})
    out = apply_history_transforms_polars(
        df,
        organization_id="org-1",
        process_type="Weekly",
        source_extension="csv",
        fast_validation=True,
    )

    assert out["granularity"].to_list() == ["week"]
    assert out["source"].to_list() == ["csv"]

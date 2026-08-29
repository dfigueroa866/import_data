"""History configurable column defaults."""

from __future__ import annotations

import polars as pl

from data_staging.services.history.history_registry import (
    history_column_defaults,
    history_required_targets,
    history_required_targets_needing_mapping,
)
from data_staging.services.history.history_transforms import apply_history_column_defaults_polars


def test_history_column_defaults_excludes_system_and_empty():
    entry = {
        "non_mappable_targets": ["organization_id", "granularity"],
        "defaults": {
            "pieces": "0",
            "organization_id": "should-skip",
            "granularity": "should-skip",
            "currency": "  ",
            "on_hand_qty": "0",
        },
    }
    assert history_column_defaults(entry) == {"pieces": "0", "on_hand_qty": "0"}


def test_history_required_targets_needing_mapping_skips_defaulted():
    entry = {
        "required_mapping_columns": ["location_code", "sku", "pieces", "quantity"],
        "non_mappable_targets": ["organization_id"],
        "defaults": {"pieces": "0"},
    }
    assert history_required_targets(entry) == [
        "location_code",
        "sku",
        "pieces",
        "quantity",
    ]
    assert history_required_targets_needing_mapping(entry) == [
        "location_code",
        "sku",
        "quantity",
    ]


def test_apply_history_column_defaults_polars_fills_missing_and_empty():
    rules = {
        "defaults": {"pieces": "0", "currency": "USD"},
        "non_mappable_targets": [],
    }
    df = pl.DataFrame({"sku": ["A", "B"], "pieces": ["keep", None]})
    out = apply_history_column_defaults_polars(df, rules)
    assert out["pieces"].to_list() == ["keep", "0"]
    assert out["currency"].to_list() == ["USD", "USD"]
    assert out["sku"].to_list() == ["A", "B"]

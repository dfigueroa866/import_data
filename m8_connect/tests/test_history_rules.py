"""Tests for resolve_history_rules and config-driven validation helpers."""

import pytest

from data_staging.services.history.history_config import (
    get_auto_promotion_columns,
    resolve_history_rules,
    sku_columns_for_validation,
)


def test_resolve_history_rules_prefers_batch_snapshot():
    metadata = {
        "history_config": {
            "required_mapping_columns": ["location_code", "sku"],
            "optional_columns": ["pieces"],
            "sku_mapping_targets": ["sku"],
            "logical_columns": ["sku_code"],
            "sales_channel_default": "WHOLESALE",
            "unique_keys": ["organization_id", "sku"],
            "non_mappable_targets": ["granularity", "source", "sales_channel"],
            "defaults": {"pieces": "0"},
        }
    }
    rules = resolve_history_rules(metadata)
    assert rules["required_mapping_columns"] == ["location_code", "sku"]
    assert rules["optional_columns"] == ["pieces"]
    assert rules["sales_channel_default"] == "WHOLESALE"
    assert rules["unique_keys"] == ["organization_id", "sku"]
    assert rules["defaults"] == {"pieces": "0"}
    assert "organization_id" in rules["auto_promotion_columns"]
    assert "granularity" in rules["auto_promotion_columns"]


def test_resolve_history_rules_falls_back_to_store():
    rules = resolve_history_rules(None)
    assert rules["required_mapping_columns"]
    assert rules["sales_channel_default"]
    assert rules["auto_promotion_columns"]


def test_sku_columns_for_validation_includes_logical():
    rules = {
        "sku_mapping_targets": ["sku"],
        "logical_columns": ["sku_code"],
    }
    cols = sku_columns_for_validation(rules)
    assert cols == ["sku", "sku_code"]


def test_get_auto_promotion_columns_from_non_mappable():
    rules = {
        "non_mappable_targets": [
            "organization_id",
            "granularity",
            "source",
            "sales_channel",
        ],
    }
    auto = get_auto_promotion_columns(rules)
    assert auto[0] == "organization_id"
    assert "granularity" in auto
    assert "sales_channel" in auto

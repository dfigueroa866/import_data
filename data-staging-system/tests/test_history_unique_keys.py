"""History unique keys configuration regression."""

from __future__ import annotations

from data_staging.history.history_config import (
    HISTORY_REQUIRED_COLUMNS,
    HISTORY_SKU_MAPPING_TARGETS,
    HISTORY_UNIQUE_KEYS,
)


def test_history_unique_keys_five_columns():
    assert HISTORY_UNIQUE_KEYS == [
        "organization_id",
        "location_code",
        "sku",
        "period_start",
        "granularity",
    ]


def test_sku_id_not_in_history_model():
    assert "sku_id" not in HISTORY_REQUIRED_COLUMNS
    assert "sku_id" not in HISTORY_SKU_MAPPING_TARGETS

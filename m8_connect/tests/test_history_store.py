"""Tests for history definition store validation."""

import pytest

from data_staging.services.history import history_store


def test_normalize_process_type_accepts_polars_month_suffix():
    pt = history_store._normalize_process_type(
        {
            "key": "Monthly",
            "label": "Monthly (agrupa por mes)",
            "granularity": "month",
            "date_truncate": "1mo",
        }
    )
    assert pt["date_truncate"] == "1mo"


def test_normalize_process_type_accepts_week():
    pt = history_store._normalize_process_type(
        {
            "key": "Weekly",
            "label": "Weekly",
            "granularity": "week",
            "date_truncate": "1w",
        }
    )
    assert pt["date_truncate"] == "1w"


def test_normalize_process_type_rejects_invalid_truncate():
    with pytest.raises(ValueError, match="date_truncate inválido"):
        history_store._normalize_process_type(
            {
                "key": "Bad",
                "label": "Bad",
                "granularity": "day",
                "date_truncate": "monthly",
            }
        )


def test_update_definition_with_builtin_process_types():
    entry = history_store.update_definition(history_store.get_definition())
    keys = {pt["key"]: pt["date_truncate"] for pt in entry["process_types"]}
    assert keys["Weekly"] == "1w"
    assert keys["Monthly"] == "1mo"

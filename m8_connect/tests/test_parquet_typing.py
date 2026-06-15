"""Tests for typed Parquet casting utilities."""

from __future__ import annotations

from datetime import date

import polars as pl

from data_staging.utils.parquet_typing import (
    cast_dataframe_to_target_types,
    map_file_headers_to_target_types,
    sanitize_frame_for_copy,
)


def test_map_file_headers_to_target_types_case_insensitive():
    target = {"period_start": "date", "quantity": "numeric", "sku": "character varying(50)"}
    mapped = map_file_headers_to_target_types(
        ["PERIOD_START", "quantity", "unknown_col"],
        target,
    )
    assert mapped["PERIOD_START"] == "date"
    assert mapped["quantity"] == "numeric"
    assert mapped["unknown_col"] == "text"


def test_cast_dataframe_to_target_types_date_and_numeric():
    df = pl.DataFrame(
        {
            "period_start": ["20240108", "2024-01-15"],
            "quantity": ["10", "5.5"],
            "sku": ["A", "B"],
        }
    )
    out = cast_dataframe_to_target_types(
        df,
        {
            "period_start": "date",
            "quantity": "numeric",
            "sku": "character varying(50)",
        },
    )
    assert out["period_start"].dtype == pl.Date
    assert out["period_start"].to_list() == [date(2024, 1, 8), date(2024, 1, 15)]
    assert out["quantity"].dtype == pl.Float64
    assert out["sku"].dtype == pl.Utf8


def test_sanitize_frame_for_copy_handles_datetime_and_object():
    import pandas as pd

    frame = pd.DataFrame(
        {
            "period_start": pd.to_datetime(["2024-01-01", "2024-01-02"]),
            "sku": ["A\tB", "C\nD"],
            "quantity": [1.0, 2.0],
        }
    )
    cleaned = sanitize_frame_for_copy(frame)
    assert cleaned["period_start"].iloc[0] == "2024-01-01 00:00:00"
    assert "\t" not in str(cleaned["sku"].iloc[0])
    assert cleaned["quantity"].iloc[0] == 1.0

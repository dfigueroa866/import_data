"""Golden batch aggregation regression tests."""

from __future__ import annotations

import hashlib

import polars as pl
import pytest

from data_staging.services.aggregation_service import process_aggregation


def _group_checksum(df: pl.DataFrame) -> str:
    keys = [c for c in ["organization_id", "location_code", "sku", "period_start"] if c in df.columns]
    chk = df.group_by(keys).agg(pl.col("quantity").sum().alias("qty")).sort(keys)
    return hashlib.sha256(chk.write_csv().encode()).hexdigest()[:16]


def test_golden_aggregation_row_counts(
    golden_raw_csv,
    golden_column_mappings_wizard,
    golden_column_toggles,
    golden_expected,
):
    stats, out_path = process_aggregation(
        str(golden_raw_csv),
        golden_column_mappings_wizard,
        golden_column_toggles,
        process_type=golden_expected["process_type"],
    )
    assert not stats.get("has_error"), stats.get("error_detail")
    assert stats["total_rows"] == golden_expected["raw_rows"]
    assert stats["grouped_rows"] == golden_expected["aggregated_rows"]

    agg_df = pl.read_parquet(out_path)
    assert agg_df.height == golden_expected["aggregated_rows"]


def test_golden_aggregation_quantity_checksum(
    golden_raw_csv,
    golden_column_mappings_wizard,
    golden_column_toggles,
    golden_expected,
):
    stats, out_path = process_aggregation(
        str(golden_raw_csv),
        golden_column_mappings_wizard,
        golden_column_toggles,
        process_type=golden_expected["process_type"],
    )
    assert stats["orig_qty"] == pytest.approx(golden_expected["aggregation"]["orig_qty"])
    assert stats["agg_qty"] == pytest.approx(golden_expected["aggregation"]["agg_qty"])

    agg_df = pl.read_parquet(out_path)
    assert _group_checksum(agg_df) == golden_expected["aggregation"]["group_checksum"]

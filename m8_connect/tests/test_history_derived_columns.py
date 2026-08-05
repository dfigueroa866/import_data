"""MVP2 history auto columns: ISO from period_start + constant flags."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from data_staging.services.history.history_config import (
    HISTORY_AUTO_PROMOTION_COLUMNS,
    HISTORY_NON_MAPPABLE_TARGETS,
    HISTORY_UPSERT_UPDATE_COLUMNS,
    get_auto_promotion_columns,
)
from data_staging.services.history.history_transforms import (
    apply_history_derived_columns_polars,
    apply_history_transforms_polars,
)


def test_contract_includes_mvp2_auto_columns():
    for col in (
        "iso_year",
        "iso_week",
        "stockout_flag",
        "markdown_pct",
        "promo_flag",
    ):
        assert col in HISTORY_NON_MAPPABLE_TARGETS
        assert col in HISTORY_AUTO_PROMOTION_COLUMNS
        assert col in HISTORY_UPSERT_UPDATE_COLUMNS

    auto = get_auto_promotion_columns()
    assert "iso_year" in auto
    assert "stockout_flag" in auto


def test_derived_columns_from_period_start():
    # Monday 2024-01-08 → ISO year 2024, ISO week 2
    df = pl.DataFrame({"period_start": [date(2024, 1, 8)]}).with_columns(
        pl.col("period_start").cast(pl.Date)
    )
    out = apply_history_derived_columns_polars(df)
    assert out["iso_year"][0] == 2024
    assert out["iso_week"][0] == 2
    assert out["stockout_flag"][0] is False
    assert out["promo_flag"][0] is False
    assert out["markdown_pct"][0] == 0


def test_derived_columns_recalc_after_truncated_bucket():
    # After weekly truncate to Monday 2024-01-01 (week 1)
    df = pl.DataFrame({"period_start": [date(2024, 1, 1)]}).with_columns(
        pl.col("period_start").cast(pl.Date)
    )
    out = apply_history_derived_columns_polars(df)
    assert out["iso_year"][0] == 2024
    assert out["iso_week"][0] == 1


def test_transforms_apply_derived_in_normal_and_aggregated_mode():
    df = pl.DataFrame(
        {
            "sku": ["A"],
            "location_code": ["L1"],
            "period_start": [date(2024, 1, 8)],
            "quantity": [1.0],
        }
    ).with_columns(pl.col("period_start").cast(pl.Date))

    normal = apply_history_transforms_polars(
        df,
        organization_id="org-1",
        process_type="Weekly",
        source_extension="csv",
    )
    assert "iso_year" in normal.columns
    assert normal["stockout_flag"][0] is False

    agg_in = normal.select(
        ["sku", "location_code", "period_start", "quantity", "organization_id"]
    )
    aggregated = apply_history_transforms_polars(
        agg_in,
        organization_id="org-1",
        aggregated_mode=True,
    )
    assert aggregated["iso_week"][0] == 2
    assert aggregated["markdown_pct"][0] == 0


def test_transforms_granularity_from_process_type():
    """granularity must come from Paso 1 processType (Weekly→week, Monthly→month)."""
    df = pl.DataFrame(
        {
            "sku": ["A"],
            "location_code": ["L1"],
            "period_start": [date(2024, 1, 8)],
            "quantity": [1.0],
        }
    ).with_columns(pl.col("period_start").cast(pl.Date))

    weekly = apply_history_transforms_polars(
        df,
        organization_id="org-1",
        process_type="Weekly",
        source_extension="csv",
    )
    assert weekly["granularity"][0] == "week"

    monthly = apply_history_transforms_polars(
        df,
        organization_id="org-1",
        process_type="Monthly",
        source_extension="csv",
    )
    assert monthly["granularity"][0] == "month"


def test_ensure_history_promotion_batch_fills_mvp2_columns():
    import pyarrow as pa

    from data_staging.workers.promotion_worker import _ensure_history_promotion_batch

    batch = pa.RecordBatch.from_pydict(
        {
            "sku": ["A"],
            "period_start": [date(2024, 1, 8)],
            "quantity": [1.0],
            "granularity": ["wrong"],
        }
    )
    cols = [
        "sku",
        "period_start",
        "quantity",
        "granularity",
        "sales_channel",
        "iso_year",
        "iso_week",
        "stockout_flag",
        "markdown_pct",
        "promo_flag",
    ]
    out = _ensure_history_promotion_batch(
        batch,
        cols,
        sales_channel_default="SELL_IN",
        process_type="Monthly",
    )
    pdf = out.to_pandas()
    assert pdf["granularity"].iloc[0] == "month"
    assert pdf["sales_channel"].iloc[0] == "SELL_IN"
    assert bool(pdf["stockout_flag"].iloc[0]) is False
    assert int(pdf["markdown_pct"].iloc[0]) == 0
    assert bool(pdf["promo_flag"].iloc[0]) is False
    assert int(pdf["iso_year"].iloc[0]) == 2024
    assert int(pdf["iso_week"].iloc[0]) == 2

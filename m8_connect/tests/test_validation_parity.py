"""Parity: legacy validate_and_prepare_chunk vs vectorized path."""

from __future__ import annotations

import polars as pl
import pytest

from data_staging.workers.file_processor import validate_and_prepare_chunk
from data_staging.utils.vectorized_validation import validate_chunk_vectorized


def _run_both(df, **kwargs):
    legacy = validate_and_prepare_chunk(chunk_df=df.clone(), **kwargs)
    vector = validate_chunk_vectorized(
        chunk_df=df.clone(),
        batch_id=kwargs["batch_id"],
        chunk_idx=kwargs.get("chunk_idx", 0),
        chunk_size=250_000,
        column_mapping=kwargs.get("column_mapping"),
        target_column_types=kwargs.get("target_column_types"),
        not_null_columns=kwargs.get("not_null_columns"),
        foreign_keys_data=kwargs.get("foreign_keys_data"),
        history_mode=kwargs.get("history_mode", False),
    )
    return legacy, vector


def test_validation_parity_golden_batch(
    golden_aggregated_parquet,
    golden_column_mappings,
    golden_fk_sets,
    golden_expected,
):
    df = pl.read_parquet(golden_aggregated_parquet)
    org_id = golden_expected["column_mappings"]["__fixed_organization_id__"]["default_value"]
    common = dict(
        batch_id=golden_expected["batch_id"],
        chunk_idx=0,
        source_name="sales_history",
        column_mapping=golden_column_mappings,
        target_column_types={
            "organization_id": "uuid",
            "location_code": "varchar",
            "sku": "varchar",
            "period_start": "date",
            "granularity": "varchar",
            "quantity": "numeric",
            "pieces": "numeric",
            "source": "varchar",
            "sales_channel": "varchar",
        },
        not_null_columns={
            "organization_id": True,
            "location_code": True,
            "sku": True,
            "period_start": True,
            "granularity": True,
            "quantity": True,
            "source": True,
        },
        foreign_keys_data=golden_fk_sets,
        history_mode=True,
        process_type=golden_expected["process_type"],
        organization_id=org_id,
    )

    legacy, vector = _run_both(df, **common)

    assert len(legacy) == len(vector)
    legacy_by_row = {r["source_row_number"]: r for r in legacy}
    for vr in vector:
        lr = legacy_by_row[vr["source_row_number"]]
        assert lr["validation_status"] == vr["validation_status"]
        if lr["validation_status"] == "FAILED":
            assert lr["error_details"] == vr["error_details"]

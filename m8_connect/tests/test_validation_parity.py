"""Parity: legacy validate_and_prepare_chunk vs vectorized path."""

from __future__ import annotations

import json
from unittest.mock import patch

import polars as pl
import pytest

from data_staging.workers.file_processor import validate_and_prepare_chunk
from data_staging.utils.vectorized_validation import (
    ChunkValidationResult,
    validate_chunk_vectorized,
)


def _flatten_validation_result(
    result: ChunkValidationResult,
    *,
    batch_id: str,
    chunk_idx: int,
    chunk_size: int,
    total_cols: int,
) -> list:
    records = list(result.failed_records)
    start_row_num = (chunk_idx * chunk_size) + 1
    for i, raw_row in enumerate(result.passed_df.to_dicts()):
        null_count = sum(1 for v in raw_row.values() if v is None)
        quality_score = 100.0 - (null_count * 100.0 / total_cols) if total_cols > 0 else 100.0
        records.append(
            {
                "batch_id": batch_id,
                "source_row_number": start_row_num + i,
                "source_file_data": json.dumps({}),
                "raw_data": json.dumps(raw_row),
                "processed_data": json.dumps(raw_row),
                "validation_status": "PASSED",
                "data_quality_score": quality_score,
                "is_duplicate": False,
                "error_details": None,
            }
        )
    return records


def _run_both(df, **kwargs):
    chunk_size = kwargs.get("chunk_size", 250_000)
    with patch(
        "data_staging.utils.vectorized_validation.use_vectorized_validation",
        return_value=False,
    ):
        legacy = validate_and_prepare_chunk(chunk_df=df.clone(), **kwargs)

    prepped = validate_and_prepare_chunk(chunk_df=df.clone(), **kwargs)
    if isinstance(prepped, ChunkValidationResult):
        vector = _flatten_validation_result(
            prepped,
            batch_id=kwargs["batch_id"],
            chunk_idx=kwargs.get("chunk_idx", 0),
            chunk_size=chunk_size,
            total_cols=len(df.columns),
        )
    else:
        vector = prepped
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

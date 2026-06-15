"""Parity: validate_history_chunk vs validate_and_prepare_chunk (history)."""

from __future__ import annotations

import json

import polars as pl

from data_staging.services.history.history_chunk_validation import validate_history_chunk
from data_staging.utils.vectorized_validation import ChunkValidationResult
from data_staging.workers.file_processor import validate_and_prepare_chunk


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
                "raw_data": json.dumps(raw_row, default=str),
                "processed_data": json.dumps(raw_row, default=str),
                "validation_status": "PASSED",
                "data_quality_score": quality_score,
                "is_duplicate": False,
                "error_details": None,
            }
        )
    return records


def test_validation_parity_golden_batch(
    golden_aggregated_parquet,
    golden_column_mappings,
    golden_fk_sets,
    golden_expected,
):
    df = pl.read_parquet(golden_aggregated_parquet)
    org_id = golden_expected["organization_id"]
    chunk_size = 250_000
    history_kwargs = dict(
        batch_id=golden_expected["batch_id"],
        chunk_idx=0,
        chunk_size=chunk_size,
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
        history_rules=None,
        process_type=golden_expected["process_type"],
        organization_id=org_id,
        source_extension="csv",
        sku_resolver=None,
        resolve_sku_id=False,
    )
    processor_kwargs = {
        **{k: v for k, v in history_kwargs.items() if k != "chunk_size"},
        "source_name": "sales_history",
        "history_mode": True,
    }

    direct = validate_history_chunk(chunk_df=df.clone(), **history_kwargs)
    via_processor = validate_and_prepare_chunk(chunk_df=df.clone(), **processor_kwargs)

    assert isinstance(via_processor, ChunkValidationResult)
    vector = _flatten_validation_result(
        via_processor,
        batch_id=history_kwargs["batch_id"],
        chunk_idx=0,
        chunk_size=chunk_size,
        total_cols=len(df.columns),
    )
    direct_flat = _flatten_validation_result(
        direct,
        batch_id=history_kwargs["batch_id"],
        chunk_idx=0,
        chunk_size=chunk_size,
        total_cols=len(df.columns),
    )

    assert len(direct_flat) == len(vector)
    direct_by_row = {r["source_row_number"]: r for r in direct_flat}
    for vr in vector:
        dr = direct_by_row[vr["source_row_number"]]
        assert dr["validation_status"] == vr["validation_status"]
        if dr["validation_status"] == "FAILED":
            assert dr["error_details"] == vr["error_details"]

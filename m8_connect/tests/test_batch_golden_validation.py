"""Golden batch validation regression (offline)."""

from __future__ import annotations

import polars as pl

from data_staging.utils.vectorized_validation import ChunkValidationResult
from data_staging.workers.file_processor import validate_and_prepare_chunk


def _count_validation_results(records) -> tuple[int, int]:
    if isinstance(records, ChunkValidationResult):
        passed = records.passed_df.height
        failed = len(records.failed_records)
        return passed, failed
    passed = sum(1 for r in records if r["validation_status"] == "PASSED")
    failed = sum(1 for r in records if r["validation_status"] == "FAILED")
    return passed, failed


def test_golden_validation_passed_count(
    golden_aggregated_parquet,
    golden_column_mappings,
    golden_fk_sets,
    golden_expected,
):
    df = pl.read_parquet(golden_aggregated_parquet)
    org_id = golden_expected["organization_id"]

    records = validate_and_prepare_chunk(
        chunk_df=df,
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

    passed, failed = _count_validation_results(records)
    expected_passed = golden_expected["processing_stats"]["total_inserted"]
    expected_failed = golden_expected["processing_stats"]["total_rejected"] or 0

    assert passed == expected_passed
    assert failed == expected_failed

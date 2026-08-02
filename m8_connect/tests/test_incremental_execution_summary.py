"""Tests for incremental run execution summary metadata."""

from m8_incremental.services.orchestrator import (
    _execution_metadata_patch,
    _record_enqueued,
    _record_skip,
)


def test_execution_summary_records_enqueued_and_skipped():
    enqueued = []
    skipped = []
    skip_messages = []

    _record_enqueued(
        enqueued,
        load_kind="catalog",
        catalog_slug="skus",
        file_name="skus.csv",
        batch_id="batch-1",
    )
    _record_skip(
        skipped,
        skip_messages,
        load_kind="history",
        granularity="weekly",
        reason="Historia omitida: no hay archivos",
    )

    patch = _execution_metadata_patch(enqueued, skipped)
    summary = patch["execution_summary"]

    assert len(summary["enqueued"]) == 1
    assert summary["enqueued"][0]["catalog_slug"] == "skus"
    assert summary["enqueued"][0]["batch_id"] == "batch-1"

    assert len(summary["skipped"]) == 1
    assert summary["skipped"][0]["load_kind"] == "history"
    assert summary["skipped"][0]["granularity"] == "weekly"
    assert "no hay archivos" in summary["skipped"][0]["reason"]

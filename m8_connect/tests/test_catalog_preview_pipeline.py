"""Tests for catalog preview pipeline (homologated with history, no aggregation)."""

from __future__ import annotations

from pathlib import Path

import polars as pl

from data_staging.services.catalog.catalog_preview_pipeline import (
    run_catalog_preview_from_validated,
)


def test_run_catalog_preview_from_validated_no_aggregation(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "data_staging.services.catalog.catalog_preview_pipeline.report_processing_progress",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "data_staging.services.catalog.catalog_preview_pipeline.open_progress_connection",
        lambda: type("Conn", (), {"close": lambda self: None})(),
    )

    validated = tmp_path / "batch_validated.parquet"
    pl.DataFrame(
        {
            "organization_id": ["org-1", "org-1"],
            "code": ["A", "B"],
            "name": ["Alpha", "Beta"],
        }
    ).write_parquet(validated)

    stats, out_path = run_catalog_preview_from_validated(
        batch_id="batch-1",
        validated_path=validated,
        valid_rows=2,
        rejected_rows=0,
        total_rows=2,
        metadata={},
    )

    assert out_path == validated
    assert stats["has_error"] is False
    assert stats["valid_rows"] == 2
    assert stats["grouped_rows"] == 2
    assert len(stats["preview_data"]) == 2

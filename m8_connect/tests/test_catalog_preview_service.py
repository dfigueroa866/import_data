"""Tests for catalog preview read path (step 3 light preview)."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from data_staging.services.catalog_preview_service import (
    CatalogPreviewError,
    process_catalog_preview_light,
    run_catalog_wizard_preview,
)


@pytest.fixture
def sample_parquet(tmp_path: Path) -> Path:
    path = tmp_path / "sample.raw.parquet"
    pl.DataFrame(
        {
            "code": [f"C{i:03d}" for i in range(100)],
            "name": [f"Item {i}" for i in range(100)],
            "city": ["CDMX"] * 100,
        }
    ).write_parquet(path)
    return path


def test_preview_light_reads_row_sample_only(monkeypatch, sample_parquet: Path):
    catalog_meta = {
        "name": "items",
        "target_schema": "public",
        "target_table": "items",
        "required_columns": [],
        "unique_keys": [],
    }

    monkeypatch.setattr(
        "data_staging.services.catalog_preview_service.get_catalog_table",
        lambda _name: catalog_meta,
    )
    monkeypatch.setattr(
        "data_staging.services.catalog_preview_service.apply_catalog_transforms",
        lambda pdf, *_a, **_k: pdf,
    )

    read_calls: list[dict] = []
    original_read = pl.read_parquet

    def tracking_read_parquet(path, **kwargs):
        read_calls.append(kwargs)
        return original_read(path, **kwargs)

    monkeypatch.setattr(pl, "read_parquet", tracking_read_parquet)

    stats, _path = process_catalog_preview_light(
        file_path=str(sample_parquet),
        target_table="items",
        column_mappings={
            "code": {"target": "code"},
            "name": {"target": "name"},
        },
        column_toggles={"code": True, "name": True},
        preview_limit=20,
    )

    assert stats["total_rows"] == 100
    assert len(stats["preview_data"]) == 20
    assert any(c.get("n_rows") == 20 for c in read_calls)
    data_call = next(c for c in read_calls if c.get("n_rows") == 20)
    assert set(data_call.get("columns") or []) == {"code", "name"}


def test_run_catalog_wizard_preview_uses_catalog_name(monkeypatch, sample_parquet: Path):
    catalog_meta = {
        "name": "location",
        "target_schema": "public",
        "target_table": "locations",
        "required_columns": [],
        "unique_keys": [],
    }

    monkeypatch.setattr(
        "data_staging.services.catalog_preview_service.get_catalog_table",
        lambda name: catalog_meta if name == "location" else None,
    )
    monkeypatch.setattr(
        "data_staging.services.catalog_preview_service.apply_catalog_transforms",
        lambda pdf, *_a, **_k: pdf,
    )

    metadata = {
        "catalog_name": "location",
        "target_table": "locations",
        "column_mappings": {"code": {"target": "code"}, "name": {"target": "name"}},
        "column_toggles": {"code": True, "name": True},
    }

    stats, _path = run_catalog_wizard_preview(str(sample_parquet), metadata, preview_limit=5)

    assert stats["total_rows"] == 100
    assert len(stats["preview_data"]) == 5


def test_preview_light_missing_file():
    with pytest.raises(CatalogPreviewError, match="File not found"):
        process_catalog_preview_light(
            file_path="/nonexistent/file.raw.parquet",
            target_table="items",
            column_mappings={},
            column_toggles={},
        )

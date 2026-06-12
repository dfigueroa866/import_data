"""Tests for history preview validation + aggregation pipeline.

Regression (CI): paridad agregación incremental vs spill (`test_streaming_aggregation_spill_path`).
Aceptación 20M: criterios en docs/FUNCIONAMIENTO_APLICACION.md §7.7 (benchmark manual).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from data_staging.services.history.history_validation import (
    convert_wizard_column_mapping,
    identity_wizard_mappings_for_columns,
)


def test_convert_wizard_column_mapping():
    mappings = {
        "FECHA": {"target": "period_start"},
        "QTY": {"target": "quantity"},
        "__org__": {"target": "organization_id", "default_value": "org-1"},
    }
    toggles = {"FECHA": True, "QTY": True, "__org__": True}
    column_mapping, selected = convert_wizard_column_mapping(mappings, toggles)
    assert "period_start" in column_mapping
    assert column_mapping["period_start"]["source"] == "FECHA"
    assert "FECHA" in selected


def test_identity_wizard_mappings_for_columns():
    cols = ["period_start", "quantity", "sku"]
    mappings, toggles = identity_wizard_mappings_for_columns(cols)
    assert mappings["sku"]["target"] == "sku"
    assert toggles["quantity"] is True


def test_aggregation_no_drop_nulls(tmp_path):
    """Rows with nulls in optional cols should not be dropped before group."""
    from data_staging.services.aggregation_service import _prepare_chunk_for_agg

    df = pl.DataFrame(
        {
            "period_start": ["2024-01-01", "2024-01-02"],
            "quantity": [1.0, None],
            "location_code": ["A", "B"],
            "sku": ["S1", "S2"],
            "organization_id": ["org", "org"],
        }
    )
    out = _prepare_chunk_for_agg(df, {}, {})
    assert out.height == 2


def test_coerce_period_start_mixed_formats():
    from data_staging.services.catalog.catalog_transforms import coerce_period_start_to_date

    df = pl.DataFrame(
        {
            "period_start": ["20240108", "08/01/2024", "2024-01-15"],
        }
    )
    out = coerce_period_start_to_date(df)
    assert out["period_start"].dtype == pl.Date
    assert out["period_start"].to_list() == [
        date(2024, 1, 8),
        date(2024, 8, 1),
        date(2024, 1, 15),
    ]


def test_parse_dates_polars_european_format():
    from data_staging.services.catalog.catalog_transforms import parse_dates_polars_series

    series = pl.Series(["20240108", "08/01/2024", "2024-01-15"])
    parsed = parse_dates_polars_series(series, prefer_us_format=False)
    assert [v.date() if v is not None else None for v in parsed.to_list()] == [
        date(2024, 1, 8),
        date(2024, 1, 8),
        date(2024, 1, 15),
    ]


def test_vectorized_validation_parses_compact_dates():
    from data_staging.utils.vectorized_validation import validate_chunk_vectorized

    df = pl.DataFrame(
        {
            "period_start": ["20240108", "20240115"],
            "quantity": [1, 2],
            "location_code": ["A", "B"],
            "sku": ["S1", "S2"],
        }
    )
    result = validate_chunk_vectorized(
        df,
        batch_id="test-batch",
        chunk_idx=0,
        chunk_size=1000,
        column_mapping={
            "period_start": {"source": "period_start"},
            "quantity": {"source": "quantity"},
            "location_code": {"source": "location_code"},
            "sku": {"source": "sku"},
        },
        target_column_types={
            "period_start": "date",
            "quantity": "numeric",
            "location_code": "varchar(50)",
            "sku": "varchar(50)",
        },
        not_null_columns={
            "period_start": True,
            "quantity": True,
            "location_code": True,
            "sku": True,
        },
        history_mode=True,
    )
    assert result.passed_df.height == 2
    assert result.passed_df["period_start"].to_list() == ["2024-01-08", "2024-01-15"]


def test_is_chunk_already_mapped_distinguishes_source_vs_target_names():
    import polars as pl
    from data_staging.utils.mapping_helpers import is_chunk_already_mapped

    raw = pl.DataFrame(
        {
            "sku": ["S1"],
            "location": ["A"],
            "quantity": [1],
            "start_date": ["2024-01-01"],
        }
    )
    mapping = {
        "sku": {"source": "sku"},
        "location_code": {"source": "location"},
        "quantity": {"source": "quantity"},
        "period_start": {"source": "start_date"},
        "organization_id": {"source": None, "default": "org-1"},
    }
    assert is_chunk_already_mapped(raw, mapping) is False

    mapped = pl.DataFrame(
        {
            "sku": ["S1"],
            "location_code": ["A"],
            "quantity": [1],
            "period_start": ["2024-01-01"],
            "organization_id": ["org-1"],
        }
    )
    assert is_chunk_already_mapped(mapped, mapping) is True


def test_validate_applies_mapping_before_history_validation():
    import polars as pl
    from data_staging.utils.vectorized_validation import ChunkValidationResult
    from data_staging.workers.file_processor import validate_and_prepare_chunk

    chunk = pl.DataFrame(
        {
            "sku": ["SKU-1"],
            "location": ["LOC-A"],
            "quantity": [10],
            "start_date": ["2024-01-08"],
        }
    )
    column_mapping = {
        "sku": {"source": "sku"},
        "location_code": {"source": "location"},
        "quantity": {"source": "quantity"},
        "period_start": {"source": "start_date"},
        "organization_id": {"source": None, "default": "test-org"},
    }
    result = validate_and_prepare_chunk(
        chunk,
        batch_id="b1",
        chunk_idx=0,
        source_name="b1",
        column_mapping=column_mapping,
        selected_columns=["sku", "location", "quantity", "start_date"],
        target_column_types={
            "sku": "varchar",
            "location_code": "varchar",
            "quantity": "numeric",
            "period_start": "date",
            "organization_id": "varchar",
        },
        not_null_columns={
            "sku": True,
            "location_code": True,
            "quantity": True,
            "period_start": True,
        },
        foreign_keys_data={
            "__valid_skus__": {"sku-1"},
            "__valid_locations__": {"loc-a"},
        },
        history_mode=True,
        organization_id="test-org",
        process_type="Weekly",
    )

    assert isinstance(result, ChunkValidationResult)
    assert result.passed_df.height == 1
    assert result.passed_df["location_code"][0] == "LOC-A"
    assert str(result.passed_df["period_start"][0]).startswith("2024-01-08")
    assert result.passed_df["organization_id"][0] == "test-org"


def test_find_rejected_records_file_by_batch_id(tmp_path, monkeypatch):
    from data_staging.utils import batch_staging_files as bsf

    batch_id = "batch-abc-123"
    rejected = tmp_path / f"{batch_id}{bsf.REJECTED_SUFFIX}"
    rejected.write_text("linea_y_errores,col\n1;error,x\n", encoding="utf-8")

    monkeypatch.setattr(bsf, "get_temp_dir", lambda: tmp_path)

    found = bsf.find_rejected_records_file(batch_id, metadata_path="/ruta/inexistente.tsv")
    assert found == rejected.resolve()

    found_by_metadata = bsf.find_rejected_records_file(
        batch_id,
        metadata_path=str(rejected).replace("/", "\\"),
    )
    assert found_by_metadata == rejected.resolve()


def test_sku_resolver_preload_matches_resolve():
    from data_staging.services.history.history_transforms import SkuCodeResolver

    class FakeCursor:
        def __init__(self):
            self.individual_calls = 0
            self.preload_calls = 0

        def execute(self, query, params=None):
            if "LOWER" in query and "WHERE organization_id" in query and "LIMIT" not in query:
                self.preload_calls += 1
                self._preload_rows = [("sku-a", "uuid-a"), ("sku-b", "uuid-b")]
            else:
                self.individual_calls += 1
                code = params[1].lower()
                mapping = {"sku-a": "uuid-a", "sku-b": "uuid-b", "missing": None}
                row = (mapping.get(code),) if mapping.get(code) else None
                self._individual_row = row

        def fetchall(self):
            return getattr(self, "_preload_rows", [])

        def fetchone(self):
            return getattr(self, "_individual_row", None)

    cursor = FakeCursor()
    resolver = SkuCodeResolver(cursor, "org-1", pk_column="id", code_column="code")
    resolver.preload()
    assert cursor.preload_calls == 1
    assert resolver.resolve("SKU-A") == "uuid-a"
    assert resolver.resolve("missing") is None
    assert cursor.individual_calls == 0


def test_resolve_sku_id_series_matches_row_logic():
    import polars as pl
    from data_staging.services.history.history_transforms import (
        SkuCodeResolver,
        _resolve_sku_id_from_row,
    )

    class FakeCursor:
        def execute(self, query, params=None):
            self._rows = [("code-a", "id-a"), ("code-b", "id-b")]

        def fetchall(self):
            return self._rows

        def fetchone(self):
            return None

    resolver = SkuCodeResolver(FakeCursor(), "org-1")
    resolver.preload()

    df = pl.DataFrame(
        {
            "sku_code": ["CODE-A", None, "UNKNOWN"],
            "sku": ["fallback", "CODE-B", "X"],
            "sku_id": [None, "existing-id", None],
        }
    )

    vectorized = resolver.resolve_sku_id_series(df, resolve_sku_id=True).to_list()
    rowwise = [
        _resolve_sku_id_from_row(row, resolver, resolve_sku_id=True)
        for row in df.to_dicts()
    ]
    assert vectorized == rowwise
    assert vectorized == ["id-a", "existing-id", None]


def test_map_preview_progress_phase():
    from data_staging.api.v1.upload import _map_preview_progress_phase

    meta = {"preview_in_progress": True}
    assert _map_preview_progress_phase(meta, "validating") == "preview_validating"
    assert _map_preview_progress_phase(meta, "preview_aggregating") == "preview_aggregating"
    assert _map_preview_progress_phase({}, "validating") == "validating"


def test_merge_agg_partials_matches_concat_groupby():
    from data_staging.services.aggregation_service import (
        _merge_agg_partials,
        DATE_COL,
        QTY_COL,
        LOC_COL,
        SKU_COL,
    )

    dims = ["organization_id", LOC_COL, SKU_COL, DATE_COL]
    partial_a = pl.DataFrame(
        {
            "organization_id": ["org"],
            "location_code": ["A"],
            "sku": ["S1"],
            "period_start": [date(2024, 1, 1)],
            "quantity": [10.0],
        }
    )
    partial_b = pl.DataFrame(
        {
            "organization_id": ["org"],
            "location_code": ["A"],
            "sku": ["S1"],
            "period_start": [date(2024, 1, 1)],
            "quantity": [5.0],
        }
    )
    incremental = _merge_agg_partials(_merge_agg_partials(None, partial_a, dims), partial_b, dims)
    combined = pl.concat([partial_a, partial_b], how="diagonal_relaxed")
    metrics = [pl.col(QTY_COL).sum().alias(QTY_COL)]
    reference = combined.group_by(dims).agg(metrics)
    assert incremental["quantity"].sum() == reference["quantity"].sum()
    assert incremental.height == 1


def test_streaming_aggregation_spill_path(tmp_path, monkeypatch):
    from data_staging.services import aggregation_service as agg_mod

    monkeypatch.setattr(agg_mod.settings, "AGG_SPILL_THRESHOLD_ROWS", 50)
    monkeypatch.setattr(agg_mod.settings, "AGGREGATION_CHUNK_SIZE", 30)
    monkeypatch.setattr(agg_mod, "get_temp_dir", lambda: tmp_path)

    rows = []
    for idx in range(120):
        week = date(2024, 1, 1) if idx < 60 else date(2024, 1, 8)
        rows.append(
            {
                "organization_id": "org",
                "location_code": f"LOC-{idx % 5}",
                "sku": f"SKU-{idx % 10}",
                "period_start": week,
                "quantity": float(1 + (idx % 3)),
            }
        )
    source = tmp_path / "input_validated.parquet"
    pl.DataFrame(rows).write_parquet(source)
    mappings, toggles = identity_wizard_mappings_for_columns(
        ["organization_id", "location_code", "sku", "period_start", "quantity"]
    )

    stats, out_path = agg_mod.process_aggregation(
        file_path=str(source),
        column_mappings=mappings,
        column_toggles=toggles,
        process_type="Weekly",
        total_rows_hint=120,
        batch_id="spill-test-batch",
    )

    assert not stats.get("has_error")
    assert out_path.is_file()
    assert stats["grouped_rows"] > 0
    assert stats["orig_qty"] == stats["agg_qty"]
    assert not list(tmp_path.glob("spill-test-batch_agg_partial_*.parquet"))


def test_resolve_promotion_tuning_scales_with_row_count():
    from data_staging.workers.promotion_worker import resolve_promotion_tuning

    small = resolve_promotion_tuning(1_000_000)
    medium = resolve_promotion_tuning(8_000_000)
    large = resolve_promotion_tuning(20_000_000)

    assert small["batch_size"] <= medium["batch_size"] <= large["batch_size"]
    assert small["work_mem"] != large["work_mem"]

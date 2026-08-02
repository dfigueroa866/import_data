"""Tests for incremental worker helpers."""

from m8_incremental.services.run_helpers import batch_source_row_stats, normalize_batch_ids


def test_normalize_batch_ids_from_list():
    assert normalize_batch_ids(["a", "b"]) == ["a", "b"]


def test_normalize_batch_ids_from_pg_array_string():
    raw = "{11111111-1111-1111-1111-111111111111,22222222-2222-2222-2222-222222222222}"
    assert normalize_batch_ids(raw) == [
        "11111111-1111-1111-1111-111111111111",
        "22222222-2222-2222-2222-222222222222",
    ]


def test_batch_source_row_stats_prefers_preview_rejections():
    meta = {
        "preview_result": {
            "validation_summary": {
                "total_rows": 42000,
                "valid_rows": 17748,
                "rejected_rows": 24252,
            }
        },
        "processing_stats": {
            "total_inserted": 17745,
            "total_rejected": 0,
        },
        "promoted_inserted": 0,
        "promoted_updated": 17745,
    }
    stats = batch_source_row_stats(meta)
    assert stats["source_rows"] == 42000
    assert stats["rejected_rows"] == 24252
    assert stats["valid_rows"] == 17748


def test_batch_source_row_stats_falls_back_to_processing():
    meta = {
        "processing_stats": {
            "total_inserted": 1000,
            "total_rejected": 50,
        }
    }
    stats = batch_source_row_stats(meta)
    assert stats["source_rows"] == 1050
    assert stats["rejected_rows"] == 50


def test_batch_source_row_stats_uses_metadata_rejected_rows():
    meta = {
        "processing_stats": {"total_inserted": 10, "total_rejected": 0},
        "rejected_rows": 99,
    }
    stats = batch_source_row_stats(meta)
    assert stats["rejected_rows"] == 99
    assert stats["source_rows"] == 109

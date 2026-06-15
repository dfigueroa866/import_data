"""Tests for promotion progress / orphan detection helpers."""

from datetime import datetime, timedelta, timezone

from data_staging.api.v1 import upload as upload_mod
from data_staging.api.v1.upload import _is_orphan_promotion


def _metadata_with_phase(phase: str, *, updated_at: str | None = None) -> dict:
    ts = updated_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "processing_progress": {
            "phase": phase,
            "updated_at": ts,
            "current_operation": "Ejecutando UPSERT…",
        }
    }


def test_orphan_promotion_not_orphan_when_job_active(monkeypatch):
    monkeypatch.setattr(upload_mod, "_promotion_job_active", lambda _db, _bid: True)
    metadata = _metadata_with_phase("promoting")
    assert _is_orphan_promotion(
        metadata,
        "batch-1",
        batch_status="COMPLETED",
        db=object(),
    ) is False


def test_orphan_promotion_detects_stale_without_job(monkeypatch):
    monkeypatch.setattr(upload_mod, "_promotion_job_active", lambda _db, _bid: False)
    stale_ts = (datetime.now(timezone.utc) - timedelta(seconds=900)).isoformat().replace(
        "+00:00", "Z"
    )
    metadata = _metadata_with_phase("promoting", updated_at=stale_ts)
    assert _is_orphan_promotion(
        metadata,
        "batch-1",
        batch_status="COMPLETED",
        db=object(),
    ) is True


def test_orphan_promotion_ignores_done_phase(monkeypatch):
    monkeypatch.setattr(upload_mod, "_promotion_job_active", lambda _db, _bid: False)
    metadata = _metadata_with_phase("done")
    assert _is_orphan_promotion(
        metadata,
        "batch-1",
        batch_status="COMPLETED",
        db=object(),
    ) is False

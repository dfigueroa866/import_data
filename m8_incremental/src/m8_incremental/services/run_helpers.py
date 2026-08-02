"""Shared helpers for incremental run bookkeeping."""

from __future__ import annotations

from typing import Any, Dict, List


def normalize_batch_ids(batch_ids) -> List[str]:
    """Normalize PostgreSQL uuid[] values from psycopg2 (list or '{...}' string)."""
    if batch_ids is None:
        return []
    if isinstance(batch_ids, (list, tuple)):
        return [str(value) for value in batch_ids if value]
    if isinstance(batch_ids, str):
        raw = batch_ids.strip()
        if raw.startswith("{") and raw.endswith("}"):
            inner = raw[1:-1].strip()
            if not inner:
                return []
            return [part.strip().strip('"') for part in inner.split(",") if part.strip()]
        return [raw] if raw else []
    return [str(batch_ids)]


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def batch_source_row_stats(metadata: Dict[str, Any] | None) -> Dict[str, int]:
    """
    Source-file row counts for a batch.

    Prefer preview validation_summary (original file) over processing_stats,
    because history process overwrites processing_stats with the agglomerated
    parquet (valid-only) and can zero out rejected_rows.
    """
    meta = metadata if isinstance(metadata, dict) else {}
    preview = meta.get("preview_result") or {}
    if not isinstance(preview, dict):
        preview = {}
    summary = preview.get("validation_summary") or {}
    if not isinstance(summary, dict):
        summary = {}
    process = meta.get("processing_stats") or {}
    if not isinstance(process, dict):
        process = {}

    preview_rejected = _as_int(
        summary.get("rejected_rows")
        if summary.get("rejected_rows") is not None
        else summary.get("total_rejected")
    )
    preview_valid = _as_int(
        summary.get("valid_rows")
        if summary.get("valid_rows") is not None
        else summary.get("total_inserted")
    )
    preview_total = _as_int(summary.get("total_rows"))
    if preview_total <= 0 and (preview_valid or preview_rejected):
        preview_total = preview_valid + preview_rejected

    process_rejected = _as_int(process.get("total_rejected"))
    process_valid = _as_int(
        process.get("total_inserted")
        if process.get("total_inserted") is not None
        else process.get("total_rows")
    )
    meta_rejected = _as_int(meta.get("rejected_rows"))

    rejected = max(preview_rejected, process_rejected, meta_rejected)
    # Prefer original-file total from preview; fall back to process valid + rejected.
    if preview_total > 0:
        source_rows = preview_total
    else:
        source_rows = process_valid + rejected

    return {
        "source_rows": source_rows,
        "rejected_rows": rejected,
        "valid_rows": max(0, source_rows - rejected) if source_rows else preview_valid or process_valid,
    }

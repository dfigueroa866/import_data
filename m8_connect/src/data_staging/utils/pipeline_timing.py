"""Accumulate per-phase timings into batch_control.metadata."""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

import psycopg2

from data_staging.utils.batch_staging_files import metadata_merge_expr


class PipelineTimer:
    """Thread-local style accumulator for pipeline phase durations (milliseconds)."""

    def __init__(self, namespace: str) -> None:
        self.namespace = namespace
        self._totals: Dict[str, float] = {}

    def add_ms(self, phase: str, elapsed_ms: float) -> None:
        self._totals[phase] = self._totals.get(phase, 0.0) + elapsed_ms

    @contextmanager
    def phase(self, name: str) -> Iterator[None]:
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.add_ms(name, (time.perf_counter() - t0) * 1000.0)

    def snapshot(self) -> Dict[str, Any]:
        rounded = {k: int(round(v)) for k, v in self._totals.items()}
        return {
            f"{self.namespace}_timing_ms": rounded,
            f"{self.namespace}_timing_total_ms": int(round(sum(self._totals.values()))),
        }


def persist_timing_metadata(
    conn: psycopg2.extensions.connection,
    batch_id: str,
    timing_snapshot: Dict[str, Any],
) -> None:
    """Merge timing snapshot into batch_control.metadata."""
    if not timing_snapshot:
        return
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"""
            UPDATE staging_meta.batch_control
            SET metadata = {metadata_merge_expr("%s::jsonb")},
                updated_at = CURRENT_TIMESTAMP
            WHERE batch_id = %s
            """,
            (json.dumps(timing_snapshot), batch_id),
        )
        if not getattr(conn, "autocommit", False):
            conn.commit()
    finally:
        cursor.close()

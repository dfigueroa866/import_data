"""FIFO retention for incremental load cycles."""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

import pyarrow.parquet as pq

from data_staging.services.history.history_config import HISTORY_UNIQUE_KEYS
from data_staging.utils.batch_control import normalize_metadata
from m8_incremental.config import settings
from m8_incremental.services.batch_purge import purge_batch, purge_run_directory

logger = logging.getLogger(__name__)


def _connect():
    return psycopg2.connect(str(settings.DATABASE_URL))


def _retention_limit(granularity: str, retention_years: int) -> int:
    g = (granularity or "weekly").lower()
    if g in ("monthly", "month"):
        return retention_years * 12
    return retention_years * 52


def _purge_production_history_keys(batch_id: str, metadata: Dict[str, Any]) -> int:
    """Delete sales_history rows matching keys from promoted parquet."""
    from data_staging.utils.batch_staging_files import valid_records_path

    valid_path = valid_records_path(batch_id, metadata)
    if not valid_path.is_file():
        return 0

    table = pq.read_table(valid_path, columns=HISTORY_UNIQUE_KEYS)
    df = table.to_pandas()
    if df.empty:
        return 0

    conn = _connect()
    deleted = 0
    try:
        with conn.cursor() as cur:
            for _, row in df.drop_duplicates().iterrows():
                conditions = " AND ".join(f"{col} = %s" for col in HISTORY_UNIQUE_KEYS)
                params = tuple(row[col] for col in HISTORY_UNIQUE_KEYS)
                cur.execute(
                    f"DELETE FROM public.sales_history WHERE {conditions}",
                    params,
                )
                deleted += cur.rowcount
        conn.commit()
    finally:
        conn.close()
    return deleted


def _find_oldest_completed_run(
    conn,
    organization_id: str,
    *,
    exclude_run_id: str,
) -> Optional[Dict[str, Any]]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT run_id, load_date, batch_ids, metadata
            FROM staging_meta.incremental_runs
            WHERE organization_id = %s
              AND status = 'COMPLETED'
              AND run_id != %s
            ORDER BY load_date ASC, started_at ASC
            LIMIT 1
            """,
            (organization_id, exclude_run_id),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def purge_run(run_id: str) -> Dict[str, int]:
    """Purge files, staging, and production history for a completed run."""
    conn = _connect()
    result = {"files_deleted": 0, "rows_deleted": 0}
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM staging_meta.incremental_runs WHERE run_id = %s",
                (run_id,),
            )
            run = cur.fetchone()
        if not run:
            return result

        batch_ids = [str(b) for b in (run.get("batch_ids") or [])]
        date_folder: Optional[Path] = None

        for bid in batch_ids:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT metadata, load_type FROM staging_meta.batch_control WHERE batch_id = %s",
                    (bid,),
                )
                batch = cur.fetchone()
            if not batch:
                continue
            meta = normalize_metadata(batch["metadata"])
            load_dir = meta.get("load_storage_dir")
            if load_dir and date_folder is None:
                p = Path(load_dir)
                date_folder = p.parent.parent if p.name in ("catalogos", "historia") else p.parent

            if meta.get("load_type") == "history":
                result["rows_deleted"] += _purge_production_history_keys(bid, meta)

            result["files_deleted"] += purge_batch(bid)

        if date_folder and date_folder.is_dir():
            purge_run_directory(date_folder)

        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM staging_meta.incremental_runs WHERE run_id = %s",
                (run_id,),
            )
            cur.execute(
                """
                INSERT INTO staging_meta.incremental_retention_log
                (run_id_purged, organization_id, files_deleted, rows_deleted)
                VALUES (%s, %s, %s, %s)
                """,
                (run_id, run["organization_id"], result["files_deleted"], result["rows_deleted"]),
            )
        conn.commit()
    finally:
        conn.close()
    return result


def apply_retention_after_success(
    organization_id: str,
    granularity: str,
    new_run_id: str,
) -> Optional[str]:
    """If over retention limit, purge oldest completed run."""
    conn = _connect()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT retention_years FROM staging_meta.incremental_schedule WHERE id = 1"
            )
            sched = cur.fetchone()
            retention_years = int((sched or {}).get("retention_years") or 3)

            cur.execute(
                """
                SELECT COUNT(*) FROM staging_meta.incremental_runs
                WHERE organization_id = %s AND status = 'COMPLETED'
                """,
                (organization_id,),
            )
            count = cur.fetchone()["count"]

        limit = _retention_limit(granularity, retention_years)
        if count <= limit:
            return None

        oldest = _find_oldest_completed_run(conn, organization_id, exclude_run_id=new_run_id)
        if not oldest:
            return None

        logger.info("Retention: purging run %s for org %s", oldest["run_id"], organization_id)
        purge_run(str(oldest["run_id"]))
        return str(oldest["run_id"])
    finally:
        conn.close()

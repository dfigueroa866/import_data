"""Purge staging batches and files (adapted from upload bulk purge)."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import List, Optional

import psycopg2

from data_staging.utils.batch_control import collect_batch_file_paths, normalize_metadata
from m8_incremental.config import settings

logger = logging.getLogger(__name__)


def purge_batch(batch_id: str) -> int:
    """Delete batch_control row, related jobs/logs, and files. Returns files deleted count."""
    conn = psycopg2.connect(str(settings.DATABASE_URL))
    files_deleted = 0
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT metadata FROM staging_meta.batch_control WHERE batch_id = %s",
                (batch_id,),
            )
            row = cur.fetchone()
            metadata = normalize_metadata(row[0]) if row else {}

            for path_str in collect_batch_file_paths(metadata, file_path_column=None):
                path = Path(path_str)
                try:
                    if path.is_file():
                        path.unlink()
                        files_deleted += 1
                    elif path.is_dir():
                        shutil.rmtree(path, ignore_errors=True)
                        files_deleted += 1
                except OSError as exc:
                    logger.warning("Could not delete %s: %s", path, exc)

            cur.execute(
                "DELETE FROM staging_meta.validation_logs WHERE batch_id = %s",
                (batch_id,),
            )
            cur.execute(
                "DELETE FROM staging_meta.job_queue WHERE payload->>'batch_id' = %s",
                (batch_id,),
            )
            cur.execute(
                "DELETE FROM staging_meta.load_history WHERE batch_id = %s",
                (batch_id,),
            )
            cur.execute(
                "DELETE FROM staging_meta.batch_control WHERE batch_id = %s",
                (batch_id,),
            )
        conn.commit()
    finally:
        conn.close()
    return files_deleted


def purge_run_directory(load_storage_parent: Path) -> int:
    """Remove entire date folder if empty after batch purge."""
    deleted = 0
    if load_storage_parent.is_dir():
        try:
            shutil.rmtree(load_storage_parent)
            deleted = 1
        except OSError as exc:
            logger.warning("Could not remove directory %s: %s", load_storage_parent, exc)
    return deleted


def purge_batches(batch_ids: List[str]) -> int:
    total = 0
    for bid in batch_ids:
        total += purge_batch(bid)
    return total

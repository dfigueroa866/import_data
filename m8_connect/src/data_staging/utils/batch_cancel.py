"""Cooperative cancellation checks for long-running batch jobs."""

from __future__ import annotations

import logging
from typing import Optional

import psycopg2

logger = logging.getLogger(__name__)


class BatchCancelledError(Exception):
    """Raised when batch_control.status is CANCELLED and work must stop."""


def is_batch_cancelled(batch_id: str, conn: Optional[psycopg2.extensions.connection] = None) -> bool:
    """Return True if the batch was cancelled by the user."""
    own_conn = False
    if conn is None:
        from data_staging.config import settings

        conn = psycopg2.connect(str(settings.DATABASE_URL))
        conn.autocommit = True
        own_conn = True
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT status
            FROM staging_meta.batch_control
            WHERE batch_id = %s
            """,
            (batch_id,),
        )
        row = cursor.fetchone()
        cursor.close()
        return row is not None and row[0] == "CANCELLED"
    finally:
        if own_conn:
            conn.close()


def raise_if_batch_cancelled(
    batch_id: str,
    conn: Optional[psycopg2.extensions.connection] = None,
) -> None:
    """Abort current work if the batch was cancelled."""
    if is_batch_cancelled(batch_id, conn):
        logger.info("Batch %s cancelled — stopping worker", batch_id)
        raise BatchCancelledError(f"Batch {batch_id} cancelled by user")

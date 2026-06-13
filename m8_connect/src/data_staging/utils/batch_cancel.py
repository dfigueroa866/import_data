"""Cooperative cancellation checks for long-running batch jobs."""

from __future__ import annotations

import logging
from typing import Optional

import psycopg2

logger = logging.getLogger(__name__)


class BatchCancelledError(Exception):
    """Raised when batch work must stop (cancelled or batch removed)."""


def is_batch_cancelled(
    batch_id: str,
    conn: Optional[psycopg2.extensions.connection] = None,
) -> bool:
    """Return True if the batch was cancelled or removed from batch_control.

    Always uses a dedicated autocommit connection so open worker transactions
    cannot hide a fresh CANCELLED status or a delete committed elsewhere.
    """
    del conn  # ignored — never read cancellation through the worker txn
    from data_staging.config import settings

    check_conn = psycopg2.connect(str(settings.DATABASE_URL))
    check_conn.autocommit = True
    try:
        cursor = check_conn.cursor()
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
        if row is None:
            logger.info("Batch %s no longer exists — treat as cancelled", batch_id)
            return True
        return row[0] == "CANCELLED"
    finally:
        check_conn.close()


def raise_if_batch_cancelled(
    batch_id: str,
    conn: Optional[psycopg2.extensions.connection] = None,
) -> None:
    """Abort current work if the batch was cancelled or deleted."""
    if is_batch_cancelled(batch_id, conn):
        logger.info("Batch %s cancelled — stopping worker", batch_id)
        raise BatchCancelledError(f"Batch {batch_id} cancelled or removed")

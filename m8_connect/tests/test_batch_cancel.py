"""Tests for cooperative batch cancellation."""

from unittest.mock import MagicMock, patch

import pytest

from data_staging.utils.batch_cancel import (
    BatchCancelledError,
    is_batch_cancelled,
    raise_if_batch_cancelled,
)


def test_is_batch_cancelled_true():
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    cursor.fetchone.return_value = ("CANCELLED",)

    assert is_batch_cancelled("batch-1", conn=conn) is True
    cursor.execute.assert_called_once()


def test_is_batch_cancelled_false():
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    cursor.fetchone.return_value = ("PROCESSING",)

    assert is_batch_cancelled("batch-1", conn=conn) is False


def test_raise_if_batch_cancelled_raises():
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    cursor.fetchone.return_value = ("CANCELLED",)

    with pytest.raises(BatchCancelledError, match="batch-1"):
        raise_if_batch_cancelled("batch-1", conn=conn)


def test_raise_if_batch_cancelled_ok():
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    cursor.fetchone.return_value = ("PENDING_PREVIEW",)

    raise_if_batch_cancelled("batch-1", conn=conn)


@patch("data_staging.workers.job_queue.psycopg2.connect")
def test_complete_job_skips_cancelled(mock_connect):
    from data_staging.workers.job_queue import PostgresQueueWorker

    conn = MagicMock()
    mock_connect.return_value = conn
    cursor = MagicMock()
    conn.cursor.return_value = cursor

    worker = PostgresQueueWorker("postgresql://test", "worker_1")
    worker._complete_job("job-1")

    sql = cursor.execute.call_args[0][0]
    assert "status = 'PROCESSING'" in sql


@patch("data_staging.workers.job_queue.psycopg2.connect")
def test_ack_cancelled_job(mock_connect):
    from data_staging.workers.job_queue import PostgresQueueWorker

    conn = MagicMock()
    mock_connect.return_value = conn
    cursor = MagicMock()
    conn.cursor.return_value = cursor

    worker = PostgresQueueWorker("postgresql://test", "worker_1")
    worker._ack_cancelled_job("job-1")

    sql = cursor.execute.call_args[0][0]
    assert "status = 'CANCELLED'" in sql
    assert "status = 'PROCESSING'" in sql

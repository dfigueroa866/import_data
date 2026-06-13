"""Tests for cooperative batch cancellation."""

from unittest.mock import MagicMock, patch

import pytest

from data_staging.utils.batch_cancel import (
    BatchCancelledError,
    is_batch_cancelled,
    raise_if_batch_cancelled,
)


def test_is_batch_cancelled_true():
    cursor = MagicMock()
    cursor.fetchone.return_value = ("CANCELLED",)

    with patch("data_staging.utils.batch_cancel.psycopg2.connect") as mock_connect:
        check_conn = MagicMock()
        check_conn.autocommit = True
        check_conn.cursor.return_value = cursor
        mock_connect.return_value = check_conn
        assert is_batch_cancelled("batch-1") is True
        cursor.execute.assert_called_once()


def test_is_batch_cancelled_false():
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    cursor.fetchone.return_value = ("PROCESSING",)

    with patch("data_staging.utils.batch_cancel.psycopg2.connect") as mock_connect:
        check_conn = MagicMock()
        check_conn.autocommit = True
        check_conn.cursor.return_value = cursor
        mock_connect.return_value = check_conn
        assert is_batch_cancelled("batch-1", conn=conn) is False


def test_is_batch_cancelled_when_batch_deleted():
    cursor = MagicMock()
    cursor.fetchone.return_value = None

    with patch("data_staging.utils.batch_cancel.psycopg2.connect") as mock_connect:
        check_conn = MagicMock()
        check_conn.autocommit = True
        check_conn.cursor.return_value = cursor
        mock_connect.return_value = check_conn
        assert is_batch_cancelled("batch-1") is True


def test_is_batch_cancelled_ignores_stale_worker_connection():
    stale_conn = MagicMock()
    stale_cursor = MagicMock()
    stale_conn.cursor.return_value = stale_cursor
    stale_cursor.fetchone.return_value = ("PROCESSING",)

    fresh_cursor = MagicMock()
    fresh_cursor.fetchone.return_value = ("CANCELLED",)
    fresh_conn = MagicMock()
    fresh_conn.autocommit = True
    fresh_conn.cursor.return_value = fresh_cursor

    with patch("data_staging.utils.batch_cancel.psycopg2.connect", return_value=fresh_conn):
        assert is_batch_cancelled("batch-1", conn=stale_conn) is True


def test_raise_if_batch_cancelled_raises():
    with patch("data_staging.utils.batch_cancel.is_batch_cancelled", return_value=True):
        with pytest.raises(BatchCancelledError, match="batch-1"):
            raise_if_batch_cancelled("batch-1")


def test_raise_if_batch_cancelled_ok():
    with patch("data_staging.utils.batch_cancel.is_batch_cancelled", return_value=False):
        raise_if_batch_cancelled("batch-1")


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

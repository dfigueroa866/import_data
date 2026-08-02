"""RUN_INCREMENTAL_LOAD job: preview → process → promote pipeline."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from data_staging.config import settings as connect_settings
from data_staging.services.history.history_config import HISTORY_TARGET_SCHEMA, HISTORY_TARGET_TABLE
from data_staging.utils.batch_control import normalize_metadata
from data_staging.workers.file_processor import process_file_job
from data_staging.workers.preview_worker import execute_preview_pipeline
from data_staging.workers.promotion_worker import promote_batch_job
from m8_incremental.config import settings
from m8_incremental.services.run_helpers import batch_source_row_stats, normalize_batch_ids

logger = logging.getLogger(__name__)


def _connect():
    return psycopg2.connect(str(settings.DATABASE_URL))


def _load_batch(batch_id: str) -> Optional[Dict[str, Any]]:
    conn = _connect()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM staging_meta.batch_control WHERE batch_id = %s",
                (batch_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def _aggregate_run_stats(run_id: str) -> None:
    conn = _connect()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT batch_ids FROM staging_meta.incremental_runs WHERE run_id = %s",
                (run_id,),
            )
            row = cur.fetchone()
            if not row or not row["batch_ids"]:
                return
            batch_ids = normalize_batch_ids(row["batch_ids"])
            total_processed = 0
            total_inserted = 0
            total_updated = 0
            total_rejected = 0
            all_promoted = True
            any_failed = False
            errors = []

            for bid in batch_ids:
                cur.execute(
                    "SELECT status, metadata, error_message FROM staging_meta.batch_control WHERE batch_id = %s",
                    (str(bid),),
                )
                batch = cur.fetchone()
                if not batch:
                    continue
                meta = normalize_metadata(batch["metadata"])
                row_stats = batch_source_row_stats(meta)
                total_processed += row_stats["source_rows"]
                total_rejected += row_stats["rejected_rows"]
                total_inserted += int(meta.get("promoted_inserted") or 0)
                total_updated += int(meta.get("promoted_updated") or 0)
                status = batch["status"]
                if status not in ("PROMOTED", "PARTIALLY_PROMOTED", "COMPLETED"):
                    all_promoted = False
                if status == "FAILED":
                    any_failed = True
                    if batch.get("error_message"):
                        errors.append(batch["error_message"])

            run_status = "COMPLETED"
            error_message = None
            if any_failed:
                run_status = "FAILED"
                error_message = "; ".join(errors)[:2000] if errors else "Uno o más batches fallaron"
            elif not all_promoted:
                run_status = "PROCESSING"

            cur.execute(
                """
                UPDATE staging_meta.incremental_runs
                SET status = %s::staging_meta.incremental_run_status,
                    total_processed = %s,
                    total_inserted = %s,
                    total_updated = %s,
                    total_rejected = %s,
                    error_message = COALESCE(%s, error_message),
                    finished_at = CASE WHEN %s IN ('COMPLETED', 'FAILED') THEN CURRENT_TIMESTAMP ELSE finished_at END
                WHERE run_id = %s
                """,
                (
                    run_status,
                    total_processed,
                    total_inserted,
                    total_updated,
                    total_rejected,
                    error_message,
                    run_status,
                    run_id,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def _all_batches_done(run_id: str) -> bool:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT batch_ids FROM staging_meta.incremental_runs WHERE run_id = %s",
                (run_id,),
            )
            row = cur.fetchone()
            if not row or not row[0]:
                return True
            for bid in normalize_batch_ids(row[0]):
                cur.execute(
                    "SELECT status FROM staging_meta.batch_control WHERE batch_id = %s",
                    (str(bid),),
                )
                status_row = cur.fetchone()
                if not status_row:
                    continue
                if status_row[0] not in (
                    "PROMOTED",
                    "PARTIALLY_PROMOTED",
                    "FAILED",
                    "CANCELLED",
                    "COMPLETED",
                ):
                    return False
            return True
    finally:
        conn.close()


def run_incremental_load_job(payload: Dict[str, Any]) -> None:
    """Execute full incremental pipeline for one batch."""
    batch_id = payload.get("batch_id")
    org_id = payload.get("organization_id")
    run_id = payload.get("incremental_run_id")

    if not batch_id or not org_id:
        raise ValueError("batch_id and organization_id are required")

    batch = _load_batch(batch_id)
    if not batch:
        raise ValueError(f"Batch {batch_id} not found")

    metadata = normalize_metadata(batch.get("metadata"))
    load_type = metadata.get("load_type", "history")
    target_schema = metadata.get("target_schema") or HISTORY_TARGET_SCHEMA
    target_table = metadata.get("target_table") or HISTORY_TARGET_TABLE

    error: Optional[str] = None
    try:
        logger.info("Incremental load: preview batch %s", batch_id)
        execute_preview_pipeline(batch_id, org_id)

        batch = _load_batch(batch_id)
        metadata = normalize_metadata(batch.get("metadata") if batch else {})
        if metadata.get("preview_error"):
            raise RuntimeError(str(metadata["preview_error"]))

        logger.info("Incremental load: process batch %s", batch_id)
        process_file_job({"batch_id": batch_id, "organization_id": org_id})

        batch = _load_batch(batch_id)
        metadata = normalize_metadata(batch.get("metadata") if batch else {})
        if batch and batch.get("status") == "FAILED":
            raise RuntimeError(batch.get("error_message") or "Procesamiento falló")

        logger.info("Incremental load: promote batch %s", batch_id)
        promote_batch_job(
            {
                "batch_id": batch_id,
                "target_schema": target_schema,
                "target_table": target_table,
            }
        )
    except Exception as exc:
        error = str(exc)
        logger.exception("Incremental load failed for batch %s: %s", batch_id, exc)
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE staging_meta.batch_control
                    SET status = 'FAILED', error_message = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE batch_id = %s AND status NOT IN ('PROMOTED', 'PARTIALLY_PROMOTED')
                    """,
                    (error[:2000], batch_id),
                )
            conn.commit()
        finally:
            conn.close()
        if run_id:
            _aggregate_run_stats(run_id)
            if _all_batches_done(run_id):
                try:
                    from m8_incremental.services.email_service import notify_run_if_complete

                    notify_run_if_complete(run_id)
                except Exception as notify_exc:
                    logger.error("Notification after failure: %s", notify_exc)
        raise

    if run_id:
        _aggregate_run_stats(run_id)
        if _all_batches_done(run_id):
            try:
                from m8_incremental.services.email_service import notify_run_if_complete
                from m8_incremental.services.retention import apply_retention_after_success

                notify_run_if_complete(run_id)
                conn = _connect()
                try:
                    with conn.cursor(cursor_factory=RealDictCursor) as cur:
                        cur.execute(
                            "SELECT organization_id, status, metadata FROM staging_meta.incremental_runs WHERE run_id = %s",
                            (run_id,),
                        )
                        run_row = cur.fetchone()
                    if run_row and run_row["status"] == "COMPLETED":
                        meta = run_row.get("metadata") or {}
                        if isinstance(meta, str):
                            meta = json.loads(meta)
                        granularity = meta.get("granularity") or "weekly"
                        apply_retention_after_success(
                            str(run_row["organization_id"]),
                            granularity,
                            run_id,
                        )
                finally:
                    conn.close()
            except Exception as notify_exc:
                logger.error("Post-run notification/retention failed: %s", notify_exc)

#!/usr/bin/env python3
"""APScheduler entry point for incremental loads."""

from __future__ import annotations

import logging
import signal
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("m8_incremental.scheduler")

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT.parent / "m8_connect" / "src"))

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import psycopg2
from psycopg2.extras import RealDictCursor

from m8_incremental.config import settings
from m8_incremental.services.orchestrator import run_all_pending


def _load_schedule() -> dict:
    conn = psycopg2.connect(str(settings.DATABASE_URL))
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM staging_meta.incremental_schedule WHERE id = 1")
            row = cur.fetchone()
            return dict(row) if row else {}
    finally:
        conn.close()


def _tick():
    sched = _load_schedule()
    if not sched.get("enabled", True):
        logger.info("Incremental schedule disabled; skipping tick")
        return
    logger.info("Starting scheduled incremental run")
    run_ids = run_all_pending()
    logger.info("Enqueued %s incremental run(s): %s", len(run_ids), run_ids)


def main():
    sched = _load_schedule()
    cron = sched.get("cron_expression") or "0 22 * * 0"
    tz = sched.get("timezone") or "America/Mexico_City"

    scheduler = BlockingScheduler(timezone=tz)
    scheduler.add_job(_tick, CronTrigger.from_crontab(cron, timezone=tz), id="incremental_load")

    def shutdown(signum, frame):
        logger.info("Shutting down scheduler")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    logger.info("M8 Incremental Scheduler — cron=%s tz=%s", cron, tz)
    scheduler.start()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Workers for m8_incremental (RUN_INCREMENTAL_LOAD)."""

from __future__ import annotations

import logging
import signal
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
(ROOT / "logs").mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/incremental_workers.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT.parent / "m8_connect" / "src"))

from data_staging.config import settings as connect_settings
from data_staging.workers.job_queue import PostgresQueueWorker
from m8_incremental.workers.incremental_load import run_incremental_load_job


def start_workers(num_workers: int = 1):
    workers = []
    threads = []
    for i in range(num_workers):
        worker_id = f"incremental_worker_{i + 1}"
        worker = PostgresQueueWorker(
            database_url=str(connect_settings.DATABASE_URL),
            worker_id=worker_id,
            poll_interval=5,
            use_notify=False,
            job_types=["RUN_INCREMENTAL_LOAD"],
        )
        worker.register_handler("RUN_INCREMENTAL_LOAD", run_incremental_load_job)
        thread = threading.Thread(target=worker.start, name=worker_id, daemon=False)
        thread.start()
        workers.append(worker)
        threads.append(thread)
        logger.info("Started %s", worker_id)
    return workers, threads


def main():
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    workers, threads = start_workers(1)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for w in workers:
            w.stop()
        for t in threads:
            t.join(timeout=10)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Inicia workers para procesamiento asíncrono.
"""
import sys
import logging
import signal
import threading
import time
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/workers.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Import después de logging setup
# Add src to path first to ensure we use the correct data_staging package
sys.path.insert(0, str(Path(__file__).parent / "src"))

import data_staging.workers.file_processor as fp
print(f"DEBUG: LOADED FILE_PROCESSOR FROM: {fp.__file__}")

try:
    from data_staging.config import settings
    from data_staging.workers.job_queue import PostgresQueueWorker
    from data_staging.workers.file_processor import process_file_job
    from data_staging.workers.promotion_worker import promote_batch_job
except ImportError as e:
    logger.error(f"Error importing modules: {e}")
    sys.exit(1)


def start_workers(num_workers: int = 3):
    """Inicia múltiples workers."""
    workers = []
    threads = []
    
    logger.info(f"Starting {num_workers} workers...")
    
    for i in range(num_workers):
        worker_id = f"worker_{i+1}"
        
        # Crear worker
        worker = PostgresQueueWorker(
            database_url=str(settings.DATABASE_URL),
            worker_id=worker_id,
            poll_interval=5,
            use_notify=False  # Disabled LISTEN/NOTIFY string connection tie for Supabase pooler
        )
        
        # Registrar handlers
        worker.register_handler("PROCESS_FILE", process_file_job)
        worker.register_handler("PROMOTE_BATCH", promote_batch_job)
        
        # Iniciar en thread separado
        thread = threading.Thread(
            target=worker.start,
            name=worker_id,
            daemon=False
        )
        
        thread.start()
        
        workers.append(worker)
        threads.append(thread)
        
        logger.info(f"Worker {worker_id} started")
    
    return workers, threads


def shutdown_workers(workers, threads):
    """Detiene todos los workers gracefully."""
    logger.info("Shutting down workers...")
    
    for worker in workers:
        worker.stop()
    
    # Wait for threads
    for thread in threads:
        thread.join(timeout=10)
    
    logger.info("All workers stopped")


def signal_handler(signum, frame):
    """Handler para SIGINT/SIGTERM."""
    logger.info("Received shutdown signal")
    # This raises KeyboardInterrupt in main thread or just exits
    sys.exit(0)


def main():
    """Main entry point."""
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Número de workers (configurable)
    # Reducido a 1 para evitar agotar el pool de 15 conexiones (Supabase Port 5432)
    num_workers = 1  # getattr(settings, 'num_workers', 3)
    
    logger.info("=" * 50)
    logger.info("Data Staging Workers")
    logger.info("=" * 50)
    
    workers = []
    threads = []
    
    try:
        # Iniciar workers
        workers, threads = start_workers(num_workers)
        
        logger.info(f"{num_workers} workers running. Press CTRL+C to stop.")
        
        # Esperar indefinidamente (mantener main thread vivo)
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except SystemExit:
        logger.info("System exit received")
    except Exception as e:
        logger.error(f"Error: {e}")
        return 1
    finally:
        shutdown_workers(workers, threads)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

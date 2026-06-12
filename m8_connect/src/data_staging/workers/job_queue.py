"""
Sistema de colas usando PostgreSQL.
"""
import time
import logging
import json
import psycopg2
import select
from datetime import datetime
from contextlib import contextmanager
from typing import Optional, Callable, Dict, Any, List

logger = logging.getLogger(__name__)


def parse_job_payload(payload) -> Dict[str, Any]:
    """Normalize job payload from DB (json/jsonb may arrive as str)."""
    if payload is None:
        return {}
    if isinstance(payload, str):
        return json.loads(payload)
    if isinstance(payload, dict):
        return payload
    return {}


def sync_batch_on_job_failure(
    database_url: str,
    payload,
    error_message: str,
    job_type: str,
) -> None:
    """Mark batch_control as FAILED when a background job dies permanently."""
    data = parse_job_payload(payload)
    batch_id = data.get("batch_id")
    if not batch_id:
        return

    if job_type == "PREVIEW_BATCH":
        label = "Vista previa"
    elif job_type == "PROCESS_FILE":
        label = "Procesamiento"
    else:
        label = "Promoción"
    full_error = f"{label} falló: {error_message}"[:2000]

    conn = psycopg2.connect(database_url)
    try:
        cursor = conn.cursor()
        if job_type == "PREVIEW_BATCH":
            cursor.execute(
                """
                UPDATE staging_meta.batch_control
                SET metadata = metadata
                    || jsonb_build_object(
                        'preview_in_progress', false,
                        'preview_error', %s
                    ),
                    updated_at = CURRENT_TIMESTAMP
                WHERE batch_id = %s
                """,
                (full_error, batch_id),
            )
        else:
            cursor.execute(
                """
                UPDATE staging_meta.batch_control
                SET status = 'FAILED',
                    error_message = %s,
                    completed_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE batch_id = %s
                  AND status NOT IN ('PROMOTED', 'PARTIALLY_PROMOTED')
                """,
                (full_error, batch_id),
            )
        conn.commit()
    finally:
        conn.close()


class PostgresQueueWorker:
    """Worker que procesa jobs desde PostgreSQL."""
    
    def __init__(
        self, 
        database_url: str,
        worker_id: str,
        poll_interval: int = 5,
        use_notify: bool = True
    ):
        self.database_url = database_url
        self.worker_id = worker_id
        self.poll_interval = poll_interval
        self.use_notify = use_notify
        self.running = False
        self.handlers: Dict[str, Callable] = {}
        
    def register_handler(self, job_type: str, handler: Callable):
        """Registra un handler para un tipo de job."""
        self.handlers[job_type] = handler
        logger.info(f"Worker {self.worker_id}: Registered handler for '{job_type}'")
    
    def start(self):
        """Inicia el worker."""
        self.running = True
        logger.info(f"Worker {self.worker_id}: Starting...")
        
        if self.use_notify:
            self._work_loop_with_notify()
        else:
            self._work_loop_polling()
    
    def stop(self):
        """Detiene el worker."""
        self.running = False
        logger.info(f"Worker {self.worker_id}: Stopping...")
    
    def _work_loop_polling(self):
        """Loop de trabajo con polling simple."""
        while self.running:
            try:
                job = self._fetch_next_job()
                
                if job:
                    self._process_job(job)
                else:
                    time.sleep(self.poll_interval)
            except Exception as e:
                logger.error(f"Worker {self.worker_id}: Error in polling loop: {e}")
                time.sleep(self.poll_interval)
    
    def _work_loop_with_notify(self):
        """Loop de trabajo con LISTEN/NOTIFY (más eficiente)."""
        conn = None
        try:
            conn = psycopg2.connect(self.database_url)
            conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
            
            cursor = conn.cursor()
            cursor.execute("LISTEN new_job_queued;")
            logger.info(f"Worker {self.worker_id}: Listening for notifications...")
            
            while self.running:
                # Procesar todos los jobs pendientes primero
                while self.running:
                    try:
                        job = self._fetch_next_job()
                        if not job:
                            break
                        self._process_job(job)
                    except Exception as e:
                        logger.error(f"Worker {self.worker_id}: Error processing job loop: {e}")
                        break
                
                if not self.running:
                    break

                # Esperar notificación con timeout
                if select.select([conn], [], [], self.poll_interval) == ([], [], []):
                    # Timeout - revisar si hay jobs de nuevo (por si acaso se perdió notificación)
                    continue
                
                conn.poll()
                while conn.notifies:
                    notify = conn.notifies.pop(0)
                    logger.debug(f"Worker {self.worker_id}: Received notification for job {notify.payload}")
                    # El loop while interno capturará el job
                    
        except Exception as e:
            logger.error(f"Worker {self.worker_id}: Error in notify loop: {e}")
            # Fallback a polling si falla la conexión LISTEN
            time.sleep(self.poll_interval)
            if self.running:
                self._work_loop_with_notify() # Retry connection
        finally:
            if conn:
                conn.close()
    
    def _fetch_next_job(self) -> Optional[Dict[str, Any]]:
        """
        Obtiene el siguiente job pendiente.
        Usa FOR UPDATE SKIP LOCKED para evitar race conditions.
        """
        conn = psycopg2.connect(self.database_url)
        conn.autocommit = False
        
        try:
            cursor = conn.cursor()
            
            # Usar FOR UPDATE SKIP LOCKED es crucial para evitar bloqueos
            cursor.execute("""
                UPDATE staging_meta.job_queue
                SET status = 'PROCESSING',
                    started_at = CURRENT_TIMESTAMP,
                    worker_id = %s
                WHERE job_id = (
                    SELECT job_id
                    FROM staging_meta.job_queue
                    WHERE status = 'PENDING'
                    ORDER BY priority DESC, created_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                RETURNING job_id, job_type, payload, retry_count, max_retries
            """, (self.worker_id,))
            
            job = cursor.fetchone()
            conn.commit()
            
            if job:
                return {
                    "job_id": str(job[0]),
                    "job_type": job[1],
                    "payload": job[2],
                    "retry_count": job[3],
                    "max_retries": job[4]
                }
            
            return None
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Worker {self.worker_id}: Error fetching job: {e}")
            return None
        finally:
            conn.close()
    
    def _process_job(self, job: Dict[str, Any]):
        """Procesa un job."""
        job_id = job["job_id"]
        job_type = job["job_type"]
        payload = parse_job_payload(job["payload"])
        
        logger.info(f"Worker {self.worker_id}: Processing job {job_id} ({job_type})")
        
        try:
            # Buscar handler
            handler = self.handlers.get(job_type)
            
            if not handler:
                raise Exception(f"No handler registered for job type '{job_type}'")
            
            # Ejecutar handler
            handler(payload)
            
            # Marcar como completado
            self._complete_job(job_id)
            logger.info(f"Worker {self.worker_id}: Job {job_id} completed successfully")
            
        except Exception as e:
            logger.error(f"Worker {self.worker_id}: Job {job_id} failed: {e}")
            self._fail_job(
                job_id,
                str(e),
                job["retry_count"],
                job["max_retries"],
                payload,
                job_type,
            )
    
    def _complete_job(self, job_id: str):
        """Marca un job como completado."""
        conn = psycopg2.connect(self.database_url)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE staging_meta.job_queue
                SET status = 'COMPLETED',
                    completed_at = CURRENT_TIMESTAMP
                WHERE job_id = %s
            """, (job_id,))
            conn.commit()
        finally:
            conn.close()
    
    def _fail_job(
        self,
        job_id: str,
        error_message: str,
        retry_count: int,
        max_retries: int,
        payload: Dict[str, Any],
        job_type: str,
    ):
        """Marca un job como fallido o lo reintenta."""
        conn = psycopg2.connect(self.database_url)
        try:
            cursor = conn.cursor()
            
            if retry_count < max_retries:
                # Reintentar
                new_status = 'PENDING'
                new_retry = retry_count + 1
                logger.info(f"Job {job_id}: Retry {new_retry}/{max_retries}")
            else:
                # Falló definitivamente
                new_status = 'FAILED'
                new_retry = retry_count
                logger.error(f"Job {job_id}: Failed permanently after {retry_count} retries")
            
            cursor.execute("""
                UPDATE staging_meta.job_queue
                SET status = %s,
                    retry_count = %s,
                    error_message = %s,
                    completed_at = CASE WHEN %s = 'FAILED' THEN CURRENT_TIMESTAMP ELSE NULL END,
                    started_at = NULL,
                    worker_id = NULL
                WHERE job_id = %s
            """, (new_status, new_retry, error_message, new_status, job_id))
            conn.commit()

            if new_status == 'FAILED':
                try:
                    sync_batch_on_job_failure(
                        self.database_url,
                        payload,
                        error_message,
                        job_type,
                    )
                except Exception as sync_err:
                    logger.error(f"Job {job_id}: Could not sync batch failure: {sync_err}")
        finally:
            conn.close()


def create_job(database_url: str, job_type: str, payload: Dict[str, Any], priority: int = 0) -> str:
    """Crea un nuevo job en la cola."""
    conn = psycopg2.connect(database_url)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO staging_meta.job_queue (job_type, payload, priority)
            VALUES (%s, %s, %s)
            RETURNING job_id
        """, (job_type, json.dumps(payload, default=str), priority))
        
        job_id = cursor.fetchone()[0]
        conn.commit()
        return str(job_id)
    finally:
        conn.close()


def get_job_status(database_url: str, job_id: str) -> Optional[Dict[str, Any]]:
    """Obtiene el estado de un job."""
    conn = psycopg2.connect(database_url)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT job_id, job_type, status, created_at, started_at, 
                   completed_at, retry_count, error_message
            FROM staging_meta.job_queue
            WHERE job_id = %s
        """, (job_id,))
        
        row = cursor.fetchone()
        if not row:
            return None
        
        return {
            "job_id": str(row[0]),
            "job_type": row[1],
            "status": row[2],
            "created_at": row[3].isoformat() if row[3] else None,
            "started_at": row[4].isoformat() if row[4] else None,
            "completed_at": row[5].isoformat() if row[5] else None,
            "retry_count": row[6],
            "error_message": row[7]
        }
    finally:
        conn.close()

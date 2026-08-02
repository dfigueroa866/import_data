"""Email notifications for incremental load runs."""

from __future__ import annotations

import logging
import smtplib
import zipfile
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from data_staging.utils.batch_control import normalize_metadata
from data_staging.utils.batch_staging_files import rejected_records_path
from m8_incremental.config import settings
from m8_incremental.services.run_helpers import normalize_batch_ids

logger = logging.getLogger(__name__)

MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024


def _connect():
    return psycopg2.connect(str(settings.DATABASE_URL))


def _collect_rejected_files(batch_ids: List[str]) -> List[Path]:
    paths: List[Path] = []
    conn = _connect()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            for bid in batch_ids:
                cur.execute(
                    "SELECT metadata FROM staging_meta.batch_control WHERE batch_id = %s",
                    (str(bid),),
                )
                row = cur.fetchone()
                if not row:
                    continue
                meta = normalize_metadata(row["metadata"])
                path = rejected_records_path(str(bid), meta)
                if path.is_file() and path.stat().st_size > 0:
                    paths.append(path)
    finally:
        conn.close()
    return paths


def _build_attachment(paths: List[Path]) -> Optional[tuple[str, bytes, str]]:
    if not paths:
        return None
    if len(paths) == 1 and paths[0].stat().st_size <= MAX_ATTACHMENT_BYTES:
        data = paths[0].read_bytes()
        return paths[0].name, data, "text/tab-separated-values"
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in paths:
            zf.write(path, arcname=path.name)
    data = buf.getvalue()
    if len(data) > MAX_ATTACHMENT_BYTES:
        logger.warning("Rejected attachment exceeds size limit; sending without attachment")
        return None
    return "rejected_records.zip", data, "application/zip"


def _send_email(
    recipients: List[str],
    subject: str,
    body: str,
    attachment: Optional[tuple[str, bytes, str]] = None,
) -> None:
    if not settings.ALERT_EMAIL_ENABLED:
        logger.info("Email disabled; would send: %s", subject)
        return
    if not settings.SMTP_SERVER or not recipients:
        logger.warning("SMTP or recipients not configured")
        return

    msg = MIMEMultipart()
    msg["From"] = settings.EMAIL_FROM or settings.SMTP_USERNAME or "noreply@m8.local"
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    if attachment:
        name, data, mime = attachment
        part = MIMEApplication(data, Name=name)
        part["Content-Disposition"] = f'attachment; filename="{name}"'
        msg.attach(part)

    with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT) as server:
        if settings.SMTP_USE_TLS:
            server.starttls()
        if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        server.sendmail(msg["From"], recipients, msg.as_string())


def notify_run_result(run_id: str) -> None:
    conn = _connect()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT r.*, p.organization_name, p.notification_emails
                FROM staging_meta.incremental_runs r
                LEFT JOIN staging_meta.incremental_org_profiles p
                  ON p.organization_id = r.organization_id
                WHERE r.run_id = %s
                """,
                (run_id,),
            )
            run = cur.fetchone()
        if not run:
            return

        recipients = list(run.get("notification_emails") or [])
        if settings.INCREMENTAL_ADMIN_EMAIL:
            recipients.append(settings.INCREMENTAL_ADMIN_EMAIL)
        recipients = list({r.strip() for r in recipients if r and r.strip()})
        if not recipients:
            return

        org_name = run.get("organization_name") or run["organization_id"]
        load_date = run["load_date"]
        success = run["status"] == "COMPLETED"
        batch_ids = normalize_batch_ids(run.get("batch_ids"))
        rejected_paths = _collect_rejected_files(batch_ids)
        attachment = _build_attachment(rejected_paths)

        if success:
            subject = f"[M8 Incremental] Carga OK — {org_name} — {load_date}"
            body = (
                f"Carga incremental completada.\n\n"
                f"Organización: {org_name}\n"
                f"Fecha: {load_date}\n"
                f"Insertados: {run.get('total_inserted', 0)}\n"
                f"Actualizados: {run.get('total_updated', 0)}\n"
                f"Rechazados: {run.get('total_rejected', 0)}\n"
            )
        else:
            subject = f"[M8 Incremental] Carga FALLIDA — {org_name}"
            body = (
                f"La carga incremental falló.\n\n"
                f"Organización: {org_name}\n"
                f"Fecha: {load_date}\n"
                f"Motivo: {run.get('error_message') or 'Error desconocido'}\n"
                f"Rechazados: {run.get('total_rejected', 0)}\n"
            )

        try:
            _send_email(recipients, subject, body, attachment)
        except Exception as exc:
            logger.exception("Failed to send incremental email: %s", exc)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE staging_meta.incremental_runs
                    SET status = 'NOTIFICATION_FAILED'
                    WHERE run_id = %s AND status = 'COMPLETED'
                    """,
                    (run_id,),
                )
            conn.commit()
    finally:
        conn.close()


def notify_run_if_complete(run_id: str) -> None:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status FROM staging_meta.incremental_runs WHERE run_id = %s",
                (run_id,),
            )
            row = cur.fetchone()
            if row and row[0] in ("COMPLETED", "FAILED"):
                notify_run_result(run_id)
    finally:
        conn.close()

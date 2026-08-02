"""Orchestrate scheduled incremental loads per organization."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from data_staging.config import settings as connect_settings
from data_staging.services.batch_factory import create_incremental_batch
from data_staging.services.catalog.catalog_registry import get_catalog_table, resolve_catalog_db_target
from data_staging.services.history.history_catalog_prerequisites import (
    check_history_catalog_readiness,
    normalize_catalog_slug,
)
from data_staging.services.history.history_config import (
    HISTORY_SOURCE_NAME,
    HISTORY_TARGET_SCHEMA,
    HISTORY_TARGET_TABLE,
)
from data_staging.utils.organization import fetch_organization_name
from data_staging.workers.job_queue import create_job
from m8_incremental.config import default_source_root, settings
from m8_incremental.paths import (
    ensure_incremental_storage_dir,
    format_load_date,
    resolve_source_dir,
    source_catalog_dir,
    source_history_dir,
)
from m8_incremental.services.mapping_resolver import build_incremental_mappings
from m8_incremental.services.source_matcher import (
    catalog_mapping_targets,
    catalog_slug_for_filename,
    match_catalog_source_file,
)

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".parquet", ".tsv"}


def _connect():
    return psycopg2.connect(str(settings.DATABASE_URL))


def _list_source_files(directory: Path) -> List[Path]:
    if not directory.is_dir():
        return []
    files = []
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append(path)
    return files


def _fetch_enabled_profiles(conn) -> List[Dict[str, Any]]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT p.*,
                   COALESCE(
                       (SELECT json_agg(t ORDER BY t.load_kind, t.catalog_slug)
                        FROM staging_meta.incremental_org_tables t
                        WHERE t.organization_id = p.organization_id AND t.enabled = true),
                       '[]'::json
                   ) AS tables
            FROM staging_meta.incremental_org_profiles p
            WHERE p.enabled = true
            ORDER BY p.organization_name
        """)
        return list(cur.fetchall())


def _create_run(conn, organization_id: str, load_date: date) -> str:
    run_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO staging_meta.incremental_runs
            (run_id, organization_id, load_date, status)
            VALUES (%s, %s, %s, 'PENDING')
            """,
            (run_id, organization_id, load_date),
        )
    conn.commit()
    return run_id


def _record_skip(
    skipped_items: List[Dict[str, Any]],
    skip_messages: List[str],
    *,
    load_kind: str,
    reason: str,
    catalog_slug: Optional[str] = None,
    granularity: Optional[str] = None,
    file_name: Optional[str] = None,
) -> None:
    skip_messages.append(reason)
    skipped_items.append(
        {
            "load_kind": load_kind,
            "catalog_slug": catalog_slug,
            "granularity": granularity,
            "file_name": file_name,
            "reason": reason,
        }
    )


def _record_enqueued(
    enqueued_items: List[Dict[str, Any]],
    *,
    load_kind: str,
    batch_id: str,
    file_name: str,
    catalog_slug: Optional[str] = None,
    granularity: Optional[str] = None,
) -> None:
    enqueued_items.append(
        {
            "load_kind": load_kind,
            "catalog_slug": catalog_slug,
            "granularity": granularity,
            "file_name": file_name,
            "batch_id": batch_id,
        }
    )


def _execution_metadata_patch(
    enqueued_items: List[Dict[str, Any]],
    skipped_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "execution_summary": {
            "enqueued": enqueued_items,
            "skipped": skipped_items,
        }
    }


def _update_run(
    conn,
    run_id: str,
    *,
    status: Optional[str] = None,
    error_message: Optional[str] = None,
    batch_ids: Optional[List[str]] = None,
    metadata_patch: Optional[Dict[str, Any]] = None,
) -> None:
    sets = []
    params: List[Any] = []
    if status:
        sets.append("status = %s")
        params.append(status)
        if status in ("COMPLETED", "FAILED", "NOTIFICATION_FAILED"):
            sets.append("finished_at = CURRENT_TIMESTAMP")
    if error_message is not None:
        sets.append("error_message = %s")
        params.append(error_message)
    if batch_ids is not None:
        sets.append("batch_ids = %s::uuid[]")
        params.append(batch_ids)
    if metadata_patch is not None:
        sets.append("metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb")
        params.append(json.dumps(metadata_patch))
    if not sets:
        return
    params.append(run_id)
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE staging_meta.incremental_runs SET {', '.join(sets)} WHERE run_id = %s",
            params,
        )
    conn.commit()


def _enqueue_incremental_load(batch_id: str, organization_id: str, run_id: str) -> str:
    return create_job(
        str(settings.DATABASE_URL),
        "RUN_INCREMENTAL_LOAD",
        {
            "batch_id": batch_id,
            "organization_id": organization_id,
            "incremental_run_id": run_id,
        },
        priority=10,
    )


def _history_ready(conn, organization_id: str, promoted_this_run: List[str]) -> Dict[str, Any]:
    """Check catalog readiness; promoted_this_run slugs count as satisfied."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(str(settings.DATABASE_URL))
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        readiness = check_history_catalog_readiness(db, organization_id)
        if readiness.get("ready"):
            return readiness
        missing = set(readiness.get("missing_catalogs") or [])
        for slug in promoted_this_run:
            missing.discard(normalize_catalog_slug(slug) or slug)
        if not missing:
            return {"ready": True, "missing_catalogs": []}
        return {
            "ready": False,
            "missing_catalogs": sorted(missing),
            "message": readiness.get("message"),
        }
    finally:
        db.close()


class IncrementalOrchestrator:
    """Scan source folders and enqueue incremental load jobs."""

    def __init__(self, load_date: Optional[date] = None):
        self.load_date = load_date or date.today()
        self.fallback_root = default_source_root()

    def run_all_enabled(self) -> List[str]:
        conn = _connect()
        run_ids: List[str] = []
        try:
            profiles = _fetch_enabled_profiles(conn)
            for profile in profiles:
                try:
                    run_id = self.run_organization(dict(profile), conn=conn)
                    if run_id:
                        run_ids.append(run_id)
                except Exception as exc:
                    logger.exception("Incremental run failed for org %s: %s", profile.get("organization_id"), exc)
        finally:
            conn.close()
        return run_ids

    def run_organization(
        self,
        profile: Dict[str, Any],
        *,
        conn=None,
        external_conn: bool = False,
    ) -> Optional[str]:
        own_conn = conn is None
        if own_conn:
            conn = _connect()
        organization_id = str(profile["organization_id"])
        org_name = profile.get("organization_name") or organization_id
        tables = profile.get("tables") or []
        if isinstance(tables, str):
            import json

            tables = json.loads(tables)

        run_id = _create_run(conn, organization_id, self.load_date)
        _update_run(conn, run_id, status="PROCESSING")

        try:
            source_root = resolve_source_dir(
                profile["source_path"],
                fallback_root=self.fallback_root,
            )
        except FileNotFoundError as exc:
            _update_run(conn, run_id, status="FAILED", error_message=str(exc))
            if own_conn:
                conn.close()
            return run_id

        batch_ids: List[str] = []
        promoted_catalogs: List[str] = []
        skip_messages: List[str] = []
        enqueued_items: List[Dict[str, Any]] = []
        skipped_items: List[Dict[str, Any]] = []
        load_ts = datetime.now()

        catalog_tables = [t for t in tables if t.get("load_kind") == "catalog" and t.get("enabled", True)]
        history_tables = [t for t in tables if t.get("load_kind") == "history" and t.get("enabled", True)]

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        engine = create_engine(str(settings.DATABASE_URL))
        Session = sessionmaker(bind=engine)

        for table_cfg in catalog_tables:
            slug = normalize_catalog_slug(table_cfg.get("catalog_slug")) or table_cfg.get("catalog_slug")
            if not slug:
                continue
            catalog_entry = get_catalog_table(slug)
            if not catalog_entry:
                msg = f"Catálogo '{slug}' omitido: slug no registrado en definiciones"
                logger.warning(msg)
                _record_skip(
                    skipped_items,
                    skip_messages,
                    load_kind="catalog",
                    catalog_slug=slug,
                    reason=msg,
                )
                continue

            cat_dir = source_catalog_dir(source_root)
            catalog_files = _list_source_files(cat_dir)
            source_file = match_catalog_source_file(catalog_files, slug, catalog_entry)
            if not source_file:
                slug_key = catalog_slug_for_filename(slug)
                msg = (
                    f"Catálogo '{slug}' omitido: no hay archivo cuyo nombre contenga "
                    f"'{slug_key}' en {cat_dir} "
                    f"(archivos: {[f.name for f in catalog_files] or 'ninguno'})"
                )
                logger.warning(msg)
                _record_skip(
                    skipped_items,
                    skip_messages,
                    load_kind="catalog",
                    catalog_slug=slug,
                    reason=msg,
                )
                continue
            storage_dir = ensure_incremental_storage_dir(
                organization_id,
                "catalog",
                organization_name=org_name,
                load_date=self.load_date,
            )

            db = Session()
            try:
                from data_staging.api.v1.upload import upload_service

                file_analysis = upload_service.analyze_file_structure(source_file)
                headers = file_analysis.get("columns", [])
                mapping_targets = catalog_mapping_targets(catalog_entry)
                optional_targets = [
                    col
                    for col in (catalog_entry.get("optional_columns") or [])
                    if col not in mapping_targets
                ]
                mappings, toggles, _, missing = build_incremental_mappings(
                    file_headers=headers,
                    load_type="catalog",
                    organization_id=organization_id,
                    catalog_targets=mapping_targets,
                    catalog_optional_targets=optional_targets,
                    column_aliases=catalog_entry.get("column_aliases") or {},
                )
                if missing:
                    msg = (
                        f"Catálogo '{slug}' no procesado: el archivo '{source_file.name}' "
                        f"no tiene las columnas requeridas ({', '.join(missing)})"
                    )
                    logger.warning(msg)
                    _record_skip(
                        skipped_items,
                        skip_messages,
                        load_kind="catalog",
                        catalog_slug=slug,
                        file_name=source_file.name,
                        reason=msg,
                    )
                    continue
                target_schema, target_table = resolve_catalog_db_target(slug)
                batch_id = create_incremental_batch(
                    db,
                    organization_id=organization_id,
                    source_file=source_file,
                    storage_dir=storage_dir,
                    load_type="catalog",
                    load_timestamp=load_ts,
                    target_schema=target_schema,
                    target_table=target_table,
                    source_name=slug,
                    catalog_name=slug,
                    production_table=catalog_entry.get("target_table") or slug,
                    column_mappings=mappings,
                    column_toggles=toggles,
                    incremental_run_id=run_id,
                )
                db.commit()
                batch_ids.append(batch_id)
                promoted_catalogs.append(slug)
                _record_enqueued(
                    enqueued_items,
                    load_kind="catalog",
                    catalog_slug=slug,
                    file_name=source_file.name,
                    batch_id=batch_id,
                )
                _enqueue_incremental_load(batch_id, organization_id, run_id)
            finally:
                db.close()

        if history_tables and connect_settings.HISTORY_REQUIRE_PROMOTED_CATALOGS:
            readiness = _history_ready(conn, organization_id, promoted_catalogs)
            if not readiness.get("ready"):
                msg = readiness.get("message") or f"Catálogos faltantes: {readiness.get('missing_catalogs')}"
                for table_cfg in history_tables:
                    granularity = (
                        table_cfg.get("granularity")
                        or profile.get("default_granularity")
                        or "weekly"
                    )
                    _record_skip(
                        skipped_items,
                        skip_messages,
                        load_kind="history",
                        granularity=granularity,
                        reason=msg,
                    )
                _update_run(
                    conn,
                    run_id,
                    status="FAILED",
                    error_message=msg,
                    batch_ids=batch_ids,
                    metadata_patch=_execution_metadata_patch(enqueued_items, skipped_items),
                )
                if own_conn:
                    conn.close()
                return run_id

        for table_cfg in history_tables:
            hist_dir = source_history_dir(source_root)
            files = _list_source_files(hist_dir)
            if not files:
                msg = f"Historia omitida: no hay archivos en {hist_dir}"
                logger.warning(msg)
                granularity = (
                    table_cfg.get("granularity")
                    or profile.get("default_granularity")
                    or "weekly"
                )
                _record_skip(
                    skipped_items,
                    skip_messages,
                    load_kind="history",
                    granularity=granularity,
                    reason=msg,
                )
                continue

            granularity = table_cfg.get("granularity") or profile.get("default_granularity") or "weekly"
            source_file = files[0]
            storage_dir = ensure_incremental_storage_dir(
                organization_id,
                "history",
                organization_name=org_name,
                load_date=self.load_date,
            )

            db = Session()
            try:
                from data_staging.api.v1.upload import upload_service

                file_analysis = upload_service.analyze_file_structure(source_file)
                headers = file_analysis.get("columns", [])
                mappings, toggles, process_type, missing = build_incremental_mappings(
                    file_headers=headers,
                    load_type="history",
                    organization_id=organization_id,
                    granularity=granularity,
                )
                if missing:
                    msg = (
                        f"Historia no procesada: el archivo '{source_file.name}' "
                        f"no tiene las columnas requeridas ({', '.join(missing)})"
                    )
                    logger.warning(msg)
                    _record_skip(
                        skipped_items,
                        skip_messages,
                        load_kind="history",
                        granularity=granularity,
                        file_name=source_file.name,
                        reason=msg,
                    )
                    continue
                batch_id = create_incremental_batch(
                    db,
                    organization_id=organization_id,
                    source_file=source_file,
                    storage_dir=storage_dir,
                    load_type="history",
                    load_timestamp=load_ts,
                    target_schema=HISTORY_TARGET_SCHEMA,
                    target_table=HISTORY_TARGET_TABLE,
                    source_name=HISTORY_SOURCE_NAME,
                    process_type=process_type,
                    column_mappings=mappings,
                    column_toggles=toggles,
                    incremental_run_id=run_id,
                )
                db.commit()
                batch_ids.append(batch_id)
                _record_enqueued(
                    enqueued_items,
                    load_kind="history",
                    granularity=granularity,
                    file_name=source_file.name,
                    batch_id=batch_id,
                )
                _enqueue_incremental_load(batch_id, organization_id, run_id)
            finally:
                db.close()

        summary_patch = _execution_metadata_patch(enqueued_items, skipped_items)
        _update_run(conn, run_id, batch_ids=batch_ids, metadata_patch=summary_patch)
        if not batch_ids:
            error_message = (
                "; ".join(skip_messages)
                if skip_messages
                else "No se encontraron archivos para procesar"
            )
            _update_run(
                conn,
                run_id,
                status="FAILED",
                error_message=error_message,
                metadata_patch=summary_patch,
            )
        elif skip_messages:
            logger.warning(
                "Incremental run %s omitió cargas: %s",
                run_id,
                "; ".join(skip_messages),
            )
        if own_conn:
            conn.close()
        return run_id


def run_all_pending() -> List[str]:
    """Entry point for scheduler."""
    return IncrementalOrchestrator().run_all_enabled()


def run_single_organization(organization_id: str) -> Optional[str]:
    conn = _connect()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT p.*,
                       COALESCE(
                           (SELECT json_agg(t ORDER BY t.load_kind, t.catalog_slug)
                            FROM staging_meta.incremental_org_tables t
                            WHERE t.organization_id = p.organization_id AND t.enabled = true),
                           '[]'::json
                       ) AS tables
                FROM staging_meta.incremental_org_profiles p
                WHERE p.organization_id = %s
                """,
                (organization_id,),
            )
            profile = cur.fetchone()
        if not profile:
            raise ValueError(f"No incremental profile for organization {organization_id}")
        return IncrementalOrchestrator().run_organization(dict(profile), conn=conn)
    finally:
        conn.close()

"""Incremental load configuration and monitoring API."""

from __future__ import annotations

import io
import json
import logging
import zipfile
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from data_staging.auth.security import TokenUser, get_current_user, require_m8_connect_admin
from data_staging.database import get_db_session
from data_staging.schemas.incremental import (
    IncrementalOrgProfilePayload,
    IncrementalOrgTablePayload,
    IncrementalRunsDeletePayload,
    IncrementalSchedulePayload,
    IncrementalTriggerPayload,
)
from data_staging.services.connect_roles.constants import CONNECT_ROLE_ADMIN
from data_staging.services.connect_roles.service import has_permission
from data_staging.utils.batch_control import normalize_metadata
from data_staging.utils.batch_staging_files import find_rejected_records_file
from data_staging.utils.organization import fetch_organization_name

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/incremental", tags=["Incremental"])


def _scope_org_id(user: TokenUser) -> Optional[str]:
    if user.m8_connect_role == CONNECT_ROLE_ADMIN:
        return None
    return user.organization_id


def _require_incremental_read(user: TokenUser = Depends(get_current_user)) -> TokenUser:
    if user.m8_connect_role == CONNECT_ROLE_ADMIN:
        return user
    if has_permission(user.permissions, "menus.incremental"):
        return user
    if has_permission(user.permissions, "config.incremental_view"):
        return user
    raise HTTPException(status_code=403, detail="Permiso insuficiente: menus.incremental")


def _require_incremental_config_read(user: TokenUser = Depends(get_current_user)) -> TokenUser:
    if user.m8_connect_role == CONNECT_ROLE_ADMIN:
        return user
    if has_permission(user.permissions, "config.incremental_view"):
        return user
    raise HTTPException(status_code=403, detail="Permiso insuficiente: config.incremental_view")


@router.get("/schedule")
async def get_schedule(
    current_user: TokenUser = Depends(_require_incremental_config_read),
    db: Session = Depends(get_db_session),
):
    row = db.execute(text("SELECT * FROM staging_meta.incremental_schedule WHERE id = 1")).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Schedule not configured")
    return dict(row._mapping)


@router.put("/schedule")
async def update_schedule(
    payload: IncrementalSchedulePayload,
    current_user: TokenUser = Depends(require_m8_connect_admin),
    db: Session = Depends(get_db_session),
):
    db.execute(
        text("""
            UPDATE staging_meta.incremental_schedule
            SET enabled = :enabled,
                cron_expression = :cron_expression,
                timezone = :timezone,
                retention_years = :retention_years,
                updated_at = CURRENT_TIMESTAMP,
                updated_by = :updated_by
            WHERE id = 1
        """),
        {
            **payload.model_dump(),
            "updated_by": current_user.email,
        },
    )
    db.commit()
    return await get_schedule(current_user=current_user, db=db)


def _resolve_and_ensure_source_path(
    *,
    organization_id: str,
    organization_name: Optional[str],
    source_path: Optional[str],
) -> str:
    """Fill default source path if empty and create catalogos/historia folders."""
    try:
        from m8_incremental.paths import ensure_org_source_layout, suggest_org_source_path
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail="Servicio m8_incremental no instalado. pip install -e ../m8_incremental",
        ) from exc

    path = (source_path or "").strip()
    if not path:
        path = suggest_org_source_path(
            organization_id=organization_id,
            organization_name=organization_name,
        )
    try:
        ensured = ensure_org_source_layout(path)
    except Exception as exc:
        logger.exception("Could not create source layout for %s", organization_id)
        raise HTTPException(
            status_code=400,
            detail=f"No se pudo crear la ruta origen '{path}': {exc}",
        ) from exc
    return str(ensured)


@router.get("/organization-catalog")
async def list_organization_catalog(
    current_user: TokenUser = Depends(_require_incremental_config_read),
    db: Session = Depends(get_db_session),
):
    """Organizations from public.organizations (id + display name) for profile setup."""
    scope = _scope_org_id(current_user)
    if scope:
        rows = db.execute(
            text("""
                SELECT id::text AS id, name
                FROM public.organizations
                WHERE id = :oid
                ORDER BY name
            """),
            {"oid": scope},
        ).fetchall()
    else:
        rows = db.execute(
            text("""
                SELECT id::text AS id, name
                FROM public.organizations
                WHERE name IS NOT NULL AND TRIM(name) <> ''
                ORDER BY name
            """)
        ).fetchall()

    suggested_fn = None
    try:
        from m8_incremental.paths import suggest_org_source_path

        suggested_fn = suggest_org_source_path
    except ImportError:
        suggested_fn = None

    items = []
    for r in rows:
        item = {"id": r.id, "name": r.name}
        if suggested_fn:
            item["suggested_source_path"] = suggested_fn(
                organization_id=str(r.id),
                organization_name=r.name,
            )
        items.append(item)
    return items


@router.get("/organizations")
async def list_organizations(
    current_user: TokenUser = Depends(_require_incremental_config_read),
    db: Session = Depends(get_db_session),
):
    scope = _scope_org_id(current_user)
    if scope:
        rows = db.execute(
            text("SELECT * FROM staging_meta.incremental_org_profiles WHERE organization_id = :oid"),
            {"oid": scope},
        ).fetchall()
    else:
        rows = db.execute(
            text("SELECT * FROM staging_meta.incremental_org_profiles ORDER BY organization_name")
        ).fetchall()
    return [dict(r._mapping) for r in rows]


@router.post("/organizations")
async def create_organization(
    payload: IncrementalOrgProfilePayload,
    current_user: TokenUser = Depends(require_m8_connect_admin),
    db: Session = Depends(get_db_session),
):
    org_name = payload.organization_name or fetch_organization_name(db, payload.organization_id)
    source_path = _resolve_and_ensure_source_path(
        organization_id=payload.organization_id,
        organization_name=org_name,
        source_path=payload.source_path,
    )
    try:
        db.execute(
            text("""
                INSERT INTO staging_meta.incremental_org_profiles
                (organization_id, organization_name, enabled, source_path,
                 notification_emails, default_granularity)
                VALUES (:organization_id, :organization_name, :enabled, :source_path,
                        :notification_emails, :default_granularity)
            """),
            {
                "organization_id": payload.organization_id,
                "organization_name": org_name or payload.organization_id,
                "enabled": payload.enabled,
                "source_path": source_path,
                "notification_emails": payload.notification_emails,
                "default_granularity": payload.default_granularity,
            },
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Ya existe un perfil para esta organización. Selecciónala en la lista para editarla.",
        ) from None
    return {
        "status": "created",
        "organization_id": payload.organization_id,
        "source_path": source_path,
    }


@router.put("/organizations/{organization_id}")
async def update_organization(
    organization_id: str,
    payload: IncrementalOrgProfilePayload,
    current_user: TokenUser = Depends(require_m8_connect_admin),
    db: Session = Depends(get_db_session),
):
    org_name = payload.organization_name or fetch_organization_name(db, organization_id)
    source_path = _resolve_and_ensure_source_path(
        organization_id=organization_id,
        organization_name=org_name,
        source_path=payload.source_path,
    )
    result = db.execute(
        text("""
            UPDATE staging_meta.incremental_org_profiles
            SET organization_name = :organization_name,
                enabled = :enabled,
                source_path = :source_path,
                notification_emails = :notification_emails,
                default_granularity = :default_granularity,
                updated_at = CURRENT_TIMESTAMP
            WHERE organization_id = :organization_id
        """),
        {
            "organization_id": organization_id,
            "organization_name": org_name or organization_id,
            "enabled": payload.enabled,
            "source_path": source_path,
            "notification_emails": payload.notification_emails,
            "default_granularity": payload.default_granularity,
        },
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Organization profile not found")
    db.commit()
    return {"status": "updated", "source_path": source_path}


@router.delete("/organizations/{organization_id}")
async def delete_organization(
    organization_id: str,
    current_user: TokenUser = Depends(require_m8_connect_admin),
    db: Session = Depends(get_db_session),
):
    db.execute(
        text("DELETE FROM staging_meta.incremental_org_profiles WHERE organization_id = :oid"),
        {"oid": organization_id},
    )
    db.commit()
    return {"status": "deleted"}


@router.get("/organizations/{organization_id}/tables")
async def get_org_tables(
    organization_id: str,
    current_user: TokenUser = Depends(_require_incremental_config_read),
    db: Session = Depends(get_db_session),
):
    scope = _scope_org_id(current_user)
    if scope and scope != organization_id:
        raise HTTPException(status_code=403, detail="No autorizado para esta organización")
    rows = db.execute(
        text("""
            SELECT id, load_kind, catalog_slug, enabled, granularity
            FROM staging_meta.incremental_org_tables
            WHERE organization_id = :oid
            ORDER BY load_kind, catalog_slug
        """),
        {"oid": organization_id},
    ).fetchall()
    return [dict(r._mapping) for r in rows]


@router.put("/organizations/{organization_id}/tables")
async def update_org_tables(
    organization_id: str,
    tables: List[IncrementalOrgTablePayload],
    current_user: TokenUser = Depends(require_m8_connect_admin),
    db: Session = Depends(get_db_session),
):
    db.execute(
        text("DELETE FROM staging_meta.incremental_org_tables WHERE organization_id = :oid"),
        {"oid": organization_id},
    )
    for table in tables:
        db.execute(
            text("""
                INSERT INTO staging_meta.incremental_org_tables
                (organization_id, load_kind, catalog_slug, enabled, granularity)
                VALUES (:organization_id, :load_kind, :catalog_slug, :enabled, :granularity)
            """),
            {
                "organization_id": organization_id,
                "load_kind": table.load_kind,
                "catalog_slug": table.catalog_slug,
                "enabled": table.enabled,
                "granularity": table.granularity,
            },
        )
    db.commit()
    return await get_org_tables(organization_id, current_user=current_user, db=db)


@router.get("/runs")
async def list_runs(
    organization_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: TokenUser = Depends(_require_incremental_read),
    db: Session = Depends(get_db_session),
):
    scope = _scope_org_id(current_user)
    if scope:
        organization_id = scope
    clauses = ["1=1"]
    params: Dict[str, Any] = {"limit": limit, "offset": offset}
    if organization_id:
        clauses.append("r.organization_id = :organization_id")
        params["organization_id"] = organization_id
    if status:
        clauses.append("r.status = :status")
        params["status"] = status
    where = " AND ".join(clauses)
    rows = db.execute(
        text(f"""
            SELECT r.*, p.organization_name
            FROM staging_meta.incremental_runs r
            LEFT JOIN staging_meta.incremental_org_profiles p
              ON p.organization_id = r.organization_id
            WHERE {where}
            ORDER BY r.started_at DESC
            LIMIT :limit OFFSET :offset
        """),
        params,
    ).fetchall()
    total = db.execute(
        text(f"SELECT COUNT(*) FROM staging_meta.incremental_runs r WHERE {where}"),
        {k: v for k, v in params.items() if k not in ("limit", "offset")},
    ).scalar()
    return {
        "items": [dict(r._mapping) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/runs/{run_id}")
async def get_run(
    run_id: str,
    current_user: TokenUser = Depends(_require_incremental_read),
    db: Session = Depends(get_db_session),
):
    row = db.execute(
        text("""
            SELECT r.*, p.organization_name
            FROM staging_meta.incremental_runs r
            LEFT JOIN staging_meta.incremental_org_profiles p
              ON p.organization_id = r.organization_id
            WHERE r.run_id = :run_id
        """),
        {"run_id": run_id},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")
    data = dict(row._mapping)
    scope = _scope_org_id(current_user)
    if scope and str(data.get("organization_id")) != scope:
        raise HTTPException(status_code=403, detail="No autorizado")
    batch_ids = [str(bid) for bid in (data.get("batch_ids") or [])]
    batches = []
    if batch_ids:
        batch_rows = db.execute(
            text("""
                SELECT batch_id, status, metadata, error_message, created_at, completed_at,
                       file_name, source_name
                FROM staging_meta.batch_control
                WHERE batch_id::text = ANY(:ids)
            """),
            {"ids": batch_ids},
        ).fetchall()
        for br in batch_rows:
            meta = normalize_metadata(br.metadata)
            try:
                from m8_incremental.services.run_helpers import batch_source_row_stats

                row_stats = batch_source_row_stats(meta)
            except ImportError:
                process = meta.get("processing_stats") or {}
                row_stats = {
                    "source_rows": int(process.get("total_rows") or process.get("total_inserted") or 0)
                    + int(process.get("total_rejected") or 0),
                    "rejected_rows": int(process.get("total_rejected") or 0),
                    "valid_rows": int(process.get("total_inserted") or 0),
                }
            rejected_path = find_rejected_records_file(
                str(br.batch_id),
                meta.get("rejected_temp_file"),
                meta,
            )
            batches.append(
                {
                    "batch_id": str(br.batch_id),
                    "status": br.status,
                    "load_type": meta.get("load_type"),
                    "catalog_name": meta.get("catalog_name"),
                    "target_table": meta.get("target_table") or meta.get("production_table"),
                    "file_name": br.file_name,
                    "source_name": br.source_name,
                    "promoted_inserted": meta.get("promoted_inserted", 0),
                    "promoted_updated": meta.get("promoted_updated", 0),
                    "source_rows": row_stats["source_rows"],
                    "valid_rows": row_stats["valid_rows"],
                    "total_rejected": row_stats["rejected_rows"],
                    "has_rejected_file": bool(rejected_path),
                    "error_message": br.error_message,
                    "created_at": br.created_at,
                    "completed_at": br.completed_at,
                }
            )
    data["batches"] = batches

    # Recompute run totals from batch metadata so older runs also show preview rejections.
    recomputed_processed = sum(int(b.get("source_rows") or 0) for b in batches)
    recomputed_rejected = sum(int(b.get("total_rejected") or 0) for b in batches)
    if recomputed_processed > int(data.get("total_processed") or 0):
        data["total_processed"] = recomputed_processed
    if recomputed_rejected > int(data.get("total_rejected") or 0):
        data["total_rejected"] = recomputed_rejected
    data["has_rejected_files"] = any(b.get("has_rejected_file") for b in batches)

    run_meta = normalize_metadata(data.get("metadata"))
    summary = run_meta.get("execution_summary") or {}
    enqueued = list(summary.get("enqueued") or [])
    skipped = list(summary.get("skipped") or [])

    if not enqueued and batches:
        for batch in batches:
            enqueued.append(
                {
                    "load_kind": batch.get("load_type"),
                    "catalog_slug": batch.get("catalog_name"),
                    "file_name": batch.get("file_name"),
                    "batch_id": batch.get("batch_id"),
                }
            )

    batch_by_id = {b["batch_id"]: b for b in batches}
    for item in enqueued:
        batch = batch_by_id.get(item.get("batch_id"))
        if batch:
            item["status"] = batch.get("status")
            item["promoted_inserted"] = batch.get("promoted_inserted", 0)
            item["promoted_updated"] = batch.get("promoted_updated", 0)
            item["source_rows"] = batch.get("source_rows", 0)
            item["total_rejected"] = batch.get("total_rejected", 0)
            item["has_rejected_file"] = batch.get("has_rejected_file", False)
            item["error_message"] = batch.get("error_message")

    data["execution_summary"] = {"enqueued": enqueued, "skipped": skipped}
    return data


@router.post("/runs/trigger")
async def trigger_run(
    payload: IncrementalTriggerPayload,
    current_user: TokenUser = Depends(require_m8_connect_admin),
):
    try:
        from m8_incremental.services.orchestrator import (
            run_all_pending,
            run_single_organization,
        )

        if payload.organization_id:
            run_id = run_single_organization(payload.organization_id)
            return {"run_ids": [run_id] if run_id else []}
        run_ids = run_all_pending()
        return {"run_ids": run_ids}
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail="Servicio m8_incremental no instalado. pip install -e ../m8_incremental",
        ) from exc
    except Exception as exc:
        logger.exception("Trigger incremental run failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/runs/delete")
async def delete_runs(
    payload: IncrementalRunsDeletePayload,
    current_user: TokenUser = Depends(require_m8_connect_admin),
    db: Session = Depends(get_db_session),
):
    """Purge selected incremental runs (batches, files, history keys, run row)."""
    try:
        from m8_incremental.services.retention import purge_run
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail="Servicio m8_incremental no instalado. pip install -e ../m8_incremental",
        ) from exc

    scope = _scope_org_id(current_user)
    deleted: List[Dict[str, Any]] = []
    skipped: List[Dict[str, str]] = []

    for run_id in payload.run_ids:
        row = db.execute(
            text(
                "SELECT run_id, organization_id, status FROM staging_meta.incremental_runs "
                "WHERE run_id = :rid"
            ),
            {"rid": run_id},
        ).fetchone()
        if not row:
            skipped.append({"run_id": run_id, "reason": "not_found"})
            continue
        if scope and str(row.organization_id) != scope:
            skipped.append({"run_id": run_id, "reason": "forbidden"})
            continue
        try:
            stats = purge_run(str(row.run_id))
            deleted.append(
                {
                    "run_id": str(row.run_id),
                    "files_deleted": stats.get("files_deleted", 0),
                    "rows_deleted": stats.get("rows_deleted", 0),
                }
            )
        except Exception as exc:
            logger.exception("Failed to purge incremental run %s", run_id)
            skipped.append({"run_id": run_id, "reason": str(exc)})

    if not deleted and skipped:
        raise HTTPException(
            status_code=400,
            detail={"message": "No se eliminó ninguna ejecución", "skipped": skipped},
        )

    return {"deleted": deleted, "skipped": skipped, "deleted_count": len(deleted)}


@router.get("/runs/{run_id}/rejected/download")
async def download_run_rejected(
    run_id: str,
    current_user: TokenUser = Depends(_require_incremental_read),
    db: Session = Depends(get_db_session),
):
    row = db.execute(
        text("SELECT organization_id, batch_ids FROM staging_meta.incremental_runs WHERE run_id = :rid"),
        {"rid": run_id},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")
    scope = _scope_org_id(current_user)
    if scope and str(row.organization_id) != scope:
        raise HTTPException(status_code=403, detail="No autorizado")

    batch_ids = [str(bid) for bid in (row.batch_ids or [])]
    buf = io.BytesIO()
    written = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for bid in batch_ids:
            meta_row = db.execute(
                text("SELECT metadata FROM staging_meta.batch_control WHERE batch_id = :bid"),
                {"bid": bid},
            ).fetchone()
            if not meta_row:
                continue
            meta = normalize_metadata(meta_row.metadata)
            path = find_rejected_records_file(
                bid,
                meta.get("rejected_temp_file"),
                meta,
            )
            if path and path.is_file() and path.stat().st_size > 0:
                zf.write(path, arcname=path.name)
                written += 1
    if written == 0:
        raise HTTPException(
            status_code=404,
            detail=(
                "No se encontraron archivos de rechazados para esta ejecución. "
                "Si la carga fue reciente, verifica que el preview haya generado el TSV."
            ),
        )
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="rejected_{run_id}.zip"'},
    )

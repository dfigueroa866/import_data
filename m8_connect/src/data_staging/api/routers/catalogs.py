"""Admin API for catalog definitions (CRUD)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from data_staging.auth.security import (
    TokenUser,
    get_current_user,
    require_m8_connect_admin,
)
from data_staging.services.catalog import catalog_store
from data_staging.database import get_db_session
from data_staging.schemas.catalogs import CatalogDefinitionPayload
from data_staging.services.connect_roles.constants import CONNECT_ROLE_ADMIN
from data_staging.services.connect_roles.service import has_permission
from data_staging.utils.pg_schema import fetch_table_columns

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/catalogs", tags=["Catalogs"])


def _require_catalogs_read(current_user: TokenUser = Depends(get_current_user)) -> TokenUser:
    if current_user.m8_connect_role == CONNECT_ROLE_ADMIN:
        return current_user
    if has_permission(current_user.permissions, "config.catalogs_view"):
        return current_user
    raise HTTPException(status_code=403, detail="Permiso insuficiente: config.catalogs_view")


@router.get("/admin")
async def list_catalog_definitions_admin(
    current_user: TokenUser = Depends(_require_catalogs_read),
):
    """List all catalog definitions (including inactive) for admin UI."""
    return {"catalogs": catalog_store.list_all_catalogs(active_only=False)}


@router.get("/admin/schema-columns")
async def list_target_table_columns(
    schema: str = Query(...),
    table: str = Query(...),
    db: Session = Depends(get_db_session),
    current_user: TokenUser = Depends(_require_catalogs_read),
):
    """Columns from information_schema to help configure a catalog."""
    columns = fetch_table_columns(db, schema, table)

    if not columns:
        raise HTTPException(status_code=404, detail=f"Tabla {schema}.{table} no encontrada")

    return {"schema": schema, "table": table, "columns": columns}


@router.get("/admin/{name}")
async def get_catalog_definition_admin(
    name: str,
    current_user: TokenUser = Depends(_require_catalogs_read),
):
    entry = catalog_store.get_catalog_by_name(name)
    if not entry:
        raise HTTPException(status_code=404, detail="Catálogo no encontrado")
    return entry


@router.post("/admin", status_code=201)
async def create_catalog_definition(
    payload: CatalogDefinitionPayload,
    current_user: TokenUser = Depends(require_m8_connect_admin),
):
    try:
        entry = catalog_store.create_catalog(payload.model_dump())
        logger.info("Catalog created: %s by %s", entry["name"], current_user.email)
        return entry
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.put("/admin/{name}")
async def update_catalog_definition(
    name: str,
    payload: CatalogDefinitionPayload,
    current_user: TokenUser = Depends(require_m8_connect_admin),
):
    try:
        entry = catalog_store.update_catalog(name, payload.model_dump())
        logger.info("Catalog updated: %s by %s", entry["name"], current_user.email)
        return entry
    except ValueError as e:
        raise HTTPException(status_code=404 if "no encontrado" in str(e).lower() else 400, detail=str(e)) from e


@router.delete("/admin/{name}")
async def delete_catalog_definition(
    name: str,
    hard: bool = Query(False),
    current_user: TokenUser = Depends(require_m8_connect_admin),
):
    try:
        catalog_store.delete_catalog(name, hard=hard)
        return {"status": "ok", "name": name, "hard": hard}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

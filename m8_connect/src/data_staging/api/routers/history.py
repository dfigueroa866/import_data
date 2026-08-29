"""Admin API for history table definitions (sales_history, inventory_snapshot, …)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from data_staging.auth.security import (
    TokenUser,
    get_current_user,
    require_m8_connect_admin,
)
from data_staging.schemas.history import HistoryDefinitionPayload
from data_staging.services.history import history_store
from data_staging.services.connect_roles.constants import CONNECT_ROLE_ADMIN
from data_staging.services.connect_roles.service import has_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/history", tags=["History"])


def _require_history_read(current_user: TokenUser = Depends(get_current_user)) -> TokenUser:
    if current_user.m8_connect_role == CONNECT_ROLE_ADMIN:
        return current_user
    if has_permission(current_user.permissions, "config.history_view"):
        return current_user
    raise HTTPException(status_code=403, detail="Permiso insuficiente: config.history_view")


@router.get("/admin")
async def list_history_definitions_admin(
    current_user: TokenUser = Depends(_require_history_read),
):
    """List all history table definitions for admin UI."""
    return {"tables": history_store.list_all_tables(active_only=False)}


@router.get("/admin/{name}")
async def get_history_definition_admin(
    name: str,
    current_user: TokenUser = Depends(_require_history_read),
):
    """Full history definition for one table."""
    entry = history_store.get_table_by_name(name)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Tabla de historia no encontrada: {name}")
    return entry


@router.put("/admin/{name}")
async def update_history_definition_admin(
    name: str,
    payload: HistoryDefinitionPayload,
    current_user: TokenUser = Depends(require_m8_connect_admin),
):
    try:
        entry = history_store.update_definition(
            {**payload.model_dump(), "name": name},
            table_name=name,
        )
        logger.info("History definition %s updated by %s", name, current_user.email)
        return entry
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

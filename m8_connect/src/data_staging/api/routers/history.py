"""Admin API for history definition (sales_history mapping config)."""

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
async def get_history_definition_admin(
    current_user: TokenUser = Depends(_require_history_read),
):
    """Full history definition for admin UI."""
    return history_store.get_definition()


@router.put("/admin")
async def update_history_definition_admin(
    payload: HistoryDefinitionPayload,
    current_user: TokenUser = Depends(require_m8_connect_admin),
):
    try:
        entry = history_store.update_definition(payload.model_dump())
        logger.info("History definition updated by %s", current_user.email)
        return entry
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

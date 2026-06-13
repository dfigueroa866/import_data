"""Admin API for history definition (sales_history mapping config)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from data_staging.auth.security import TokenUser, get_current_user
from data_staging.schemas.history import HistoryDefinitionPayload
from data_staging.services.history import history_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/history", tags=["History"])


@router.get("/admin")
async def get_history_definition_admin(
    current_user: TokenUser = Depends(get_current_user),
):
    """Full history definition for admin UI."""
    return history_store.get_definition()


@router.put("/admin")
async def update_history_definition_admin(
    payload: HistoryDefinitionPayload,
    current_user: TokenUser = Depends(get_current_user),
):
    try:
        entry = history_store.update_definition(payload.model_dump())
        logger.info("History definition updated by %s", current_user.email)
        return entry
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

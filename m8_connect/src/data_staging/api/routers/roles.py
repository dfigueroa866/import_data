"""M8 Connect roles administration API."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from data_staging.auth.security import get_current_user, require_m8_connect_admin
from data_staging.database import get_db_session
from data_staging.schemas.auth import TokenUser
from data_staging.schemas.roles import (
    AssignRoleRequest,
    AssignRoleResponse,
    ConnectProfileResponse,
    LoaderProfileResponse,
    LoaderProfileUpdateRequest,
    UserConnectRoleItem,
    UsersWithRolesResponse,
)
from data_staging.services.connect_roles.constants import VALID_CONNECT_ROLES
from data_staging.services.connect_roles.service import (
    assign_role,
    clear_role,
    get_effective_permissions,
    get_loader_profile,
    list_users_with_roles,
    resolve_connect_role,
    update_loader_profile,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/roles", tags=["Roles"])


@router.get("/me", response_model=ConnectProfileResponse)
async def get_my_connect_profile(
    current_user: TokenUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    role = resolve_connect_role(db, current_user.id)
    permissions = get_effective_permissions(db, role)
    return ConnectProfileResponse(m8_connect_role=role, permissions=permissions)


@router.get("/users", response_model=UsersWithRolesResponse)
async def list_connect_users(
    search: str | None = Query(None),
    current_user: TokenUser = Depends(require_m8_connect_admin),
    db: Session = Depends(get_db_session),
):
    users = list_users_with_roles(db, search=search)
    return UsersWithRolesResponse(users=[UserConnectRoleItem(**u) for u in users])


@router.put("/users/{user_id}", response_model=AssignRoleResponse)
async def set_user_connect_role(
    user_id: str,
    body: AssignRoleRequest,
    current_user: TokenUser = Depends(require_m8_connect_admin),
    db: Session = Depends(get_db_session),
):
    if body.role not in VALID_CONNECT_ROLES:
        raise HTTPException(status_code=400, detail="Rol M8 Connect inválido")
    try:
        result = assign_role(db, user_id, body.role, granted_by=current_user.id)
        return AssignRoleResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/users/{user_id}", response_model=AssignRoleResponse)
async def remove_user_connect_role(
    user_id: str,
    current_user: TokenUser = Depends(require_m8_connect_admin),
    db: Session = Depends(get_db_session),
):
    result = clear_role(db, user_id)
    logger.info("Connect role cleared for %s by %s", user_id, current_user.email)
    return AssignRoleResponse(**result, is_default_loader=True)


@router.get("/loader-profile", response_model=LoaderProfileResponse)
async def get_loader_profile_admin(
    current_user: TokenUser = Depends(require_m8_connect_admin),
    db: Session = Depends(get_db_session),
):
    return LoaderProfileResponse(permissions=get_loader_profile(db))


@router.put("/loader-profile", response_model=LoaderProfileResponse)
async def update_loader_profile_admin(
    body: LoaderProfileUpdateRequest,
    current_user: TokenUser = Depends(require_m8_connect_admin),
    db: Session = Depends(get_db_session),
):
    permissions = update_loader_profile(
        db,
        body.permissions,
        updated_by=current_user.id,
    )
    logger.info("Loader profile updated by %s", current_user.email)
    return LoaderProfileResponse(permissions=permissions)

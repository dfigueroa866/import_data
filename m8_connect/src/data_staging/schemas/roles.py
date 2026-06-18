"""Schemas for M8 Connect roles API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ConnectPermissions(BaseModel):
    menus: Dict[str, bool] = Field(default_factory=dict)
    upload: Dict[str, bool] = Field(default_factory=dict)
    config: Dict[str, bool] = Field(default_factory=dict)


class UserConnectRoleItem(BaseModel):
    id: str
    email: str
    platform_role: str
    organization_id: str
    organization_name: Optional[str] = None
    m8_connect_role: str
    explicit_role: Optional[str] = None
    is_default_loader: bool = False
    granted_at: Optional[str] = None


class UsersWithRolesResponse(BaseModel):
    users: List[UserConnectRoleItem]


class AssignRoleRequest(BaseModel):
    role: str


class AssignRoleResponse(BaseModel):
    user_id: str
    m8_connect_role: str
    is_default_loader: bool = False


class LoaderProfileResponse(BaseModel):
    permissions: Dict[str, Any]


class LoaderProfileUpdateRequest(BaseModel):
    permissions: Dict[str, Any]


class ConnectProfileResponse(BaseModel):
    m8_connect_role: str
    permissions: Dict[str, Any]

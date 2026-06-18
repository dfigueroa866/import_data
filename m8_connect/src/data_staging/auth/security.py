"""Password verification and JWT token helpers."""

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional

import bcrypt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from data_staging.config import settings
from data_staging.schemas.auth import TokenUser
from data_staging.services.connect_roles.constants import CONNECT_ROLE_ADMIN
from data_staging.services.connect_roles.service import has_permission

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> TokenUser:
    """Decode JWT and return the authenticated user."""
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=401, detail="No autenticado")

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")

    if payload.get("typ") == "refresh":
        raise HTTPException(status_code=401, detail="Token inválido o expirado")

    user_id = payload.get("sub")
    organization_id = payload.get("organization_id")
    if not user_id or not organization_id:
        raise HTTPException(status_code=401, detail="Token incompleto")

    permissions = payload.get("permissions") or {}
    if not isinstance(permissions, dict):
        permissions = {}

    return TokenUser(
        id=str(user_id),
        email=str(payload.get("email") or ""),
        role=str(payload.get("role") or ""),
        organization_id=str(organization_id),
        m8_connect_role=str(payload.get("m8_connect_role") or "loader"),
        permissions=permissions,
    )


def require_m8_connect_admin(
    current_user: TokenUser = Depends(get_current_user),
) -> TokenUser:
    if current_user.m8_connect_role != CONNECT_ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="Se requiere rol admin_m8_connect")
    return current_user


def require_permission(permission_key: str) -> Callable:
    def _dependency(current_user: TokenUser = Depends(get_current_user)) -> TokenUser:
        if current_user.m8_connect_role == CONNECT_ROLE_ADMIN:
            return current_user
        if not has_permission(current_user.permissions, permission_key):
            raise HTTPException(
                status_code=403,
                detail=f"Permiso insuficiente: {permission_key}",
            )
        return current_user

    return _dependency


ORG_MAPPING_KEY = "__fixed_organization_id__"


def ensure_organization_id_mapping(
    column_mappings: dict,
    column_toggles: dict,
    organization_id: str,
) -> tuple[dict, dict]:
    """Force organization_id from the logged-in user; strip file-based org mappings."""
    mappings = dict(column_mappings or {})
    toggles = dict(column_toggles or {})

    for file_col, cfg in list(mappings.items()):
        if file_col == ORG_MAPPING_KEY:
            continue
        if cfg.get("target") == "organization_id":
            mappings.pop(file_col, None)
            toggles[file_col] = False

    mappings[ORG_MAPPING_KEY] = {
        "target": "organization_id",
        "auto_mapped": False,
        "is_fixed": True,
        "from_organization_id": True,
    }
    toggles[ORG_MAPPING_KEY] = True
    return mappings, toggles


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a bcrypt hash."""
    if not plain_password or not hashed_password:
        return False
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False


def create_access_token(
    user_id: str,
    email: str,
    role: str,
    organization_id: str,
    m8_connect_role: str = "loader",
    permissions: Optional[Dict[str, Any]] = None,
    expires_minutes: int | None = None,
) -> str:
    """Create a signed JWT access token."""
    expire_delta = timedelta(
        minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    expire = datetime.now(timezone.utc) + expire_delta
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "organization_id": organization_id,
        "m8_connect_role": m8_connect_role,
        "permissions": permissions or {},
        "typ": "access",
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(
    user_id: str,
    email: str,
    role: str,
    organization_id: str,
    m8_connect_role: str = "loader",
    permissions: Optional[Dict[str, Any]] = None,
    expires_days: int | None = None,
) -> str:
    """Create a signed JWT refresh token."""
    expire_delta = timedelta(
        days=expires_days or settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    expire = datetime.now(timezone.utc) + expire_delta
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "organization_id": organization_id,
        "m8_connect_role": m8_connect_role,
        "permissions": permissions or {},
        "typ": "refresh",
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_refresh_token(token: str) -> dict:
    """Validate refresh token and return its payload."""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Sesión expirada, inicia sesión de nuevo") from exc

    if payload.get("typ") != "refresh":
        raise HTTPException(status_code=401, detail="Token de refresco inválido")

    user_id = payload.get("sub")
    organization_id = payload.get("organization_id")
    if not user_id or not organization_id:
        raise HTTPException(status_code=401, detail="Token incompleto")

    return payload


def resolve_user_connect_context(db: Session, user_id: str) -> tuple[str, Dict[str, Any]]:
    from data_staging.services.connect_roles.service import (
        get_effective_permissions,
        resolve_connect_role,
    )

    connect_role = resolve_connect_role(db, user_id)
    permissions = get_effective_permissions(db, connect_role)
    return connect_role, permissions

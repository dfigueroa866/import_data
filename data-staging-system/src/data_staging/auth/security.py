"""Password verification and JWT token helpers."""

from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt, JWTError
from pydantic import BaseModel

from data_staging.config import settings

_bearer = HTTPBearer(auto_error=False)


class TokenUser(BaseModel):
    id: str
    email: str
    role: str
    organization_id: str


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

    return TokenUser(
        id=str(user_id),
        email=str(payload.get("email") or ""),
        role=str(payload.get("role") or ""),
        organization_id=str(organization_id),
    )


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
        "default_value": organization_id,
        "auto_mapped": False,
        "is_fixed": True,
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
        "typ": "access",
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(
    user_id: str,
    email: str,
    role: str,
    organization_id: str,
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

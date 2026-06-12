"""Authentication endpoints for M8 Connect."""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from data_staging.auth.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    get_current_user,
    verify_password,
)
from data_staging.schemas.auth import (
    TokenUser,
    LoginRequest,
    UserResponse,
    LoginResponse,
    RefreshRequest,
    RefreshResponse,
)
from data_staging.config import settings
from data_staging.database import get_db_session

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
    responses={404: {"description": "Not found"}},
)

logger = logging.getLogger(__name__)





def _fetch_organization_name(db: Session, organization_id: str) -> Optional[str]:
    if not organization_id:
        return None
    try:
        row = db.execute(
            text("""
                SELECT name
                FROM public.organizations
                WHERE id = :organization_id
                LIMIT 1
            """),
            {"organization_id": organization_id},
        ).fetchone()
        return str(row.name) if row and row.name else None
    except Exception as e:
        logger.warning(f"Could not load organization name for {organization_id}: {e}")
        return None


def _build_user_response(db: Session, user_row) -> UserResponse:
    email = str(user_row.email)
    organization_id = str(user_row.organization_id)
    return UserResponse(
        id=str(user_row.id),
        email=email,
        display_name=email.split("@")[0],
        role=str(user_row.role),
        organization_id=organization_id,
        organization_name=_fetch_organization_name(db, organization_id),
    )


@router.post("/login", response_model=LoginResponse)
async def login(credentials: LoginRequest, db: Session = Depends(get_db_session)):
    """Authenticate user against public.users with bcrypt password verification."""
    try:
        result = db.execute(
            text("""
                SELECT id, email, role, organization_id, password_hash, locked_until
                FROM public.users
                WHERE LOWER(email::text) = LOWER(:email)
                  AND password_hash IS NOT NULL
                LIMIT 1
            """),
            {"email": credentials.email.strip()},
        ).fetchone()
    except Exception as e:
        logger.error(f"Login query failed: {e}")
        raise HTTPException(status_code=500, detail="Error al validar credenciales")

    if not result:
        raise HTTPException(
            status_code=401,
            detail="Correo o contraseña incorrectos",
        )

    if result.locked_until:
        locked_until = result.locked_until
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if locked_until > datetime.now(timezone.utc):
            raise HTTPException(
                status_code=403,
                detail="Cuenta bloqueada temporalmente. Inténtalo más tarde.",
            )

    if not verify_password(credentials.password, result.password_hash):
        raise HTTPException(
            status_code=401,
            detail="Correo o contraseña incorrectos",
        )

    access_token = create_access_token(
        user_id=str(result.id),
        email=str(result.email),
        role=str(result.role),
        organization_id=str(result.organization_id),
    )
    refresh_token = create_refresh_token(
        user_id=str(result.id),
        email=str(result.email),
        role=str(result.role),
        organization_id=str(result.organization_id),
    )

    email = str(result.email)
    logger.info(f"User logged in: {email}")

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=_build_user_response(db, result),
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_session(
    body: RefreshRequest,
    db: Session = Depends(get_db_session),
):
    """Issue a new access token from a valid refresh token."""
    payload = decode_refresh_token(body.refresh_token)
    user_id = str(payload["sub"])

    result = db.execute(
        text("""
            SELECT id, email, role, organization_id, locked_until
            FROM public.users
            WHERE id = :user_id
            LIMIT 1
        """),
        {"user_id": user_id},
    ).fetchone()

    if not result:
        raise HTTPException(status_code=401, detail="Sesión expirada, inicia sesión de nuevo")

    if result.locked_until:
        locked_until = result.locked_until
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if locked_until > datetime.now(timezone.utc):
            raise HTTPException(
                status_code=403,
                detail="Cuenta bloqueada temporalmente. Inténtalo más tarde.",
            )

    access_token = create_access_token(
        user_id=str(result.id),
        email=str(result.email),
        role=str(result.role),
        organization_id=str(result.organization_id),
    )

    return RefreshResponse(
        access_token=access_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: TokenUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """Return current user profile including organization display name."""
    result = db.execute(
        text("""
            SELECT id, email, role, organization_id
            FROM public.users
            WHERE id = :user_id
            LIMIT 1
        """),
        {"user_id": current_user.id},
    ).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    return _build_user_response(db, result)

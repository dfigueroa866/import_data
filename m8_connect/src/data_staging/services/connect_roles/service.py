"""Resolve and manage M8 Connect roles and loader profile."""

from __future__ import annotations

import json
import logging
from copy import deepcopy
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from data_staging.services.connect_roles.constants import (
    ADMIN_PERMISSIONS,
    CONNECT_ROLE_ADMIN,
    CONNECT_ROLE_LOADER,
    DEFAULT_LOADER_PERMISSIONS,
    VALID_CONNECT_ROLES,
    deep_copy_permissions,
)

logger = logging.getLogger(__name__)


def _merge_permissions(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(base)
    for section, values in override.items():
        if isinstance(values, dict) and isinstance(merged.get(section), dict):
            merged[section].update(values)
        else:
            merged[section] = values
    return merged


def resolve_connect_role(db: Session, user_id: str) -> str:
    row = db.execute(
        text("""
            SELECT role::text AS role
            FROM m8_schema.connect_user_roles
            WHERE user_id = :user_id
            LIMIT 1
        """),
        {"user_id": user_id},
    ).fetchone()
    if row and row.role in VALID_CONNECT_ROLES:
        return str(row.role)
    return CONNECT_ROLE_LOADER


def get_loader_profile(db: Session) -> Dict[str, Any]:
    row = db.execute(
        text("""
            SELECT permissions
            FROM m8_schema.loader_profile
            WHERE id = 1
            LIMIT 1
        """)
    ).fetchone()
    if not row or not row.permissions:
        return deep_copy_permissions(DEFAULT_LOADER_PERMISSIONS)
    perms = row.permissions
    if isinstance(perms, str):
        perms = json.loads(perms)
    return _merge_permissions(DEFAULT_LOADER_PERMISSIONS, perms)


def get_effective_permissions(db: Session, role: str) -> Dict[str, Any]:
    if role == CONNECT_ROLE_ADMIN:
        return deep_copy_permissions(ADMIN_PERMISSIONS)
    return get_loader_profile(db)


def has_permission(permissions: Dict[str, Any], key: str) -> bool:
    """Check dotted permission key, e.g. menus.upload or config.catalogs_view."""
    if not key:
        return False
    parts = key.split(".")
    node: Any = permissions
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return bool(node)


def list_users_with_roles(
    db: Session,
    search: Optional[str] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {"limit": limit}
    search_clause = ""
    if search:
        params["search"] = f"%{search.strip().lower()}%"
        search_clause = "AND LOWER(u.email::text) LIKE :search"

    rows = db.execute(
        text(f"""
            SELECT
                u.id,
                u.email,
                u.role::text AS platform_role,
                u.organization_id,
                o.name AS organization_name,
                cur.role::text AS m8_connect_role,
                cur.granted_at,
                CASE WHEN cur.user_id IS NULL THEN true ELSE false END AS is_default_loader
            FROM public.users u
            LEFT JOIN public.organizations o ON o.id = u.organization_id
            LEFT JOIN m8_schema.connect_user_roles cur ON cur.user_id = u.id
            WHERE u.password_hash IS NOT NULL
              {search_clause}
            ORDER BY u.email
            LIMIT :limit
        """),
        params,
    ).fetchall()

    result = []
    for row in rows:
        explicit_role = row.m8_connect_role
        effective_role = explicit_role or CONNECT_ROLE_LOADER
        result.append(
            {
                "id": str(row.id),
                "email": str(row.email),
                "platform_role": str(row.platform_role),
                "organization_id": str(row.organization_id),
                "organization_name": row.organization_name,
                "m8_connect_role": effective_role,
                "explicit_role": explicit_role,
                "is_default_loader": bool(row.is_default_loader),
                "granted_at": row.granted_at.isoformat() if row.granted_at else None,
            }
        )
    return result


def assign_role(
    db: Session,
    user_id: str,
    role: str,
    granted_by: Optional[str] = None,
) -> Dict[str, Any]:
    if role not in VALID_CONNECT_ROLES:
        raise ValueError(f"Rol inválido: {role}")

    exists = db.execute(
        text("SELECT id FROM public.users WHERE id = :user_id LIMIT 1"),
        {"user_id": user_id},
    ).fetchone()
    if not exists:
        raise ValueError("Usuario no encontrado")

    db.execute(
        text("""
            INSERT INTO m8_schema.connect_user_roles (user_id, role, granted_at, granted_by)
            VALUES (:user_id, CAST(:role AS m8_schema.connect_role), now(), :granted_by)
            ON CONFLICT (user_id) DO UPDATE
            SET role = EXCLUDED.role,
                granted_at = now(),
                granted_by = EXCLUDED.granted_by
        """),
        {"user_id": user_id, "role": role, "granted_by": granted_by},
    )
    db.commit()
    return {"user_id": user_id, "m8_connect_role": role}


def clear_role(db: Session, user_id: str) -> Dict[str, Any]:
    db.execute(
        text("DELETE FROM m8_schema.connect_user_roles WHERE user_id = :user_id"),
        {"user_id": user_id},
    )
    db.commit()
    return {"user_id": user_id, "m8_connect_role": CONNECT_ROLE_LOADER, "is_default_loader": True}


def update_loader_profile(
    db: Session,
    permissions: Dict[str, Any],
    updated_by: Optional[str] = None,
) -> Dict[str, Any]:
    merged = _merge_permissions(DEFAULT_LOADER_PERMISSIONS, permissions)
    db.execute(
        text("""
            INSERT INTO m8_schema.loader_profile (id, permissions, updated_at, updated_by)
            VALUES (1, CAST(:permissions AS jsonb), now(), :updated_by)
            ON CONFLICT (id) DO UPDATE
            SET permissions = EXCLUDED.permissions,
                updated_at = now(),
                updated_by = EXCLUDED.updated_by
        """),
        {
            "permissions": json.dumps(merged),
            "updated_by": updated_by,
        },
    )
    db.commit()
    return merged

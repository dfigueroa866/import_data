"""Bootstrap admin user for M8 Connect installs.

Revision ID: 005_bootstrap_admin_user
Revises: 004_incremental_tables
Create Date: 2026-07-31

Creates (or updates) david.figueroa@m8solutions.com.mx with password Admin123,
ensures organization "M8 Solutions" exists, and assigns admin_m8_connect.

This is an install bootstrap credential. Change the password after first login
in shared or production environments.
"""

from __future__ import annotations

import bcrypt
from alembic import op
from sqlalchemy import text

revision = "005_bootstrap_admin_user"
down_revision = "004_incremental_tables"
branch_labels = None
depends_on = None

BOOTSTRAP_ADMIN_EMAIL = "david.figueroa@m8solutions.com.mx"
BOOTSTRAP_ADMIN_PASSWORD = "Admin123"
BOOTSTRAP_ORG_NAME = "M8 Solutions"


def _table_exists(conn, schema: str, table: str) -> bool:
    return bool(
        conn.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = :schema
                      AND table_name = :table
                )
                """
            ),
            {"schema": schema, "table": table},
        ).scalar()
    )


def upgrade() -> None:
    conn = op.get_bind()
    if not (
        _table_exists(conn, "public", "organizations")
        and _table_exists(conn, "public", "users")
    ):
        return

    password_hash = bcrypt.hashpw(
        BOOTSTRAP_ADMIN_PASSWORD.encode("utf-8"),
        bcrypt.gensalt(rounds=12),
    ).decode("ascii")

    org_id = conn.execute(
        text(
            """
            SELECT id
            FROM public.organizations
            WHERE LOWER(name) = LOWER(:org_name)
            ORDER BY created_at
            LIMIT 1
            """
        ),
        {"org_name": BOOTSTRAP_ORG_NAME},
    ).scalar()

    if org_id is None:
        org_id = conn.execute(
            text(
                """
                INSERT INTO public.organizations (name)
                VALUES (:org_name)
                RETURNING id
                """
            ),
            {"org_name": BOOTSTRAP_ORG_NAME},
        ).scalar()

    conn.execute(
        text(
            """
            INSERT INTO public.users (
                organization_id,
                email,
                password_hash,
                role,
                failed_login_count,
                locked_until
            )
            VALUES (
                :organization_id,
                :email,
                :password_hash,
                CAST(:role AS user_role),
                0,
                NULL
            )
            ON CONFLICT (email) DO UPDATE
            SET password_hash = EXCLUDED.password_hash,
                organization_id = EXCLUDED.organization_id,
                role = EXCLUDED.role,
                failed_login_count = 0,
                locked_until = NULL
            """
        ),
        {
            "organization_id": org_id,
            "email": BOOTSTRAP_ADMIN_EMAIL,
            "password_hash": password_hash,
            "role": "administrador",
        },
    )

    if _table_exists(conn, "m8_schema", "connect_user_roles"):
        conn.execute(
            text(
                """
                INSERT INTO m8_schema.connect_user_roles (user_id, role, granted_at)
                SELECT id, CAST(:role AS m8_schema.connect_role), now()
                FROM public.users
                WHERE LOWER(email::text) = LOWER(:email)
                ON CONFLICT (user_id) DO UPDATE
                SET role = EXCLUDED.role,
                    granted_at = EXCLUDED.granted_at
                """
            ),
            {
                "email": BOOTSTRAP_ADMIN_EMAIL,
                "role": "admin_m8_connect",
            },
        )


def downgrade() -> None:
    conn = op.get_bind()

    if _table_exists(conn, "m8_schema", "connect_user_roles") and _table_exists(
        conn, "public", "users"
    ):
        conn.execute(
            text(
                """
                DELETE FROM m8_schema.connect_user_roles cur
                USING public.users u
                WHERE cur.user_id = u.id
                  AND LOWER(u.email::text) = LOWER(:email)
                """
            ),
            {"email": BOOTSTRAP_ADMIN_EMAIL},
        )

    if _table_exists(conn, "public", "users"):
        conn.execute(
            text(
                """
                DELETE FROM public.users
                WHERE LOWER(email::text) = LOWER(:email)
                """
            ),
            {"email": BOOTSTRAP_ADMIN_EMAIL},
        )

"""M8 Connect roles: connect_role enum, connect_user_roles, loader_profile.

Revision ID: 003_connect_roles
Revises: 002_job_queue_and_indexes
Create Date: 2026-06-18

Bootstrap admin: david.figueroa@m8solutions.com.mx
If user does not exist yet, run manually:
  INSERT INTO m8_schema.connect_user_roles (user_id, role, granted_at)
  SELECT id, 'admin_m8_connect'::m8_schema.connect_role, now()
  FROM public.users WHERE LOWER(email::text) = LOWER('david.figueroa@m8solutions.com.mx')
  ON CONFLICT (user_id) DO UPDATE SET role = EXCLUDED.role;
"""

from alembic import op

revision = "003_connect_roles"
down_revision = "002_job_queue_and_indexes"
branch_labels = None
depends_on = None

DEFAULT_LOADER_PERMISSIONS = """'{
  "menus": {
    "panel": true,
    "upload": true,
    "batches": true,
    "monitoring": false,
    "config": false
  },
  "upload": {
    "history": true,
    "catalogs": true
  },
  "config": {
    "catalogs_view": false,
    "history_view": false
  }
}'::jsonb"""

BOOTSTRAP_ADMIN_EMAIL = "david.figueroa@m8solutions.com.mx"


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS m8_schema")

    op.execute("""
        DO $$ BEGIN
            CREATE TYPE m8_schema.connect_role AS ENUM ('admin_m8_connect', 'loader');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS m8_schema.connect_user_roles (
            user_id UUID PRIMARY KEY
                REFERENCES public.users(id) ON DELETE CASCADE,
            role m8_schema.connect_role NOT NULL,
            granted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            granted_by UUID REFERENCES public.users(id) ON DELETE SET NULL
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS m8_schema.loader_profile (
            id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
            permissions JSONB NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_by UUID REFERENCES public.users(id) ON DELETE SET NULL
        )
    """)

    op.execute(f"""
        INSERT INTO m8_schema.loader_profile (id, permissions)
        VALUES (1, {DEFAULT_LOADER_PERMISSIONS})
        ON CONFLICT (id) DO NOTHING
    """)

    op.execute(f"""
        INSERT INTO m8_schema.connect_user_roles (user_id, role, granted_at)
        SELECT id, 'admin_m8_connect'::m8_schema.connect_role, now()
        FROM public.users
        WHERE LOWER(email::text) = LOWER('{BOOTSTRAP_ADMIN_EMAIL}')
        ON CONFLICT (user_id) DO UPDATE
        SET role = EXCLUDED.role,
            granted_at = EXCLUDED.granted_at
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS m8_schema.loader_profile")
    op.execute("DROP TABLE IF EXISTS m8_schema.connect_user_roles")
    op.execute("DROP TYPE IF EXISTS m8_schema.connect_role")

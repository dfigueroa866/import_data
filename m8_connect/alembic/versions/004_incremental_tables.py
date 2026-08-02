"""Incremental load configuration and run tracking tables.

Revision ID: 004_incremental_tables
Revises: 003_connect_roles
Create Date: 2026-06-22
"""

from alembic import op

revision = "004_incremental_tables"
down_revision = "003_connect_roles"
branch_labels = None
depends_on = None

INCREMENTAL_LOADER_PERMISSIONS = """'{
  "menus": {
    "panel": true,
    "upload": true,
    "batches": true,
    "monitoring": false,
    "config": false,
    "incremental": false
  },
  "upload": {
    "history": true,
    "catalogs": true
  },
  "config": {
    "catalogs_view": false,
    "history_view": false,
    "incremental_view": false
  }
}'::jsonb"""


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE staging_meta.incremental_run_status AS ENUM (
                'PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'NOTIFICATION_FAILED'
            );
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS staging_meta.incremental_schedule (
            id              SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
            enabled         BOOLEAN NOT NULL DEFAULT true,
            cron_expression VARCHAR(64) NOT NULL DEFAULT '0 22 * * 0',
            timezone        VARCHAR(64) NOT NULL DEFAULT 'America/Mexico_City',
            retention_years INT NOT NULL DEFAULT 3,
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_by      VARCHAR(128)
        )
    """)

    op.execute("""
        INSERT INTO staging_meta.incremental_schedule (id, enabled)
        VALUES (1, true)
        ON CONFLICT (id) DO NOTHING
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS staging_meta.incremental_org_profiles (
            organization_id     UUID PRIMARY KEY,
            organization_name   VARCHAR(120) NOT NULL,
            enabled             BOOLEAN NOT NULL DEFAULT true,
            source_path         TEXT NOT NULL,
            notification_emails TEXT[] NOT NULL DEFAULT '{}',
            default_granularity VARCHAR(16) CHECK (
                default_granularity IS NULL
                OR default_granularity IN ('weekly', 'monthly')
            ),
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS staging_meta.incremental_org_tables (
            id              BIGSERIAL PRIMARY KEY,
            organization_id UUID NOT NULL
                REFERENCES staging_meta.incremental_org_profiles(organization_id)
                ON DELETE CASCADE,
            load_kind       VARCHAR(16) NOT NULL CHECK (load_kind IN ('catalog', 'history')),
            catalog_slug    VARCHAR(64),
            enabled         BOOLEAN NOT NULL DEFAULT true,
            granularity     VARCHAR(16) CHECK (
                granularity IS NULL OR granularity IN ('weekly', 'monthly')
            ),
            UNIQUE (organization_id, load_kind, catalog_slug)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS staging_meta.incremental_runs (
            run_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id   UUID NOT NULL,
            load_date         DATE NOT NULL,
            started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            finished_at       TIMESTAMPTZ,
            status            staging_meta.incremental_run_status NOT NULL DEFAULT 'PENDING',
            error_message     TEXT,
            total_processed   BIGINT DEFAULT 0,
            total_inserted    BIGINT DEFAULT 0,
            total_updated     BIGINT DEFAULT 0,
            total_rejected    BIGINT DEFAULT 0,
            batch_ids         UUID[] DEFAULT '{}',
            metadata          JSONB DEFAULT '{}'
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_incremental_runs_org_date
        ON staging_meta.incremental_runs (organization_id, load_date DESC)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS staging_meta.incremental_retention_log (
            id              BIGSERIAL PRIMARY KEY,
            run_id_purged   UUID NOT NULL,
            organization_id UUID NOT NULL,
            purged_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            files_deleted   INT DEFAULT 0,
            rows_deleted    BIGINT DEFAULT 0,
            metadata        JSONB DEFAULT '{}'
        )
    """)

    op.execute(f"""
        UPDATE m8_schema.loader_profile
        SET permissions = {INCREMENTAL_LOADER_PERMISSIONS},
            updated_at = now()
        WHERE id = 1
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS staging_meta.incremental_retention_log")
    op.execute("DROP TABLE IF EXISTS staging_meta.incremental_runs")
    op.execute("DROP TABLE IF EXISTS staging_meta.incremental_org_tables")
    op.execute("DROP TABLE IF EXISTS staging_meta.incremental_org_profiles")
    op.execute("DROP TABLE IF EXISTS staging_meta.incremental_schedule")
    op.execute("DROP TYPE IF EXISTS staging_meta.incremental_run_status")

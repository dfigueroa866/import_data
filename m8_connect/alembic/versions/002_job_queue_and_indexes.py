"""Add job_queue table, notify trigger, and anti-duplicate index.

Revision ID: 002_job_queue_and_indexes
Revises: 001_initial_schema
Create Date: 2026-06-04

"""
from alembic import op

revision = "002_job_queue_and_indexes"
down_revision = "001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:


    op.execute("""
        CREATE TABLE IF NOT EXISTS staging_meta.job_queue (
            job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            job_type VARCHAR(100) NOT NULL,
            payload JSONB NOT NULL,
            status VARCHAR(50) DEFAULT 'PENDING',
            priority INTEGER DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            worker_id VARCHAR(100),
            retry_count INTEGER DEFAULT 0,
            max_retries INTEGER DEFAULT 3,
            error_message TEXT,
            progress JSONB DEFAULT NULL,
            CONSTRAINT valid_status CHECK (
                status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'CANCELLED')
            )
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_job_queue_pending
        ON staging_meta.job_queue(priority DESC, created_at ASC)
        WHERE status = 'PENDING'
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_job_queue_status
        ON staging_meta.job_queue(status)
    """)

    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_job_queue_unique_batch_pending
        ON staging_meta.job_queue ((payload->>'batch_id'))
        WHERE status IN ('PENDING', 'PROCESSING')
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION staging_meta.notify_new_job()
        RETURNS TRIGGER AS $$
        BEGIN
            PERFORM pg_notify('new_job_queued', NEW.job_id::text);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    op.execute("""
        DROP TRIGGER IF EXISTS job_queue_notify ON staging_meta.job_queue
    """)

    op.execute("""
        CREATE TRIGGER job_queue_notify
        AFTER INSERT ON staging_meta.job_queue
        FOR EACH ROW
        EXECUTE PROCEDURE staging_meta.notify_new_job()
    """)


def downgrade() -> None:


    op.execute("DROP TRIGGER IF EXISTS job_queue_notify ON staging_meta.job_queue")
    op.execute("DROP FUNCTION IF EXISTS staging_meta.notify_new_job()")
    op.execute("DROP INDEX IF EXISTS staging_meta.idx_job_queue_unique_batch_pending")
    op.execute("DROP INDEX IF EXISTS staging_meta.idx_job_queue_status")
    op.execute("DROP INDEX IF EXISTS staging_meta.idx_job_queue_pending")
    op.execute("DROP TABLE IF EXISTS staging_meta.job_queue")

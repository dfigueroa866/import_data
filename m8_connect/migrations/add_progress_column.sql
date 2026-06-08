-- Migration: Add progress column to job_queue table
-- This allows the worker to track processing progress in real-time

-- 1. Add progress column to job_queue
ALTER TABLE staging_meta.job_queue
ADD COLUMN IF NOT EXISTS progress JSONB DEFAULT NULL;

-- 2. Add comment for documentation
COMMENT ON COLUMN staging_meta.job_queue.progress IS 'Real-time processing progress with structure: {
  "progress_percentage": number (0-100),
  "current_operation": string,
  "chunks_processed": number,
  "rows_processed": number
}';

-- 3. Verify the change
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'staging_meta'
  AND table_name = 'job_queue'
  AND column_name = 'progress';

-- Expected output:
-- progress | jsonb | YES | NULL

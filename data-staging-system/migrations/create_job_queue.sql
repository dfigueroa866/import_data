-- Create job_queue table in staging_meta schema
CREATE TABLE IF NOT EXISTS staging_meta.job_queue (
  job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_type VARCHAR(100) NOT NULL,  -- 'PROCESS_FILE', 'STAGING_TO_PROD'
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
  
  CONSTRAINT valid_status CHECK (
    status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'CANCELLED')
  )
);

-- Create indexes for efficient queue processing
CREATE INDEX IF NOT EXISTS idx_job_queue_pending 
  ON staging_meta.job_queue(priority DESC, created_at ASC)
  WHERE status = 'PENDING';

CREATE INDEX IF NOT EXISTS idx_job_queue_status 
  ON staging_meta.job_queue(status);

-- Trigger function for notifying workers
CREATE OR REPLACE FUNCTION notify_new_job()
RETURNS TRIGGER AS $$
BEGIN
  PERFORM pg_notify('new_job_queued', NEW.job_id::text);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to execute notification on insert
DROP TRIGGER IF EXISTS job_queue_notify ON staging_meta.job_queue;
CREATE TRIGGER job_queue_notify
AFTER INSERT ON staging_meta.job_queue
FOR EACH ROW
EXECUTE FUNCTION notify_new_job();

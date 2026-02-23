-- DDL for staging_meta.rejected_records table
-- This table tracks records that were rejected during processing due to validation failures or data quality issues

CREATE TABLE IF NOT EXISTS staging_meta.rejected_records (
    -- Primary key
    rejection_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Foreign key to batch
    batch_id UUID NOT NULL REFERENCES staging_meta.batch_control(batch_id) ON DELETE CASCADE,
    
    -- Source information
    source_name CHARACTER VARYING(100) NOT NULL,
    source_row_number INTEGER,
    
    -- Rejection details
    rejection_reason CHARACTER VARYING(100) NOT NULL, -- VALIDATION_FAILED, DATA_TYPE_ERROR, BUSINESS_RULE_VIOLATION, etc.
    rejection_category CHARACTER VARYING(50) NOT NULL, -- CRITICAL, ERROR, WARNING
    
    -- Original data
    raw_data JSONB NOT NULL, -- Original data as received
    attempted_processed_data JSONB, -- Data after attempted transformations (if any)
    
    -- Validation details
    failed_validation_rules JSONB, -- Array of validation rules that failed
    validation_errors JSONB, -- Detailed validation error messages
    data_quality_score NUMERIC(5,2), -- Quality score if calculated (0-100)
    
    -- Processing context
    processing_stage CHARACTER VARYING(50), -- EXTRACT, TRANSFORM, VALIDATE, LOAD
    target_table CHARACTER VARYING(100), -- Intended target table
    target_schema CHARACTER VARYING(50) DEFAULT 'staging_data',
    
    -- Error details
    error_message TEXT, -- Human-readable error message
    error_details JSONB, -- Structured error information
    stack_trace TEXT, -- Technical stack trace if available
    
    -- Resolution tracking
    resolution_status CHARACTER VARYING(20) DEFAULT 'UNRESOLVED', -- UNRESOLVED, INVESTIGATING, RESOLVED, IGNORED
    resolution_notes TEXT, -- Notes about how the issue was resolved
    resolved_by CHARACTER VARYING(100), -- Who resolved the issue
    resolved_at TIMESTAMP WITH TIME ZONE, -- When the issue was resolved
    
    -- Reprocessing tracking
    can_reprocess BOOLEAN DEFAULT TRUE, -- Whether this record can be reprocessed
    reprocess_attempts INTEGER DEFAULT 0, -- Number of reprocessing attempts
    last_reprocess_attempt TIMESTAMP WITH TIME ZONE, -- Last reprocessing attempt
    
    -- Audit timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS ix_rejected_records_batch_id ON staging_meta.rejected_records(batch_id);
CREATE INDEX IF NOT EXISTS ix_rejected_records_source_name ON staging_meta.rejected_records(source_name);
CREATE INDEX IF NOT EXISTS ix_rejected_records_reason ON staging_meta.rejected_records(rejection_reason);
CREATE INDEX IF NOT EXISTS ix_rejected_records_category ON staging_meta.rejected_records(rejection_category);
CREATE INDEX IF NOT EXISTS ix_rejected_records_created ON staging_meta.rejected_records(created_at DESC);
CREATE INDEX IF NOT EXISTS ix_rejected_records_resolution ON staging_meta.rejected_records(resolution_status);
CREATE INDEX IF NOT EXISTS ix_rejected_records_stage ON staging_meta.rejected_records(processing_stage);

-- Create composite indexes for common queries
CREATE INDEX IF NOT EXISTS ix_rejected_records_source_created ON staging_meta.rejected_records(source_name, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_rejected_records_batch_reason ON staging_meta.rejected_records(batch_id, rejection_reason);
CREATE INDEX IF NOT EXISTS ix_rejected_records_unresolved ON staging_meta.rejected_records(resolution_status, created_at DESC) 
    WHERE resolution_status = 'UNRESOLVED';

-- Add comments for documentation
COMMENT ON TABLE staging_meta.rejected_records IS 'Tracks records that were rejected during processing due to validation failures or data quality issues';
COMMENT ON COLUMN staging_meta.rejected_records.rejection_id IS 'Unique identifier for the rejection record';
COMMENT ON COLUMN staging_meta.rejected_records.batch_id IS 'Reference to the batch that contained this rejected record';
COMMENT ON COLUMN staging_meta.rejected_records.source_name IS 'Name of the data source';
COMMENT ON COLUMN staging_meta.rejected_records.source_row_number IS 'Original row number from source data';
COMMENT ON COLUMN staging_meta.rejected_records.rejection_reason IS 'Primary reason for rejection (VALIDATION_FAILED, DATA_TYPE_ERROR, etc.)';
COMMENT ON COLUMN staging_meta.rejected_records.rejection_category IS 'Severity category (CRITICAL, ERROR, WARNING)';
COMMENT ON COLUMN staging_meta.rejected_records.raw_data IS 'Original data as received from source';
COMMENT ON COLUMN staging_meta.rejected_records.attempted_processed_data IS 'Data after attempted transformations (if any)';
COMMENT ON COLUMN staging_meta.rejected_records.failed_validation_rules IS 'Array of validation rules that failed';
COMMENT ON COLUMN staging_meta.rejected_records.validation_errors IS 'Detailed validation error messages';
COMMENT ON COLUMN staging_meta.rejected_records.data_quality_score IS 'Quality score if calculated (0-100)';
COMMENT ON COLUMN staging_meta.rejected_records.processing_stage IS 'Stage where rejection occurred (EXTRACT, TRANSFORM, VALIDATE, LOAD)';
COMMENT ON COLUMN staging_meta.rejected_records.target_table IS 'Intended target table';
COMMENT ON COLUMN staging_meta.rejected_records.target_schema IS 'Intended target schema';
COMMENT ON COLUMN staging_meta.rejected_records.error_message IS 'Human-readable error message';
COMMENT ON COLUMN staging_meta.rejected_records.error_details IS 'Structured error information';
COMMENT ON COLUMN staging_meta.rejected_records.stack_trace IS 'Technical stack trace if available';
COMMENT ON COLUMN staging_meta.rejected_records.resolution_status IS 'Status of issue resolution (UNRESOLVED, INVESTIGATING, RESOLVED, IGNORED)';
COMMENT ON COLUMN staging_meta.rejected_records.resolution_notes IS 'Notes about how the issue was resolved';
COMMENT ON COLUMN staging_meta.rejected_records.resolved_by IS 'Who resolved the issue';
COMMENT ON COLUMN staging_meta.rejected_records.resolved_at IS 'When the issue was resolved';
COMMENT ON COLUMN staging_meta.rejected_records.can_reprocess IS 'Whether this record can be reprocessed';
COMMENT ON COLUMN staging_meta.rejected_records.reprocess_attempts IS 'Number of reprocessing attempts';
COMMENT ON COLUMN staging_meta.rejected_records.last_reprocess_attempt IS 'Last reprocessing attempt timestamp';

-- Create trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_rejected_records_updated_at 
    BEFORE UPDATE ON staging_meta.rejected_records 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- Create view for common rejection analysis
CREATE OR REPLACE VIEW staging_meta.v_rejection_summary AS
SELECT 
    source_name,
    rejection_reason,
    rejection_category,
    processing_stage,
    COUNT(*) as rejection_count,
    COUNT(CASE WHEN resolution_status = 'UNRESOLVED' THEN 1 END) as unresolved_count,
    COUNT(CASE WHEN can_reprocess = true THEN 1 END) as reprocessable_count,
    AVG(data_quality_score) as avg_quality_score,
    MIN(created_at) as first_rejection,
    MAX(created_at) as last_rejection
FROM staging_meta.rejected_records
GROUP BY source_name, rejection_reason, rejection_category, processing_stage
ORDER BY rejection_count DESC, source_name;

COMMENT ON VIEW staging_meta.v_rejection_summary IS 'Summary view of rejection patterns by source and reason';

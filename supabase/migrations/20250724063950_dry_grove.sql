-- DDL for staging_meta.load_history table
-- This table tracks detailed load history and statistics for all data processing operations

CREATE TABLE staging_meta.load_history (
    -- Primary key
    load_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Foreign key to batch
    batch_id UUID NOT NULL REFERENCES staging_meta.batch_control(batch_id) ON DELETE CASCADE,
    
    -- Source information
    source_name CHARACTER VARYING(100) NOT NULL,
    load_type CHARACTER VARYING(50) NOT NULL, -- FULL, INCREMENTAL, DELTA, APPEND, REPLACE, MERGE, FILE_UPLOAD, API_SYNC, STREAM
    
    -- Target information
    target_table CHARACTER VARYING(100),
    target_schema CHARACTER VARYING(50) DEFAULT 'staging_data',
    
    -- Record statistics
    records_inserted INTEGER NOT NULL DEFAULT 0,
    records_updated INTEGER NOT NULL DEFAULT 0,
    records_deleted INTEGER NOT NULL DEFAULT 0,
    records_rejected INTEGER NOT NULL DEFAULT 0,
    
    -- Data quality metrics
    data_quality_score NUMERIC(5,2), -- 0-100 score
    validation_passed INTEGER NOT NULL DEFAULT 0,
    validation_failed INTEGER NOT NULL DEFAULT 0,
    
    -- Timing information
    load_start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    load_end_time TIMESTAMP WITH TIME ZONE,
    duration_seconds INTEGER,
    
    -- Status and error handling
    status CHARACTER VARYING(20) NOT NULL DEFAULT 'IN_PROGRESS', -- IN_PROGRESS, COMPLETED, FAILED, CANCELLED, PARTIALLY_COMPLETED
    error_details TEXT,
    
    -- Performance metrics
    rows_per_second NUMERIC(10,2),
    mb_per_second NUMERIC(10,2),
    
    -- Additional metadata
    metadata JSONB,
    load_config JSONB,
    
    -- Audit timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS ix_load_history_source_time ON staging_meta.load_history(source_name, load_start_time DESC);
CREATE INDEX IF NOT EXISTS ix_load_history_batch_id ON staging_meta.load_history(batch_id);
CREATE INDEX IF NOT EXISTS ix_load_history_status ON staging_meta.load_history(status);
CREATE INDEX IF NOT EXISTS ix_load_history_start_time ON staging_meta.load_history(load_start_time DESC);

-- Add comments for documentation
COMMENT ON TABLE staging_meta.load_history IS 'Tracks detailed load history and statistics for all data processing operations';
COMMENT ON COLUMN staging_meta.load_history.load_id IS 'Unique identifier for the load operation';
COMMENT ON COLUMN staging_meta.load_history.batch_id IS 'Reference to the batch that initiated this load';
COMMENT ON COLUMN staging_meta.load_history.source_name IS 'Name of the data source';
COMMENT ON COLUMN staging_meta.load_history.load_type IS 'Type of load operation (FULL, INCREMENTAL, etc.)';
COMMENT ON COLUMN staging_meta.load_history.target_table IS 'Target table name where data was loaded';
COMMENT ON COLUMN staging_meta.load_history.target_schema IS 'Target schema where data was loaded';
COMMENT ON COLUMN staging_meta.load_history.records_inserted IS 'Number of records inserted';
COMMENT ON COLUMN staging_meta.load_history.records_updated IS 'Number of records updated';
COMMENT ON COLUMN staging_meta.load_history.records_deleted IS 'Number of records deleted';
COMMENT ON COLUMN staging_meta.load_history.records_rejected IS 'Number of records rejected due to validation failures';
COMMENT ON COLUMN staging_meta.load_history.data_quality_score IS 'Overall data quality score (0-100)';
COMMENT ON COLUMN staging_meta.load_history.validation_passed IS 'Number of validation rules that passed';
COMMENT ON COLUMN staging_meta.load_history.validation_failed IS 'Number of validation rules that failed';
COMMENT ON COLUMN staging_meta.load_history.load_start_time IS 'Timestamp when load operation started';
COMMENT ON COLUMN staging_meta.load_history.load_end_time IS 'Timestamp when load operation ended';
COMMENT ON COLUMN staging_meta.load_history.duration_seconds IS 'Total duration of load operation in seconds';
COMMENT ON COLUMN staging_meta.load_history.status IS 'Status of the load operation';
COMMENT ON COLUMN staging_meta.load_history.error_details IS 'Detailed error message if load failed';
COMMENT ON COLUMN staging_meta.load_history.rows_per_second IS 'Processing rate in rows per second';
COMMENT ON COLUMN staging_meta.load_history.mb_per_second IS 'Processing rate in megabytes per second';
COMMENT ON COLUMN staging_meta.load_history.metadata IS 'Additional metadata about the load operation';
COMMENT ON COLUMN staging_meta.load_history.load_config IS 'Configuration used for this specific load';

-- Create trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_load_history_updated_at 
    BEFORE UPDATE ON staging_meta.load_history 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();
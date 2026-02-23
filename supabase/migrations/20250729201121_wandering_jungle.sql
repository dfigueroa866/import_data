-- DDL for m8_schema.data_load_log table
-- This table tracks data loading activities by file type with comprehensive logging

-- Create the main data load log table
CREATE TABLE IF NOT EXISTS m8_schema.data_load_log (
    -- Primary key
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- File type and source information
    file_type VARCHAR(50) NOT NULL, -- CSV, XLSX, JSON, PARQUET, etc.
    file_category VARCHAR(100), -- products, customers, sales, inventory, etc.
    source_name VARCHAR(200) NOT NULL, -- Name of the data source
    source_file_path TEXT, -- Full path to the source file
    source_file_name VARCHAR(500), -- Original filename
    
    -- Load timing information
    load_start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    load_end_time TIMESTAMP WITH TIME ZONE,
    load_duration_seconds INTEGER,
    
    -- Load status and results
    load_status VARCHAR(20) NOT NULL DEFAULT 'IN_PROGRESS', 
    -- Status values: IN_PROGRESS, COMPLETED, FAILED, CANCELLED, PARTIAL_SUCCESS
    
    -- Data metrics
    records_processed INTEGER DEFAULT 0,
    records_inserted INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,
    records_rejected INTEGER DEFAULT 0,
    file_size_bytes BIGINT,
    
    -- Quality and validation
    data_quality_score NUMERIC(5,2), -- 0-100 quality score
    validation_passed INTEGER DEFAULT 0,
    validation_failed INTEGER DEFAULT 0,
    
    -- Error handling and troubleshooting
    error_code VARCHAR(50), -- Standardized error codes
    error_message TEXT, -- Human-readable error description
    error_details JSONB, -- Structured error information
    stack_trace TEXT, -- Technical stack trace for debugging
    
    -- Processing context
    batch_id UUID, -- Reference to staging_meta.batch_control if applicable
    target_table VARCHAR(100), -- Target table name
    target_schema VARCHAR(50) DEFAULT 'm8_schema',
    processing_mode VARCHAR(50) DEFAULT 'BATCH', -- BATCH, STREAMING, MANUAL
    
    -- User and system context
    initiated_by VARCHAR(100), -- User or system process that started the load
    processing_server VARCHAR(100), -- Server/instance that processed the load
    application_version VARCHAR(50), -- Version of the application
    
    -- File integrity and validation
    file_checksum VARCHAR(128), -- MD5 or SHA256 checksum
    file_encoding VARCHAR(50), -- UTF-8, Latin-1, etc.
    delimiter_used VARCHAR(10), -- For CSV files
    
    -- Performance metrics
    rows_per_second NUMERIC(10,2),
    mb_per_second NUMERIC(10,2),
    memory_peak_mb NUMERIC(10,2),
    
    -- Audit timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    CONSTRAINT chk_load_status CHECK (load_status IN ('IN_PROGRESS', 'COMPLETED', 'FAILED', 'CANCELLED', 'PARTIAL_SUCCESS')),
    CONSTRAINT chk_processing_mode CHECK (processing_mode IN ('BATCH', 'STREAMING', 'MANUAL', 'SCHEDULED')),
    CONSTRAINT chk_quality_score CHECK (data_quality_score IS NULL OR (data_quality_score >= 0 AND data_quality_score <= 100)),
    CONSTRAINT chk_load_times CHECK (load_end_time IS NULL OR load_end_time >= load_start_time),
    CONSTRAINT chk_record_counts CHECK (
        records_processed >= 0 AND 
        records_inserted >= 0 AND 
        records_updated >= 0 AND 
        records_rejected >= 0 AND
        records_processed >= (records_inserted + records_updated + records_rejected)
    )
);

-- Create summary table for quick lookups of latest loads by file type
CREATE TABLE IF NOT EXISTS m8_schema.data_load_summary (
    -- Composite primary key
    file_type VARCHAR(50) NOT NULL,
    file_category VARCHAR(100) NOT NULL,
    
    -- Latest load information
    last_successful_load TIMESTAMP WITH TIME ZONE,
    last_attempted_load TIMESTAMP WITH TIME ZONE,
    last_load_status VARCHAR(20),
    last_load_duration_seconds INTEGER,
    
    -- Aggregate statistics
    total_loads INTEGER DEFAULT 0,
    successful_loads INTEGER DEFAULT 0,
    failed_loads INTEGER DEFAULT 0,
    total_records_processed BIGINT DEFAULT 0,
    
    -- Performance metrics
    avg_load_duration_seconds INTEGER,
    avg_quality_score NUMERIC(5,2),
    avg_rows_per_second NUMERIC(10,2),
    
    -- Latest file information
    last_file_name VARCHAR(500),
    last_file_size_bytes BIGINT,
    last_records_count INTEGER,
    
    -- Status tracking
    is_active BOOLEAN DEFAULT TRUE,
    next_expected_load TIMESTAMP WITH TIME ZONE,
    load_frequency VARCHAR(50), -- DAILY, WEEKLY, MONTHLY, ON_DEMAND
    
    -- Audit fields
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- Primary key
    PRIMARY KEY (file_type, file_category),
    
    -- Constraints
    CONSTRAINT chk_summary_load_status CHECK (last_load_status IN ('IN_PROGRESS', 'COMPLETED', 'FAILED', 'CANCELLED', 'PARTIAL_SUCCESS')),
    CONSTRAINT chk_summary_frequency CHECK (load_frequency IN ('DAILY', 'WEEKLY', 'MONTHLY', 'ON_DEMAND', 'REAL_TIME'))
);

-- Create indexes for optimal performance
CREATE INDEX IF NOT EXISTS ix_data_load_log_file_type_time ON m8_schema.data_load_log(file_type, load_start_time DESC);
CREATE INDEX IF NOT EXISTS ix_data_load_log_category_time ON m8_schema.data_load_log(file_category, load_start_time DESC);
CREATE INDEX IF NOT EXISTS ix_data_load_log_status ON m8_schema.data_load_log(load_status);
CREATE INDEX IF NOT EXISTS ix_data_load_log_source ON m8_schema.data_load_log(source_name);
CREATE INDEX IF NOT EXISTS ix_data_load_log_batch_id ON m8_schema.data_load_log(batch_id) WHERE batch_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_data_load_log_created ON m8_schema.data_load_log(created_at DESC);
CREATE INDEX IF NOT EXISTS ix_data_load_log_error_code ON m8_schema.data_load_log(error_code) WHERE error_code IS NOT NULL;

-- Composite indexes for common query patterns
CREATE INDEX IF NOT EXISTS ix_data_load_log_type_category_time ON m8_schema.data_load_log(file_type, file_category, load_start_time DESC);
CREATE INDEX IF NOT EXISTS ix_data_load_log_status_time ON m8_schema.data_load_log(load_status, load_start_time DESC);

-- Indexes for summary table
CREATE INDEX IF NOT EXISTS ix_data_load_summary_last_load ON m8_schema.data_load_summary(last_attempted_load DESC);
CREATE INDEX IF NOT EXISTS ix_data_load_summary_status ON m8_schema.data_load_summary(last_load_status);
CREATE INDEX IF NOT EXISTS ix_data_load_summary_active ON m8_schema.data_load_summary(is_active) WHERE is_active = TRUE;

-- Create trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_data_load_log_updated_at 
    BEFORE UPDATE ON m8_schema.data_load_log 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_data_load_summary_updated_at 
    BEFORE UPDATE ON m8_schema.data_load_summary 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- Create view for easy querying of latest loads by file type
CREATE OR REPLACE VIEW m8_schema.v_latest_loads_by_type AS
SELECT 
    file_type,
    file_category,
    source_name,
    load_start_time as last_load_time,
    load_status,
    records_processed,
    data_quality_score,
    load_duration_seconds,
    error_message,
    ROW_NUMBER() OVER (PARTITION BY file_type, file_category ORDER BY load_start_time DESC) as rn
FROM m8_schema.data_load_log
WHERE load_status IN ('COMPLETED', 'FAILED', 'PARTIAL_SUCCESS');

-- Create view for load statistics
CREATE OR REPLACE VIEW m8_schema.v_load_statistics AS
SELECT 
    file_type,
    file_category,
    COUNT(*) as total_loads,
    COUNT(CASE WHEN load_status = 'COMPLETED' THEN 1 END) as successful_loads,
    COUNT(CASE WHEN load_status = 'FAILED' THEN 1 END) as failed_loads,
    ROUND(
        COUNT(CASE WHEN load_status = 'COMPLETED' THEN 1 END)::NUMERIC / 
        NULLIF(COUNT(*), 0) * 100, 2
    ) as success_rate_percent,
    MAX(load_start_time) as last_load_time,
    AVG(load_duration_seconds) as avg_duration_seconds,
    AVG(data_quality_score) as avg_quality_score,
    SUM(records_processed) as total_records_processed
FROM m8_schema.data_load_log
WHERE load_start_time >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY file_type, file_category
ORDER BY last_load_time DESC;

-- Add comments for documentation
COMMENT ON TABLE m8_schema.data_load_log IS 'Comprehensive log of all data loading activities by file type';
COMMENT ON TABLE m8_schema.data_load_summary IS 'Summary table for quick lookups of latest load status by file type';
COMMENT ON VIEW m8_schema.v_latest_loads_by_type IS 'View showing the most recent load for each file type and category';
COMMENT ON VIEW m8_schema.v_load_statistics IS 'View providing load statistics and success rates by file type';

-- Add column comments for key fields
COMMENT ON COLUMN m8_schema.data_load_log.file_type IS 'Type of file processed (CSV, XLSX, JSON, PARQUET)';
COMMENT ON COLUMN m8_schema.data_load_log.file_category IS 'Business category of data (products, customers, sales, etc.)';
COMMENT ON COLUMN m8_schema.data_load_log.load_status IS 'Current status of the load operation';
COMMENT ON COLUMN m8_schema.data_load_log.data_quality_score IS 'Overall data quality score (0-100)';
COMMENT ON COLUMN m8_schema.data_load_log.batch_id IS 'Reference to staging system batch if applicable';
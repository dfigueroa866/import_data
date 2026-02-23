-- Stored procedure to maintain the data_load_summary table
-- This should be called after each load operation completes

CREATE OR REPLACE FUNCTION m8_schema.update_load_summary(
    p_file_type VARCHAR(50),
    p_file_category VARCHAR(100),
    p_load_status VARCHAR(20),
    p_load_duration INTEGER DEFAULT NULL,
    p_file_name VARCHAR(500) DEFAULT NULL,
    p_file_size BIGINT DEFAULT NULL,
    p_records_count INTEGER DEFAULT NULL,
    p_quality_score NUMERIC(5,2) DEFAULT NULL
)
RETURNS VOID AS $$
DECLARE
    v_is_successful BOOLEAN;
    v_current_stats RECORD;
BEGIN
    -- Determine if this was a successful load
    v_is_successful := (p_load_status = 'COMPLETED');
    
    -- Get current statistics for this file type/category
    SELECT 
        total_loads,
        successful_loads,
        failed_loads,
        avg_load_duration_seconds,
        avg_quality_score
    INTO v_current_stats
    FROM m8_schema.data_load_summary
    WHERE file_type = p_file_type AND file_category = p_file_category;
    
    -- Insert or update the summary record
    INSERT INTO m8_schema.data_load_summary (
        file_type,
        file_category,
        last_attempted_load,
        last_successful_load,
        last_load_status,
        last_load_duration_seconds,
        total_loads,
        successful_loads,
        failed_loads,
        last_file_name,
        last_file_size_bytes,
        last_records_count,
        avg_load_duration_seconds,
        avg_quality_score,
        load_frequency
    ) VALUES (
        p_file_type,
        p_file_category,
        CURRENT_TIMESTAMP,
        CASE WHEN v_is_successful THEN CURRENT_TIMESTAMP ELSE NULL END,
        p_load_status,
        p_load_duration,
        1, -- total_loads
        CASE WHEN v_is_successful THEN 1 ELSE 0 END, -- successful_loads
        CASE WHEN v_is_successful THEN 0 ELSE 1 END, -- failed_loads
        p_file_name,
        p_file_size,
        p_records_count,
        p_load_duration,
        p_quality_score,
        'ON_DEMAND' -- default frequency
    )
    ON CONFLICT (file_type, file_category) 
    DO UPDATE SET
        last_attempted_load = CURRENT_TIMESTAMP,
        last_successful_load = CASE 
            WHEN v_is_successful THEN CURRENT_TIMESTAMP 
            ELSE data_load_summary.last_successful_load 
        END,
        last_load_status = p_load_status,
        last_load_duration_seconds = p_load_duration,
        total_loads = data_load_summary.total_loads + 1,
        successful_loads = data_load_summary.successful_loads + CASE WHEN v_is_successful THEN 1 ELSE 0 END,
        failed_loads = data_load_summary.failed_loads + CASE WHEN v_is_successful THEN 0 ELSE 1 END,
        last_file_name = COALESCE(p_file_name, data_load_summary.last_file_name),
        last_file_size_bytes = COALESCE(p_file_size, data_load_summary.last_file_size_bytes),
        last_records_count = COALESCE(p_records_count, data_load_summary.last_records_count),
        -- Calculate running average for duration
        avg_load_duration_seconds = CASE 
            WHEN p_load_duration IS NOT NULL THEN
                ROUND((COALESCE(data_load_summary.avg_load_duration_seconds, 0) * data_load_summary.total_loads + p_load_duration) / (data_load_summary.total_loads + 1))
            ELSE data_load_summary.avg_load_duration_seconds
        END,
        -- Calculate running average for quality score
        avg_quality_score = CASE 
            WHEN p_quality_score IS NOT NULL AND v_is_successful THEN
                ROUND((COALESCE(data_load_summary.avg_quality_score, 0) * data_load_summary.successful_loads + p_quality_score) / (data_load_summary.successful_loads + 1), 2)
            ELSE data_load_summary.avg_quality_score
        END,
        updated_at = CURRENT_TIMESTAMP;
        
END;
$$ LANGUAGE plpgsql;

-- Function to clean up old log entries (retention policy)
CREATE OR REPLACE FUNCTION m8_schema.cleanup_old_load_logs(
    p_retention_days INTEGER DEFAULT 90
)
RETURNS INTEGER AS $$
DECLARE
    v_deleted_count INTEGER;
BEGIN
    -- Delete log entries older than retention period
    DELETE FROM m8_schema.data_load_log
    WHERE load_start_time < CURRENT_TIMESTAMP - (p_retention_days || ' days')::INTERVAL
      AND load_status IN ('COMPLETED', 'FAILED', 'CANCELLED'); -- Keep IN_PROGRESS loads regardless of age
    
    GET DIAGNOSTICS v_deleted_count = ROW_COUNT;
    
    -- Log the cleanup operation
    INSERT INTO m8_schema.data_load_log (
        file_type,
        file_category,
        source_name,
        load_start_time,
        load_end_time,
        load_status,
        records_processed,
        initiated_by,
        processing_mode,
        error_message
    ) VALUES (
        'SYSTEM',
        'maintenance',
        'log_cleanup',
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP,
        'COMPLETED',
        v_deleted_count,
        'system_maintenance',
        'MANUAL',
        'Cleaned up ' || v_deleted_count || ' log entries older than ' || p_retention_days || ' days'
    );
    
    RETURN v_deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Example usage of the maintenance functions:

-- Update summary after a successful load
-- SELECT m8_schema.update_load_summary('CSV', 'products', 'COMPLETED', 45, 'products_20250129.csv', 2048576, 1500, 98.5);

-- Update summary after a failed load
-- SELECT m8_schema.update_load_summary('XLSX', 'customers', 'FAILED', 120, 'customers_bad.xlsx', 5242880, 0, NULL);

-- Clean up logs older than 90 days
-- SELECT m8_schema.cleanup_old_load_logs(90);
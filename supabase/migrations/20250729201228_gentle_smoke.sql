-- Useful queries for monitoring and reporting data loads

-- Query 1: Check last load date by file type (most common use case)
SELECT 
    file_type,
    file_category,
    MAX(CASE WHEN load_status = 'COMPLETED' THEN load_start_time END) as last_successful_load,
    MAX(load_start_time) as last_attempted_load,
    COUNT(*) as total_loads_today,
    COUNT(CASE WHEN load_status = 'COMPLETED' THEN 1 END) as successful_loads_today,
    COUNT(CASE WHEN load_status = 'FAILED' THEN 1 END) as failed_loads_today
FROM m8_schema.data_load_log
WHERE load_start_time >= CURRENT_DATE
GROUP BY file_type, file_category
ORDER BY last_attempted_load DESC;

-- Query 2: Dashboard view - Current load status summary
SELECT 
    s.file_type,
    s.file_category,
    s.last_successful_load,
    s.last_attempted_load,
    s.last_load_status,
    s.total_loads,
    s.successful_loads,
    s.failed_loads,
    ROUND((s.successful_loads::NUMERIC / NULLIF(s.total_loads, 0)) * 100, 2) as success_rate,
    s.avg_quality_score,
    CASE 
        WHEN s.last_successful_load IS NULL THEN 'Never loaded'
        WHEN s.last_successful_load < CURRENT_TIMESTAMP - INTERVAL '1 day' AND s.load_frequency = 'DAILY' THEN 'Overdue'
        WHEN s.last_successful_load < CURRENT_TIMESTAMP - INTERVAL '7 days' AND s.load_frequency = 'WEEKLY' THEN 'Overdue'
        WHEN s.last_successful_load < CURRENT_TIMESTAMP - INTERVAL '6 hours' THEN 'Stale'
        ELSE 'Current'
    END as data_freshness,
    -- Check if there's a load currently in progress
    CASE WHEN EXISTS (
        SELECT 1 FROM m8_schema.data_load_log l 
        WHERE l.file_type = s.file_type 
        AND l.file_category = s.file_category 
        AND l.load_status = 'IN_PROGRESS'
    ) THEN 'Processing' ELSE 'Idle' END as current_status
FROM m8_schema.data_load_summary s
WHERE s.is_active = TRUE
ORDER BY s.last_attempted_load DESC NULLS LAST;

-- Query 3: Identify problematic file types (high failure rate)
SELECT 
    file_type,
    file_category,
    total_loads,
    failed_loads,
    ROUND((failed_loads::NUMERIC / NULLIF(total_loads, 0)) * 100, 2) as failure_rate,
    last_attempted_load,
    avg_quality_score
FROM m8_schema.data_load_summary
WHERE total_loads >= 5 -- Only consider file types with sufficient load attempts
  AND (failed_loads::NUMERIC / NULLIF(total_loads, 0)) > 0.1 -- Failure rate > 10%
ORDER BY failure_rate DESC, total_loads DESC;

-- Query 4: Load performance trends (last 7 days)
SELECT 
    DATE_TRUNC('day', load_start_time) as load_date,
    file_type,
    file_category,
    COUNT(*) as loads_count,
    COUNT(CASE WHEN load_status = 'COMPLETED' THEN 1 END) as successful_count,
    AVG(load_duration_seconds) as avg_duration,
    AVG(rows_per_second) as avg_throughput,
    SUM(records_processed) as total_records
FROM m8_schema.data_load_log
WHERE load_start_time >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY DATE_TRUNC('day', load_start_time), file_type, file_category
ORDER BY load_date DESC, file_type, file_category;

-- Query 5: Error analysis - most common errors by file type
SELECT 
    file_type,
    file_category,
    error_code,
    COUNT(*) as error_count,
    MAX(load_start_time) as last_occurrence,
    STRING_AGG(DISTINCT error_message, '; ' ORDER BY error_message) as sample_messages
FROM m8_schema.data_load_log
WHERE load_status = 'FAILED'
  AND load_start_time >= CURRENT_TIMESTAMP - INTERVAL '30 days'
  AND error_code IS NOT NULL
GROUP BY file_type, file_category, error_code
ORDER BY error_count DESC, last_occurrence DESC;

-- Query 6: Data quality trends
SELECT 
    file_type,
    file_category,
    DATE_TRUNC('week', load_start_time) as week_start,
    COUNT(*) as loads_count,
    AVG(data_quality_score) as avg_quality_score,
    MIN(data_quality_score) as min_quality_score,
    MAX(data_quality_score) as max_quality_score,
    STDDEV(data_quality_score) as quality_score_stddev
FROM m8_schema.data_load_log
WHERE load_status = 'COMPLETED'
  AND data_quality_score IS NOT NULL
  AND load_start_time >= CURRENT_TIMESTAMP - INTERVAL '12 weeks'
GROUP BY file_type, file_category, DATE_TRUNC('week', load_start_time)
ORDER BY week_start DESC, file_type, file_category;

-- Query 7: Find long-running or stuck loads
SELECT 
    log_id,
    file_type,
    file_category,
    source_name,
    load_start_time,
    EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - load_start_time))/60 as minutes_running,
    initiated_by,
    batch_id
FROM m8_schema.data_load_log
WHERE load_status = 'IN_PROGRESS'
  AND load_start_time < CURRENT_TIMESTAMP - INTERVAL '30 minutes' -- Running for more than 30 minutes
ORDER BY load_start_time ASC;

-- Query 8: File size vs performance analysis
SELECT 
    file_type,
    CASE 
        WHEN file_size_bytes < 1048576 THEN 'Small (<1MB)'
        WHEN file_size_bytes < 10485760 THEN 'Medium (1-10MB)'
        WHEN file_size_bytes < 104857600 THEN 'Large (10-100MB)'
        ELSE 'Very Large (>100MB)'
    END as file_size_category,
    COUNT(*) as load_count,
    AVG(load_duration_seconds) as avg_duration,
    AVG(rows_per_second) as avg_throughput,
    AVG(data_quality_score) as avg_quality
FROM m8_schema.data_load_log
WHERE load_status = 'COMPLETED'
  AND file_size_bytes IS NOT NULL
  AND load_start_time >= CURRENT_TIMESTAMP - INTERVAL '30 days'
GROUP BY file_type, 
    CASE 
        WHEN file_size_bytes < 1048576 THEN 'Small (<1MB)'
        WHEN file_size_bytes < 10485760 THEN 'Medium (1-10MB)'
        WHEN file_size_bytes < 104857600 THEN 'Large (10-100MB)'
        ELSE 'Very Large (>100MB)'
    END
ORDER BY file_type, 
    CASE 
        WHEN file_size_bytes < 1048576 THEN 1
        WHEN file_size_bytes < 10485760 THEN 2
        WHEN file_size_bytes < 104857600 THEN 3
        ELSE 4
    END;

-- Query 9: Hourly load distribution (identify peak times)
SELECT 
    EXTRACT(HOUR FROM load_start_time) as hour_of_day,
    COUNT(*) as total_loads,
    COUNT(CASE WHEN load_status = 'COMPLETED' THEN 1 END) as successful_loads,
    AVG(load_duration_seconds) as avg_duration,
    AVG(records_processed) as avg_records
FROM m8_schema.data_load_log
WHERE load_start_time >= CURRENT_TIMESTAMP - INTERVAL '7 days'
GROUP BY EXTRACT(HOUR FROM load_start_time)
ORDER BY hour_of_day;

-- Query 10: Data freshness report for business users
SELECT 
    file_category as "Data Category",
    file_type as "File Type",
    last_successful_load as "Last Successful Load",
    CASE 
        WHEN last_successful_load IS NULL THEN 'Never'
        WHEN last_successful_load >= CURRENT_TIMESTAMP - INTERVAL '1 hour' THEN 'Very Fresh'
        WHEN last_successful_load >= CURRENT_TIMESTAMP - INTERVAL '6 hours' THEN 'Fresh'
        WHEN last_successful_load >= CURRENT_TIMESTAMP - INTERVAL '1 day' THEN 'Acceptable'
        WHEN last_successful_load >= CURRENT_TIMESTAMP - INTERVAL '3 days' THEN 'Stale'
        ELSE 'Very Stale'
    END as "Data Freshness",
    total_loads as "Total Loads",
    ROUND((successful_loads::NUMERIC / NULLIF(total_loads, 0)) * 100, 1) as "Success Rate %",
    ROUND(avg_quality_score, 1) as "Avg Quality Score"
FROM m8_schema.data_load_summary
WHERE is_active = TRUE
ORDER BY 
    CASE 
        WHEN last_successful_load IS NULL THEN 6
        WHEN last_successful_load >= CURRENT_TIMESTAMP - INTERVAL '1 hour' THEN 1
        WHEN last_successful_load >= CURRENT_TIMESTAMP - INTERVAL '6 hours' THEN 2
        WHEN last_successful_load >= CURRENT_TIMESTAMP - INTERVAL '1 day' THEN 3
        WHEN last_successful_load >= CURRENT_TIMESTAMP - INTERVAL '3 days' THEN 4
        ELSE 5
    END,
    file_category, file_type;
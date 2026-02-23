-- Sample INSERT/UPDATE statements for m8_schema.data_load_log
-- These examples show how to maintain the data load log

-- Example 1: Starting a new load operation
INSERT INTO m8_schema.data_load_log (
    file_type,
    file_category,
    source_name,
    source_file_path,
    source_file_name,
    load_start_time,
    load_status,
    file_size_bytes,
    initiated_by,
    processing_mode,
    target_table,
    batch_id
) VALUES (
    'CSV',
    'products',
    'daily_products_feed',
    '/data/uploads/products_20250129.csv',
    'products_20250129.csv',
    CURRENT_TIMESTAMP,
    'IN_PROGRESS',
    2048576, -- 2MB file
    'automated_etl_process',
    'BATCH',
    'products',
    'a1b2c3d4-e5f6-7890-abcd-ef1234567890'::UUID
);

-- Example 2: Completing a successful load
UPDATE m8_schema.data_load_log 
SET 
    load_end_time = CURRENT_TIMESTAMP,
    load_duration_seconds = EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - load_start_time))::INTEGER,
    load_status = 'COMPLETED',
    records_processed = 1500,
    records_inserted = 1450,
    records_updated = 50,
    records_rejected = 0,
    data_quality_score = 98.5,
    validation_passed = 15,
    validation_failed = 0,
    rows_per_second = 1500.0 / EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - load_start_time)),
    file_checksum = 'a1b2c3d4e5f67890abcdef1234567890',
    file_encoding = 'UTF-8',
    delimiter_used = ','
WHERE log_id = (
    SELECT log_id FROM m8_schema.data_load_log 
    WHERE source_name = 'daily_products_feed' 
    AND load_status = 'IN_PROGRESS'
    ORDER BY load_start_time DESC 
    LIMIT 1
);

-- Example 3: Recording a failed load
UPDATE m8_schema.data_load_log 
SET 
    load_end_time = CURRENT_TIMESTAMP,
    load_duration_seconds = EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - load_start_time))::INTEGER,
    load_status = 'FAILED',
    error_code = 'VALIDATION_ERROR',
    error_message = 'Data validation failed: 150 records with invalid product_id format',
    error_details = jsonb_build_object(
        'validation_errors', jsonb_build_array(
            jsonb_build_object('rule', 'product_id_format', 'failed_count', 150),
            jsonb_build_object('rule', 'price_range', 'failed_count', 25)
        ),
        'first_error_row', 45,
        'total_errors', 175
    ),
    records_processed = 500,
    records_rejected = 175,
    data_quality_score = 65.0,
    validation_passed = 8,
    validation_failed = 7
WHERE log_id = (
    SELECT log_id FROM m8_schema.data_load_log 
    WHERE source_name = 'weekly_inventory_update' 
    AND load_status = 'IN_PROGRESS'
    ORDER BY load_start_time DESC 
    LIMIT 1
);

-- Example 4: Insert/Update summary table (typically done via trigger or stored procedure)
INSERT INTO m8_schema.data_load_summary (
    file_type,
    file_category,
    last_successful_load,
    last_attempted_load,
    last_load_status,
    last_load_duration_seconds,
    total_loads,
    successful_loads,
    failed_loads,
    last_file_name,
    last_file_size_bytes,
    last_records_count,
    load_frequency
) VALUES (
    'CSV',
    'products',
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP,
    'COMPLETED',
    45,
    1,
    1,
    0,
    'products_20250129.csv',
    2048576,
    1500,
    'DAILY'
) ON CONFLICT (file_type, file_category) 
DO UPDATE SET
    last_attempted_load = EXCLUDED.last_attempted_load,
    last_load_status = EXCLUDED.last_load_status,
    last_load_duration_seconds = EXCLUDED.last_load_duration_seconds,
    total_loads = data_load_summary.total_loads + 1,
    successful_loads = CASE 
        WHEN EXCLUDED.last_load_status = 'COMPLETED' 
        THEN data_load_summary.successful_loads + 1 
        ELSE data_load_summary.successful_loads 
    END,
    failed_loads = CASE 
        WHEN EXCLUDED.last_load_status = 'FAILED' 
        THEN data_load_summary.failed_loads + 1 
        ELSE data_load_summary.failed_loads 
    END,
    last_successful_load = CASE 
        WHEN EXCLUDED.last_load_status = 'COMPLETED' 
        THEN EXCLUDED.last_attempted_load 
        ELSE data_load_summary.last_successful_load 
    END,
    last_file_name = EXCLUDED.last_file_name,
    last_file_size_bytes = EXCLUDED.last_file_size_bytes,
    last_records_count = EXCLUDED.last_records_count,
    updated_at = CURRENT_TIMESTAMP;

-- Example 5: Bulk insert for multiple file types
INSERT INTO m8_schema.data_load_log (
    file_type, file_category, source_name, source_file_name, 
    load_start_time, load_status, initiated_by, processing_mode
) VALUES 
    ('XLSX', 'customers', 'customer_master_data', 'customers_202501.xlsx', CURRENT_TIMESTAMP, 'IN_PROGRESS', 'data_team', 'MANUAL'),
    ('JSON', 'sales', 'daily_sales_api', 'sales_api_response.json', CURRENT_TIMESTAMP, 'IN_PROGRESS', 'api_scheduler', 'SCHEDULED'),
    ('PARQUET', 'analytics', 'warehouse_export', 'analytics_data.parquet', CURRENT_TIMESTAMP, 'IN_PROGRESS', 'etl_pipeline', 'BATCH');

-- Example 6: Query to check last load date by file type
SELECT 
    file_type,
    file_category,
    source_name,
    last_successful_load,
    last_attempted_load,
    last_load_status,
    total_loads,
    successful_loads,
    failed_loads,
    ROUND((successful_loads::NUMERIC / NULLIF(total_loads, 0)) * 100, 2) as success_rate_percent,
    CASE 
        WHEN last_successful_load IS NULL THEN 'Never loaded'
        WHEN last_successful_load < CURRENT_TIMESTAMP - INTERVAL '1 day' THEN 'Overdue'
        WHEN last_successful_load < CURRENT_TIMESTAMP - INTERVAL '12 hours' THEN 'Stale'
        ELSE 'Recent'
    END as freshness_status
FROM m8_schema.data_load_summary
WHERE is_active = TRUE
ORDER BY last_attempted_load DESC NULLS LAST;

-- Example 7: Query to find recent failed loads
SELECT 
    file_type,
    file_category,
    source_name,
    load_start_time,
    error_code,
    error_message,
    records_processed,
    records_rejected
FROM m8_schema.data_load_log
WHERE load_status = 'FAILED'
  AND load_start_time >= CURRENT_TIMESTAMP - INTERVAL '7 days'
ORDER BY load_start_time DESC;

-- Example 8: Query for load performance analysis
SELECT 
    file_type,
    file_category,
    COUNT(*) as total_loads,
    AVG(load_duration_seconds) as avg_duration_seconds,
    AVG(rows_per_second) as avg_rows_per_second,
    AVG(data_quality_score) as avg_quality_score,
    MAX(records_processed) as max_records_processed,
    MIN(load_start_time) as first_load,
    MAX(load_start_time) as latest_load
FROM m8_schema.data_load_log
WHERE load_status = 'COMPLETED'
  AND load_start_time >= CURRENT_TIMESTAMP - INTERVAL '30 days'
GROUP BY file_type, file_category
ORDER BY avg_duration_seconds DESC;
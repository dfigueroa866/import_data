# alembic/versions/001_initial_schema.py
"""Initial schema creation

Revision ID: 001_initial_schema
Revises: 
Create Date: 2025-07-22 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

# Try importing the enums safely to get values
try:
    from src.data_staging.models.batch import BatchStatus
    from src.data_staging.models.load_history import LoadStatus
    from src.data_staging.models.validation import ValidationStatus
except ImportError:
    try:
        from data_staging.models.batch import BatchStatus
        from data_staging.models.load_history import LoadStatus
        from data_staging.models.validation import ValidationStatus
    except ImportError:
        # Fallback values if import fails
        class BatchStatus:
            PENDING = "PENDING"
        class LoadStatus:
            IN_PROGRESS = "IN_PROGRESS"
        class ValidationStatus:
            PENDING = "PENDING"

# revision identifiers, used by Alembic.
revision = '001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create initial database schema"""
    bind = op.get_bind()
    is_clickhouse = bind.dialect.name in ('clickhouse', 'clickhousedb')

    # Detect engines and types for ClickHouse vs PostgreSQL
    if is_clickhouse:
        try:
            from clickhouse_sqlalchemy import engines as ch_engines
            from clickhouse_sqlalchemy.types import Array as CHArray, Int32 as CHInt32
            array_type = CHArray(CHInt32)
        except ImportError:
            ch_engines = None
            array_type = sa.String()
            
        uuid_type = sa.String()
        json_type = sa.Text()
        datetime_type = sa.DateTime()  # ClickHouse doesn't support timezone=True in DDL compilation
        
        # ClickHouse does not support creating custom ENUM types using enum.create()
        # and standard columns use String for enums
        source_type_enum = sa.String()
        batch_status_enum = sa.String()
        load_type_enum = sa.String()
        load_status_enum = sa.String()
        validation_status_enum = sa.String()
        validation_type_enum = sa.String()
    else:
        uuid_type = sa.UUID(as_uuid=True)
        json_type = postgresql.JSONB(astext_type=sa.Text())
        array_type = sa.ARRAY(sa.Integer())
        datetime_type = sa.DateTime(timezone=True)

    def string_type(length=None):
        return sa.String() if is_clickhouse else sa.String(length)

    # Create schemas/databases
    if is_clickhouse:
        op.execute('CREATE DATABASE IF NOT EXISTS staging_meta')
        op.execute('CREATE DATABASE IF NOT EXISTS staging_data') 
        op.execute('CREATE DATABASE IF NOT EXISTS production')
    else:
        op.execute('CREATE SCHEMA IF NOT EXISTS staging_meta')
        op.execute('CREATE SCHEMA IF NOT EXISTS staging_data') 
        op.execute('CREATE SCHEMA IF NOT EXISTS production')
        op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # Create custom ENUM types in PostgreSQL
    if not is_clickhouse:
        source_type_enum = postgresql.ENUM(
            'file', 'api', 'database', 'stream', 'ftp', 'sftp', 's3', 'manual',
            name='sourcetype',
            schema='staging_meta'
        )
        source_type_enum.create(op.get_bind())
        
        batch_status_enum = postgresql.ENUM(
            'PENDING', 'UPLOADED', 'PROCESSING', 'VALIDATING', 'TRANSFORMING', 
            'LOADING', 'COMPLETED', 'FAILED', 'CANCELLED', 'RETRY',
            name='batchstatus',
            schema='staging_meta'
        )
        batch_status_enum.create(op.get_bind())
        
        load_type_enum = postgresql.ENUM(
            'FULL', 'INCREMENTAL', 'DELTA', 'APPEND', 'REPLACE', 'MERGE',
            'FILE_UPLOAD', 'API_SYNC', 'STREAM',
            name='loadtype',
            schema='staging_meta'
        )
        load_type_enum.create(op.get_bind())
        
        load_status_enum = postgresql.ENUM(
            'IN_PROGRESS', 'COMPLETED', 'FAILED', 'CANCELLED', 'PARTIALLY_COMPLETED',
            name='loadstatus',
            schema='staging_meta'
        )
        load_status_enum.create(op.get_bind())
        
        validation_status_enum = postgresql.ENUM(
            'PENDING', 'PASSED', 'FAILED', 'WARNING', 'ERROR', 'CRITICAL',
            name='validationstatus',
            schema='staging_meta'
        )
        validation_status_enum.create(op.get_bind())
        
        validation_type_enum = postgresql.ENUM(
            'completeness', 'uniqueness', 'data_type', 'range', 'pattern',
            'business_rule', 'referential_integrity', 'custom', 'format', 'consistency',
            name='validationtype',
            schema='staging_meta'
        )
        validation_type_enum.create(op.get_bind())

    # Create data_sources table
    data_sources_cols = [
        sa.Column('source_id', sa.Integer(), autoincrement=True, nullable=False, comment='Unique identifier for the data source'),
        sa.Column('source_name', string_type(100), nullable=False, comment='Unique name for the data source'),
        sa.Column('source_type', source_type_enum, nullable=False, comment='Type of data source'),
        sa.Column('description', sa.Text(), nullable=True, comment='Description of the data source'),
        sa.Column('connection_config', json_type, nullable=True, comment='JSON configuration for connection parameters'),
        sa.Column('validation_rules', json_type, nullable=True, comment='JSON configuration for data validation rules'),
        sa.Column('transformation_rules', json_type, nullable=True, comment='JSON configuration for data transformation rules'),
        sa.Column('target_table', string_type(100), nullable=True, comment='Target table name for processed data'),
        sa.Column('target_schema', string_type(50), nullable=True, comment='Target schema for processed data'),
        sa.Column('is_active', sa.Boolean(), nullable=False, comment='Whether this data source is active'),
        sa.Column('schedule_expression', string_type(100), nullable=True, comment='Cron expression for scheduled processing'),
        sa.Column('last_processed_at', datetime_type, nullable=True, comment='Timestamp of last successful processing'),
        sa.Column('next_scheduled_at', datetime_type, nullable=True, comment='Timestamp of next scheduled processing'),
        sa.Column('max_retries', sa.Integer(), nullable=False, comment='Maximum number of retry attempts'),
        sa.Column('timeout_seconds', sa.Integer(), nullable=False, comment='Timeout for processing in seconds'),
        sa.Column('batch_size', sa.Integer(), nullable=True, comment='Batch size for processing large datasets'),
        sa.Column('tags', json_type, nullable=True, comment='Tags for categorizing data sources'),
        sa.Column('owner', string_type(100), nullable=True, comment='Owner or responsible person for this data source'),
        sa.Column('created_at', datetime_type, server_default=sa.text('now()'), nullable=False, comment='Timestamp when record was created'),
        sa.Column('updated_at', datetime_type, server_default=sa.text('now()'), nullable=False, comment='Timestamp when record was last updated'),
    ]
    
    data_sources_kwargs = {'schema': 'staging_meta'}
    if is_clickhouse:
        if ch_engines:
            data_sources_cols.append(ch_engines.MergeTree(order_by=('source_id',)))
    else:
        data_sources_cols.append(sa.PrimaryKeyConstraint('source_id', name='pk_data_sources'))
        data_sources_cols.append(sa.UniqueConstraint('source_name', name='uq_data_sources_source_name'))
        
    op.create_table('data_sources', *data_sources_cols, **data_sources_kwargs)
    
    # Create indexes for data_sources
    if not is_clickhouse:
        op.create_index('ix_data_sources_type_active', 'data_sources', ['source_type', 'is_active'], schema='staging_meta')
        op.create_index('ix_data_sources_schedule', 'data_sources', ['next_scheduled_at', 'is_active'], schema='staging_meta')
        op.create_index('ix_data_sources_owner', 'data_sources', ['owner'], schema='staging_meta')

    # Create source_load_summary table
    summary_cols = [
        sa.Column('source_name', string_type(100), primary_key=not is_clickhouse, nullable=False, comment='Name of the data source'),
        sa.Column('last_successful_load', datetime_type, nullable=True, comment='Timestamp of last successful load'),
        sa.Column('last_attempted_load', datetime_type, nullable=True, comment='Timestamp of last attempted load'),
        sa.Column('total_successful_loads', sa.Integer(), nullable=False, default=0, comment='Total number of successful loads'),
        sa.Column('total_failed_loads', sa.Integer(), nullable=False, default=0, comment='Total number of failed loads'),
        sa.Column('average_load_duration_seconds', sa.Integer(), nullable=True, comment='Average duration of successful loads in seconds'),
        sa.Column('last_record_count', sa.Integer(), nullable=False, default=0, comment='Number of records in last successful load'),
        sa.Column('last_data_quality_score', sa.Numeric(5, 2), nullable=True, comment='Data quality score from last successful load'),
        sa.Column('current_status', string_type(20), nullable=True, comment='Current status of the data source'),
        sa.Column('next_scheduled_load', datetime_type, nullable=True, comment='Timestamp of next scheduled load'),
        sa.Column('load_frequency', string_type(50), nullable=True, comment='Frequency of scheduled loads (DAILY, WEEKLY, etc.)'),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True, comment='Whether this data source is active'),
        sa.Column('created_at', datetime_type, server_default=sa.text('now()'), nullable=False, comment='Timestamp when record was created'),
        sa.Column('updated_at', datetime_type, server_default=sa.text('now()'), nullable=False, comment='Timestamp when record was last updated'),
    ]
    summary_kwargs = {'schema': 'staging_meta'}
    if is_clickhouse:
        if ch_engines:
            summary_cols.append(ch_engines.MergeTree(order_by=('source_name',)))
            
    op.create_table('source_load_summary', *summary_cols, **summary_kwargs)

    # Create batch_control table
    batch_status_default = BatchStatus.PENDING.value if hasattr(BatchStatus.PENDING, 'value') else BatchStatus.PENDING
    batch_control_cols = [
        sa.Column('batch_id', uuid_type, primary_key=not is_clickhouse, default=uuid.uuid4, comment='Unique identifier for the batch'),
        sa.Column('source_name', string_type(100), nullable=False, comment='Name of the data source'),
        sa.Column('source_type', string_type(50), nullable=False, comment='Type of data source'),
        sa.Column('file_name', string_type(255), nullable=True, comment='Original filename for file-based sources'),
        sa.Column('file_path', string_type(500), nullable=True, comment='Full path to the uploaded/processed file'),
        sa.Column('file_size', sa.BigInteger(), nullable=True, comment='File size in bytes'),
        sa.Column('records_count', sa.Integer(), nullable=True, comment='Total number of records in the batch'),
        sa.Column('status', batch_status_enum, nullable=False, default=batch_status_default, comment='Current status of the batch processing'),
        sa.Column('started_at', datetime_type, nullable=True, comment='Timestamp when processing started'),
        sa.Column('completed_at', datetime_type, nullable=True, comment='Timestamp when processing completed'),
        sa.Column('error_message', sa.Text(), nullable=True, comment='Error message if processing failed'),
        sa.Column('retry_count', sa.Integer(), nullable=False, default=0, comment='Number of retry attempts'),
        sa.Column('max_retries', sa.Integer(), nullable=False, default=3, comment='Maximum number of retry attempts allowed'),
        sa.Column('metadata', json_type, nullable=True, comment='Additional metadata about the batch'),
        sa.Column('processing_config', json_type, nullable=True, comment='Configuration used for processing this batch'),
        sa.Column('created_at', datetime_type, server_default=sa.text('now()'), nullable=False, comment='Timestamp when record was created'),
        sa.Column('updated_at', datetime_type, server_default=sa.text('now()'), nullable=False, comment='Timestamp when record was last updated'),
    ]
    batch_kwargs = {'schema': 'staging_meta'}
    if is_clickhouse:
        if ch_engines:
            batch_control_cols.append(ch_engines.MergeTree(order_by=('batch_id',)))
            
    op.create_table('batch_control', *batch_control_cols, **batch_kwargs)

    # Create load_history table
    load_status_default = LoadStatus.IN_PROGRESS.value if hasattr(LoadStatus.IN_PROGRESS, 'value') else LoadStatus.IN_PROGRESS
    load_history_cols = [
        sa.Column('load_id', uuid_type, primary_key=not is_clickhouse, default=uuid.uuid4, comment='Unique identifier for the load operation'),
        sa.Column('batch_id', uuid_type, nullable=False, comment='Reference to the batch that initiated this load'),
        sa.Column('source_name', string_type(100), nullable=False, comment='Name of the data source'),
        sa.Column('load_type', load_type_enum, nullable=False, comment='Type of load operation'),
        sa.Column('target_table', string_type(100), nullable=True, comment='Target table name where data was loaded'),
        sa.Column('target_schema', string_type(50), nullable=True, comment='Target schema where data was loaded'),
        sa.Column('records_inserted', sa.Integer(), nullable=False, default=0, comment='Number of records inserted'),
        sa.Column('records_updated', sa.Integer(), nullable=False, default=0, comment='Number of records updated'),
        sa.Column('records_deleted', sa.Integer(), nullable=False, default=0, comment='Number of records deleted'),
        sa.Column('records_rejected', sa.Integer(), nullable=False, default=0, comment='Number of records rejected due to validation failures'),
        sa.Column('data_quality_score', sa.Numeric(5, 2), nullable=True, comment='Overall data quality score (0-100)'),
        sa.Column('validation_passed', sa.Integer(), nullable=False, default=0, comment='Number of validation rules that passed'),
        sa.Column('validation_failed', sa.Integer(), nullable=False, default=0, comment='Number of validation rules that failed'),
        sa.Column('load_start_time', datetime_type, nullable=False, comment='Timestamp when load operation started'),
        sa.Column('load_end_time', datetime_type, nullable=True, comment='Timestamp when load operation ended'),
        sa.Column('duration_seconds', sa.Integer(), nullable=True, comment='Total duration of load operation in seconds'),
        sa.Column('status', load_status_enum, nullable=False, default=load_status_default, comment='Status of the load operation'),
        sa.Column('error_details', sa.Text(), nullable=True, comment='Detailed error message if load failed'),
        sa.Column('rows_per_second', sa.Numeric(10, 2), nullable=True, comment='Processing rate in rows per second'),
        sa.Column('mb_per_second', sa.Numeric(10, 2), nullable=True, comment='Processing rate in megabytes per second'),
        sa.Column('metadata', json_type, nullable=True, comment='Additional metadata about the load operation'),
        sa.Column('load_config', json_type, nullable=True, comment='Configuration used for this specific load'),
    ]
    load_kwargs = {'schema': 'staging_meta'}
    if is_clickhouse:
        if ch_engines:
            load_history_cols.append(ch_engines.MergeTree(order_by=('load_id',)))
            
    op.create_table('load_history', *load_history_cols, **load_kwargs)

    # Create validation_logs table
    validation_logs_cols = [
        sa.Column('log_id', uuid_type, primary_key=not is_clickhouse, default=uuid.uuid4, comment='Unique identifier for the validation log entry'),
        sa.Column('batch_id', uuid_type, nullable=False, comment='Reference to the batch being validated'),
        sa.Column('validation_type', validation_type_enum, nullable=False, comment='Type of validation performed'),
        sa.Column('validation_rule', string_type(100), nullable=False, comment='Name or identifier of the validation rule'), 
        sa.Column('column_name', string_type(100), nullable=True, comment='Column being validated (if applicable)'),
        sa.Column('status', validation_status_enum, nullable=False, comment='Result status of the validation'),
        sa.Column('error_count', sa.Integer(), nullable=False, default=0, comment='Number of records that failed this validation'),
        sa.Column('total_count', sa.Integer(), nullable=False, default=0, comment='Total number of records checked by this validation'),
        sa.Column('success_rate', sa.Numeric(5, 2), nullable=True, comment='Success rate as percentage (0-100)'),
        sa.Column('message', sa.Text(), nullable=True, comment='Detailed message about the validation result'),
        sa.Column('failed_rows', array_type, nullable=True, comment='Array of row indices that failed validation'),
        sa.Column('rule_config', json_type, nullable=True, comment='Configuration parameters used for this validation rule'),
        sa.Column('error_details', json_type, nullable=True, comment='Detailed error information for failed validations'),
        sa.Column('execution_time_ms', sa.Integer(), nullable=True, comment='Time taken to execute this validation in milliseconds'),
    ]
    validation_kwargs = {'schema': 'staging_meta'}
    if is_clickhouse:
        if ch_engines:
            validation_logs_cols.append(ch_engines.MergeTree(order_by=('log_id',)))
            
    op.create_table('validation_logs', *validation_logs_cols, **validation_kwargs)

    # Create template_staging table
    validation_status_default = ValidationStatus.PENDING.value if hasattr(ValidationStatus.PENDING, 'value') else ValidationStatus.PENDING
    template_staging_cols = [
        sa.Column('staging_id', uuid_type, primary_key=not is_clickhouse, default=uuid.uuid4, comment='Unique identifier for the staging record'),
        sa.Column('batch_id', uuid_type, nullable=False, comment='Reference to the batch this record belongs to'),
        sa.Column('source_row_number', sa.Integer(), nullable=True, comment='Original row number from source data'),
        sa.Column('raw_data', json_type, nullable=True, comment='Raw data as received from source'),
        sa.Column('processed_data', json_type, nullable=True, comment='Data after transformations and cleaning'),
        sa.Column('validation_status', validation_status_enum, nullable=False, default=validation_status_default, comment='Overall validation status for this record'),  
        sa.Column('validation_errors', json_type, nullable=True, comment='Detailed validation errors for this record'),
        sa.Column('data_quality_score', sa.Numeric(5, 2), nullable=True, comment='Data quality score for this specific record (0-100)'),
        sa.Column('processed_at', datetime_type, nullable=True, comment='Timestamp when record was processed'),
        sa.Column('loaded_at', datetime_type, nullable=True, comment='Timestamp when record was loaded to target'),
        sa.Column('created_at', datetime_type, server_default=sa.text('now()'), nullable=False, comment='Timestamp when record was created'),
        sa.Column('updated_at', datetime_type, server_default=sa.text('now()'), nullable=False, comment='Timestamp when record was last updated'),
    ]
    staging_kwargs = {'schema': 'staging_data'}
    if is_clickhouse:
        if ch_engines:
            template_staging_cols.append(ch_engines.MergeTree(order_by=('staging_id',)))
            
    op.create_table('template_staging', *template_staging_cols, **staging_kwargs)


def downgrade() -> None:
    """Drop database schema"""
    bind = op.get_bind()
    is_clickhouse = bind.dialect.name in ('clickhouse', 'clickhousedb')

    # Drop tables
    op.drop_table('template_staging', schema='staging_data')
    op.drop_table('validation_logs', schema='staging_meta')
    op.drop_table('load_history', schema='staging_meta')
    op.drop_table('batch_control', schema='staging_meta')
    op.drop_table('source_load_summary', schema='staging_meta')
    op.drop_table('data_sources', schema='staging_meta')

    # Drop schemas/databases
    if is_clickhouse:
        op.execute('DROP DATABASE IF EXISTS staging_meta')
        op.execute('DROP DATABASE IF EXISTS staging_data')
        op.execute('DROP DATABASE IF EXISTS production')
    else:
        op.execute('DROP SCHEMA IF EXISTS staging_meta')
        op.execute('DROP SCHEMA IF EXISTS staging_data')
        op.execute('DROP SCHEMA IF EXISTS production')
        
        # Drop custom enums in postgres
        op.execute('DROP TYPE IF EXISTS staging_meta.sourcetype')
        op.execute('DROP TYPE IF EXISTS staging_meta.batchstatus')
        op.execute('DROP TYPE IF EXISTS staging_meta.loadtype')
        op.execute('DROP TYPE IF EXISTS staging_meta.loadstatus')
        op.execute('DROP TYPE IF EXISTS staging_meta.validationstatus')
        op.execute('DROP TYPE IF EXISTS staging_meta.validationtype')

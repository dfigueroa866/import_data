# alembic/versions/001_initial_schema.py
"""Initial schema creation

Revision ID: 001_initial_schema
Revises: 
Create Date: 2025-07-22 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create initial database schema"""
    
    # Create schemas
    op.execute('CREATE SCHEMA IF NOT EXISTS staging_meta')
    op.execute('CREATE SCHEMA IF NOT EXISTS staging_data') 
    op.execute('CREATE SCHEMA IF NOT EXISTS production')
    
    # Install UUID extension if not exists
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    
    # Create custom types
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
    op.create_table(
        'data_sources',
        sa.Column('source_id', sa.Integer(), autoincrement=True, nullable=False, comment='Unique identifier for the data source'),
        sa.Column('source_name', sa.String(100), nullable=False, comment='Unique name for the data source'),
        sa.Column('source_type', source_type_enum, nullable=False, comment='Type of data source'),
        sa.Column('description', sa.Text(), nullable=True, comment='Description of the data source'),
        sa.Column('connection_config', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='JSON configuration for connection parameters'),
        sa.Column('validation_rules', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='JSON configuration for data validation rules'),
        sa.Column('transformation_rules', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='JSON configuration for data transformation rules'),
        sa.Column('target_table', sa.String(100), nullable=True, comment='Target table name for processed data'),
        sa.Column('target_schema', sa.String(50), nullable=True, comment='Target schema for processed data'),
        sa.Column('is_active', sa.Boolean(), nullable=False, comment='Whether this data source is active'),
        sa.Column('schedule_expression', sa.String(100), nullable=True, comment='Cron expression for scheduled processing'),
        sa.Column('last_processed_at', sa.DateTime(timezone=True), nullable=True, comment='Timestamp of last successful processing'),
        sa.Column('next_scheduled_at', sa.DateTime(timezone=True), nullable=True, comment='Timestamp of next scheduled processing'),
        sa.Column('max_retries', sa.Integer(), nullable=False, comment='Maximum number of retry attempts'),
        sa.Column('timeout_seconds', sa.Integer(), nullable=False, comment='Timeout for processing in seconds'),
        sa.Column('batch_size', sa.Integer(), nullable=True, comment='Batch size for processing large datasets'),
        sa.Column('tags', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Tags for categorizing data sources'),
        sa.Column('owner', sa.String(100), nullable=True, comment='Owner or responsible person for this data source'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Timestamp when record was created'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Timestamp when record was last updated'),
        sa.PrimaryKeyConstraint('source_id', name='pk_data_sources'),
        sa.UniqueConstraint('source_name', name='uq_data_sources_source_name'),
        schema='staging_meta'
    )
    
    # Create indexes for data_sources
    op.create_index('ix_data_sources_type_active', 'data_sources', ['source_type', 'is_active'], schema='staging_meta')
    op.create_index('ix_data_sources_schedule', 'data_sources', ['next_scheduled_at', 'is_active'], schema='staging_meta')
    op.create_index('ix_data_sources_owner', 'data_sources', ['owner'], schema='staging_meta')

    # Create source_load_summary table
    op.create_table(
        'source_load_summary',
        sa.Column('source_name', sa.String(100), primary_key=True, nullable=False, comment='Name of the data source'),
        sa.Column('last_successful_load', sa.DateTime(timezone=True), nullable=True, comment='Timestamp of last successful load'),
        sa.Column('last_attempted_load', sa.DateTime(timezone=True), nullable=True, comment='Timestamp of last attempted load'),
        sa.Column('total_successful_loads', sa.Integer(), nullable=False, default=0, comment='Total number of successful loads'),
        sa.Column('total_failed_loads', sa.Integer(), nullable=False, default=0, comment='Total number of failed loads'),
        sa.Column('average_load_duration_seconds', sa.Integer(), nullable=True, comment='Average duration of successful loads in seconds'),
        sa.Column('last_record_count', sa.Integer(), nullable=False, default=0, comment='Number of records in last successful load'),
        sa.Column('last_data_quality_score', sa.Numeric(5, 2), nullable=True, comment='Data quality score from last successful load'),
        sa.Column('current_status', sa.String(20), nullable=True, comment='Current status of the data source'),
        sa.Column('next_scheduled_load', sa.DateTime(timezone=True), nullable=True, comment='Timestamp of next scheduled load'),
        sa.Column('load_frequency', sa.String(50), nullable=True, comment='Frequency of scheduled loads (DAILY, WEEKLY, etc.)'),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True, comment='Whether this data source is active'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Timestamp when record was created'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Timestamp when record was last updated'),
        schema='staging_meta'
    )

    # Create batch_control table
    op.create_table(
        'batch_control',
        sa.Column('batch_id', sa.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, comment='Unique identifier for the batch'),
        sa.Column('source_name', sa.String(100), nullable=False, comment='Name of the data source'),
        sa.Column('source_type', sa.String(50), nullable=False, comment='Type of data source'),
        sa.Column('file_name', sa.String(255), nullable=True, comment='Original filename for file-based sources'),
        sa.Column('file_path', sa.String(500), nullable=True, comment='Full path to the uploaded/processed file'),
        sa.Column('file_size', sa.BigInteger(), nullable=True, comment='File size in bytes'),
        sa.Column('records_count', sa.Integer(), nullable=True, comment='Total number of records in the batch'),
        sa.Column('status', batch_status_enum, nullable=False, default=BatchStatus.PENDING, comment='Current status of the batch processing'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True, comment='Timestamp when processing started'),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True, comment='Timestamp when processing completed'),
        sa.Column('error_message', sa.Text(), nullable=True, comment='Error message if processing failed'),
        sa.Column('retry_count', sa.Integer(), nullable=False, default=0, comment='Number of retry attempts'),
        sa.Column('max_retries', sa.Integer(), nullable=False, default=3, comment='Maximum number of retry attempts allowed'),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Additional metadata about the batch'),
        sa.Column('processing_config', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Configuration used for processing this batch'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Timestamp when record was created'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Timestamp when record was last updated'),
        schema='staging_meta'
    )

    # Create load_history table
    op.create_table(
        'load_history',
        sa.Column('load_id', sa.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, comment='Unique identifier for the load operation'),
        sa.Column('batch_id', sa.UUID(as_uuid=True), nullable=False, comment='Reference to the batch that initiated this load'),
        sa.Column('source_name', sa.String(100), nullable=False, comment='Name of the data source'),
        sa.Column('load_type', load_type_enum, nullable=False, comment='Type of load operation'),
        sa.Column('target_table', sa.String(100), nullable=True, comment='Target table name where data was loaded'),
        sa.Column('target_schema', sa.String(50), nullable=True, comment='Target schema where data was loaded'),
        sa.Column('records_inserted', sa.Integer(), nullable=False, default=0, comment='Number of records inserted'),
        sa.Column('records_updated', sa.Integer(), nullable=False, default=0, comment='Number of records updated'),
        sa.Column('records_deleted', sa.Integer(), nullable=False, default=0, comment='Number of records deleted'),
        sa.Column('records_rejected', sa.Integer(), nullable=False, default=0, comment='Number of records rejected due to validation failures'),
        sa.Column('data_quality_score', sa.Numeric(5, 2), nullable=True, comment='Overall data quality score (0-100)'),
        sa.Column('validation_passed', sa.Integer(), nullable=False, default=0, comment='Number of validation rules that passed'),
        sa.Column('validation_failed', sa.Integer(), nullable=False, default=0, comment='Number of validation rules that failed'),
        sa.Column('load_start_time', sa.DateTime(timezone=True), nullable=False, comment='Timestamp when load operation started'),
        sa.Column('load_end_time', sa.DateTime(timezone=True), nullable=True, comment='Timestamp when load operation ended'),
        sa.Column('duration_seconds', sa.Integer(), nullable=True, comment='Total duration of load operation in seconds'),
        sa.Column('status', load_status_enum, nullable=False, default=LoadStatus.IN_PROGRESS, comment='Status of the load operation'),
        sa.Column('error_details', sa.Text(), nullable=True, comment='Detailed error message if load failed'),
        sa.Column('rows_per_second', sa.Numeric(10, 2), nullable=True, comment='Processing rate in rows per second'),
        sa.Column('mb_per_second', sa.Numeric(10, 2), nullable=True, comment='Processing rate in megabytes per second'),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Additional metadata about the load operation'),
        sa.Column('load_config', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Configuration used for this specific load'),
        schema='staging_meta'
    )

    # Create validation_logs table
    op.create_table(
        'validation_logs',
        sa.Column('log_id', sa.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, comment='Unique identifier for the validation log entry'),
        sa.Column('batch_id', sa.UUID(as_uuid=True), nullable=False, comment='Reference to the batch being validated'),
        sa.Column('validation_type', validation_type_enum, nullable=False, comment='Type of validation performed'),
        sa.Column('validation_rule', sa.String(100), nullable=False, comment='Name or identifier of the validation rule'), 
        sa.Column('column_name', sa.String(100), nullable=True, comment='Column being validated (if applicable)'),
        sa.Column('status', validation_status_enum, nullable=False, comment='Result status of the validation'),
        sa.Column('error_count', sa.Integer(), nullable=False, default=0, comment='Number of records that failed this validation'),
        sa.Column('total_count', sa.Integer(), nullable=False, default=0, comment='Total number of records checked by this validation'),
        sa.Column('success_rate', sa.Numeric(5, 2), nullable=True, comment='Success rate as percentage (0-100)'),
        sa.Column('message', sa.Text(), nullable=True, comment='Detailed message about the validation result'),
        sa.Column('failed_rows', sa.ARRAY(sa.Integer()), nullable=True, comment='Array of row indices that failed validation'),
        sa.Column('rule_config', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Configuration parameters used for this validation rule'),
        sa.Column('error_details', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Detailed error information for failed validations'),
        sa.Column('execution_time_ms', sa.Integer(), nullable=True, comment='Time taken to execute this validation in milliseconds'),
        schema='staging_meta'
    )

    # Create template_staging table
    op.create_table(
        'template_staging',
        sa.Column('staging_id', sa.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, comment='Unique identifier for the staging record'),
        sa.Column('batch_id', sa.UUID(as_uuid=True), nullable=False, comment='Reference to the batch this record belongs to'),
        sa.Column('source_row_number', sa.Integer(), nullable=True, comment='Original row number from source data'),
        sa.Column('raw_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Raw data as received from source'),
        sa.Column('processed_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Data after transformations and cleaning'),
        sa.Column('validation_status', validation_status_enum, nullable=False, default=ValidationStatus.PENDING, comment='Overall validation status for this record'),  
        sa.Column('validation_errors', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Detailed validation errors for this record'),
        sa.Column('data_quality_score', sa.Numeric(5, 2), nullable=True, comment='Data quality score for this specific record (0-100)'),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True, comment='Timestamp when record was processed'),
        sa.Column('loaded_at', sa.DateTime(timezone=True), nullable=True, comment='Timestamp when record was loaded to target'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Timestamp when record was created'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Timestamp when record was last updated'),
        schema='staging_data'
    )

    # Create indexes for template_staging   

# src/data_staging/models/data_source.py
"""
SQLAlchemy models for data sources configuration
"""

from sqlalchemy import (
    Column, Integer, String, Boolean, Text, DateTime, 
    JSON, Enum, Index, UniqueConstraint, ForeignKey,
    Numeric, Float, BigInteger, Date
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum
import uuid

from .base import StagingMetaBase, Base, func

class SourceType(enum.Enum):
    """Enumeration for data source types"""
    FILE = "file"
    API = "api"
    DATABASE = "database"
    STREAM = "stream"
    FTP = "ftp"
    SFTP = "sftp"
    S3 = "s3"
    MANUAL = "manual"

class DataSource(Base):
    """
    Model for data source configurations
    
    Stores configuration for different types of data sources including
    files, APIs, databases, and streaming sources.
    """
    
    __tablename__ = 'data_sources'
    __table_args__ = {'schema': 'staging_meta'}
    
    # Primary key
    source_id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Unique identifier for the data source"
    )
    
    # Basic information
    source_name = Column(
        String(100),
        nullable=False,
        unique=True,
        comment="Unique name for the data source"
    )
    
    source_type = Column(
        String(50),  # character varying(50) in actual table
        nullable=False,
        comment="Type of data source (file, api, database, etc.)"
    )
    
    description = Column(
        Text,
        nullable=True,
        comment="Description of the data source"
    )
    
    # Configuration
    connection_config = Column(
        JSONB,
        nullable=True,
        comment="JSON configuration for connection parameters"
    )
    
    validation_rules = Column(
        JSONB,
        nullable=True,
        comment="JSON configuration for data validation rules"
    )
    
    transformation_rules = Column(
        JSONB,
        nullable=True,
        comment="JSON configuration for data transformation rules"
    )
    
    # Target information
    target_table = Column(
        String(100),
        nullable=True,
        comment="Target table name for processed data"
    )
    
    target_schema = Column(
        String(50),
        nullable=True,
        default='staging_data',
        comment="Target schema for processed data"
    )
    
    # Status and control
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether this data source is active"
    )
    
    # Schedule information
    schedule_expression = Column(
        Text,  # text in actual table
        nullable=True,
        comment="Cron expression for scheduled processing"
    )
    
    last_processed_at = Column(
        Date,  # date in actual table
        nullable=True,
        comment="Timestamp of last successful processing"
    )
    
    next_scheduled_at = Column(
        Date,  # date in actual table
        nullable=True,
        comment="Timestamp of next scheduled processing"
    )
    
    # Processing configuration
    max_retries = Column(
        Numeric,  # numeric in actual table
        nullable=True,  # nullable in actual table
        comment="Maximum number of retry attempts"
    )
    
    timeout_seconds = Column(
        Float,  # real in actual table
        nullable=True,  # nullable in actual table
        comment="Timeout for processing in seconds"
    )
    
    batch_size = Column(
        BigInteger,  # bigint in actual table
        nullable=True,
        comment="Batch size for processing large datasets"
    )
    
    # Metadata
    tags = Column(
        Text,  # text in actual table
        nullable=True,
        comment="Tags for categorizing data sources"
    )
    
    owner = Column(
        Text,  # text in actual table
        nullable=True,
        comment="Owner or responsible person for this data source"
    )
    
    # Relationships
    batches = relationship(
        "BatchControl",
        back_populates="data_source",
        cascade="all, delete-orphan"
    )
    
    load_summaries = relationship(
        "SourceLoadSummary",
        back_populates="data_source",
        cascade="all, delete-orphan"
    )
    
    # Indexes
    __table_args__ = (
        Index('ix_data_sources_type_active', 'source_type', 'is_active'),
        Index('ix_data_sources_schedule', 'next_scheduled_at', 'is_active'),
        Index('ix_data_sources_owner', 'owner'),
        {'schema': 'staging_meta'}
    )
    
    def __repr__(self):
        return f"<DataSource(id={self.source_id}, name='{self.source_name}', type='{self.source_type}')>"
    
    @property
    def is_scheduled(self) -> bool:
        """Check if this data source has scheduling enabled"""
        return self.schedule_expression is not None
    
    @property
    def connection_string(self) -> str:
        """Get connection string from configuration"""
        if self.connection_config and 'connection_string' in self.connection_config:
            return self.connection_config['connection_string']
        return ""
    
    def get_validation_rule(self, rule_name: str, default=None):
        """Get specific validation rule"""
        if self.validation_rules and rule_name in self.validation_rules:
            return self.validation_rules[rule_name]
        return default
    
    def get_transformation_rule(self, rule_name: str, default=None):
        """Get specific transformation rule"""
        if self.transformation_rules and rule_name in self.transformation_rules:
            return self.transformation_rules[rule_name]
        return default
    
    def update_last_processed(self):
        """Update the last processed timestamp"""
        self.last_processed_at = func.now()
    
    def to_config_dict(self) -> dict:
        """Convert to configuration dictionary for processing"""
        return {
            'source_id': self.source_id,
            'source_name': self.source_name,
            'source_type': self.source_type,
            'connection_config': self.connection_config or {},
            'validation_rules': self.validation_rules or {},
            'transformation_rules': self.transformation_rules or {},
            'target_table': self.target_table,
            'target_schema': self.target_schema,
            'batch_size': self.batch_size,
            'max_retries': self.max_retries,
            'timeout_seconds': self.timeout_seconds
        }
    
    def to_dict(self, exclude_fields: list = None) -> dict:
        """Convert model instance to dictionary"""
        exclude_fields = exclude_fields or []
        result = {}
        
        for column in self.__table__.columns:
            if column.name not in exclude_fields:
                value = getattr(self, column.name)
                result[column.name] = value
                
        return result
    
    def update_from_dict(self, data: dict, exclude_fields: list = None):
        """Update model instance from dictionary"""
        exclude_fields = exclude_fields or ['source_id', 'created_at']
        
        for key, value in data.items():
            if hasattr(self, key) and key not in exclude_fields:
                setattr(self, key, value)

class SourceLoadSummary(StagingMetaBase):
    """
    Model for tracking load summary statistics per data source
    """
    
    __tablename__ = 'source_load_summary'
    
    # Primary key (using source_name as PK as per original schema)
    source_name = Column(
        String(100),
        ForeignKey('staging_meta.data_sources.source_name', ondelete='CASCADE'),
        primary_key=True,
        comment="Name of the data source"
    )
    
    # Load statistics
    last_successful_load = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of last successful load"
    )
    
    last_attempted_load = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of last attempted load"
    )
    
    total_successful_loads = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Total number of successful loads"
    )
    
    total_failed_loads = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Total number of failed loads"
    )
    
    average_load_duration_seconds = Column(
        Integer,
        nullable=True,
        comment="Average duration of successful loads in seconds"
    )
    
    last_record_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of records in last successful load"
    )
    
    last_data_quality_score = Column(
        "last_data_quality_score",
        nullable=True,
        comment="Data quality score from last successful load"
    )
    
    # Status and scheduling
    current_status = Column(
        String(20),
        nullable=True,
        comment="Current status of the data source"
    )
    
    next_scheduled_load = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of next scheduled load"
    )
    
    load_frequency = Column(
        String(50),
        nullable=True,
        comment="Frequency of scheduled loads (DAILY, WEEKLY, etc.)"
    )
    
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether this data source is active"
    )
    
    # Relationship
    data_source = relationship(
        "DataSource",
        back_populates="load_summaries"
    )
    
    # Indexes
    __table_args__ = (
        Index('ix_source_summary_status', 'current_status', 'is_active'),
        Index('ix_source_summary_schedule', 'next_scheduled_load', 'is_active'),
        {'schema': 'staging_meta'}
    )
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage"""
        total_loads = self.total_successful_loads + self.total_failed_loads
        if total_loads == 0:
            return 0.0
        return (self.total_successful_loads / total_loads) * 100
    
    @property
    def is_overdue(self) -> bool:
        """Check if the next scheduled load is overdue"""
        if not self.next_scheduled_load:
            return False
        
        from datetime import datetime
        return datetime.now() > self.next_scheduled_load
    
    def update_success_stats(self, duration_seconds: int, record_count: int, quality_score: float = None):
        """Update statistics after a successful load"""
        self.total_successful_loads += 1
        self.last_successful_load = func.now()
        self.last_attempted_load = func.now()
        self.last_record_count = record_count
        self.current_status = 'COMPLETED'
        
        if quality_score is not None:
            self.last_data_quality_score = quality_score
        
        # Update average duration
        if self.average_load_duration_seconds:
            # Weighted average with previous loads
            total_loads = self.total_successful_loads
            self.average_load_duration_seconds = int(
                ((self.average_load_duration_seconds * (total_loads - 1)) + duration_seconds) / total_loads
            )
        else:
            self.average_load_duration_seconds = duration_seconds
    
    def update_failure_stats(self):
        """Update statistics after a failed load"""
        self.total_failed_loads += 1
        self.last_attempted_load = func.now()
        self.current_status = 'FAILED'
# src/data_staging/models/load_history.py
"""
SQLAlchemy models for load history tracking
"""

from sqlalchemy import (
    Column, Integer, String, DateTime, Text, ForeignKey,
    Index, Enum, Numeric
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum
import uuid

from .base import StagingMetaBase, Base, func

class LoadType(enum.Enum):
    """Enumeration for load types"""
    FULL = "FULL"
    INCREMENTAL = "INCREMENTAL"
    DELTA = "DELTA"
    APPEND = "APPEND"
    REPLACE = "REPLACE"
    MERGE = "MERGE"
    FILE_UPLOAD = "FILE_UPLOAD"
    API_SYNC = "API_SYNC"
    STREAM = "STREAM"

class LoadStatus(enum.Enum):
    """Enumeration for load status"""
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"

class LoadHistory(StagingMetaBase):
    """
    Model for tracking detailed load history and statistics
    
    This table maintains a comprehensive history of all data loads,
    including performance metrics, data quality scores, and error details.
    """
    
    __tablename__ = 'load_history'
    
    # Primary key
    load_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for the load operation"
    )
    
    # Foreign key to batch
    batch_id = Column(
        UUID(as_uuid=True),
        ForeignKey('staging_meta.batch_control.batch_id', ondelete='CASCADE'),
        nullable=False,
        comment="Reference to the batch that initiated this load"
    )
    
    # Source information
    source_name = Column(
        String(100),
        nullable=False,
        comment="Name of the data source"
    )
    
    load_type = Column(
        Enum(LoadType),
        nullable=False,
        comment="Type of load operation"
    )
    
    # Target information
    target_table = Column(
        String(100),
        nullable=True,
        comment="Target table name where data was loaded"
    )
    
    target_schema = Column(
        String(50),
        nullable=True,
        default='staging_data',
        comment="Target schema where data was loaded"
    )
    
    # Record statistics
    records_inserted = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of records inserted"
    )
    
    records_updated = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of records updated"
    )
    
    records_deleted = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of records deleted"
    )
    
    records_rejected = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of records rejected due to validation failures"
    )
    
    # Data quality metrics
    data_quality_score = Column(
        Numeric(5, 2),
        nullable=True,
        comment="Overall data quality score (0-100)"
    )
    
    validation_passed = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of validation rules that passed"
    )
    
    validation_failed = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of validation rules that failed"
    )
    
    # Timing information
    load_start_time = Column(
        DateTime(timezone=True),
        nullable=False,
        comment="Timestamp when load operation started"
    )
    
    load_end_time = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when load operation ended"
    )
    
    duration_seconds = Column(
        Integer,
        nullable=True,
        comment="Total duration of load operation in seconds"
    )
    
    # Status and error handling
    status = Column(
        Enum(LoadStatus),
        nullable=False,
        default=LoadStatus.IN_PROGRESS,
        comment="Status of the load operation"
    )
    
    error_details = Column(
        Text,
        nullable=True,
        comment="Detailed error message if load failed"
    )
    
    # Performance metrics
    rows_per_second = Column(
        Numeric(10, 2),
        nullable=True,
        comment="Processing rate in rows per second"
    )
    
    mb_per_second = Column(
        Numeric(10, 2),
        nullable=True,
        comment="Processing rate in megabytes per second"
    )
    
    # Additional metadata
    load_metadata = Column(
        JSONB,
        nullable=True,
        comment="Additional metadata about the load operation"
    )
    
    load_config = Column(
        JSONB,
        nullable=True,
        comment="Configuration used for this specific load"
    )
    
    # Relationships
    batch = relationship(
        "BatchControl",
        back_populates="load_history"
    )
    
    # Indexes
    __table_args__ = (
        Index('ix_load_history_source_time', 'source_name', 'load_start_time'),
        Index('ix_load_history_batch_id', 'batch_id'),
        Index('ix_load_history_status', 'status'),
        Index('ix_load_history_start_time', 'load_start_time'),
        {'schema': 'staging_meta'}
    )
    
    def __repr__(self):
        return f"<LoadHistory(id={self.load_id}, source='{self.source_name}', status='{self.status}')>"
    
    @property
    def total_records_processed(self) -> int:
        """Calculate total records processed"""
        return self.records_inserted + self.records_updated + self.records_deleted
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage"""
        total_processed = self.total_records_processed
        if total_processed == 0:
            return 100.0
        return ((total_processed - self.records_rejected) / total_processed) * 100
    
    @property
    def is_completed(self) -> bool:
        """Check if load is completed"""
        return self.status in [LoadStatus.COMPLETED, LoadStatus.FAILED, 
                              LoadStatus.CANCELLED, LoadStatus.PARTIALLY_COMPLETED]
    
    @property
    def validation_success_rate(self) -> float:
        """Calculate validation success rate"""
        total_validations = self.validation_passed + self.validation_failed
        if total_validations == 0:
            return 100.0
        return (self.validation_passed / total_validations) * 100
    
    def start_load(self, load_type: LoadType, target_table: str = None, target_schema: str = None):
        """Initialize load operation"""
        self.load_type = load_type
        self.load_start_time = func.now()
        self.status = LoadStatus.IN_PROGRESS
        if target_table:
            self.target_table = target_table
        if target_schema:
            self.target_schema = target_schema
    
    def complete_successfully(self):
        """Mark load as completed successfully"""
        self.status = LoadStatus.COMPLETED
        self.load_end_time = func.now()
        self._calculate_metrics()
    
    def complete_partially(self, error_details: str = None):
        """Mark load as partially completed"""
        self.status = LoadStatus.PARTIALLY_COMPLETED
        self.load_end_time = func.now()
        if error_details:
            self.error_details = error_details
        self._calculate_metrics()
    
    def fail_with_error(self, error_details: str):
        """Mark load as failed with error details"""
        self.status = LoadStatus.FAILED
        self.load_end_time = func.now()
        self.error_details = error_details
        self._calculate_metrics()
    
    def cancel(self):
        """Cancel the load operation"""
        self.status = LoadStatus.CANCELLED
        self.load_end_time = func.now()
        self._calculate_metrics()
    
    def update_record_counts(self, inserted: int = 0, updated: int = 0, 
                           deleted: int = 0, rejected: int = 0):
        """Update record processing counts"""
        self.records_inserted = inserted
        self.records_updated = updated
        self.records_deleted = deleted
        self.records_rejected = rejected
    
    def update_validation_counts(self, passed: int = 0, failed: int = 0):
        """Update validation counts"""
        self.validation_passed = passed
        self.validation_failed = failed
    
    def set_data_quality_score(self, score: float):
        """Set the data quality score"""
        self.data_quality_score = max(0, min(100, score))  # Clamp between 0 and 100
    
    def _calculate_metrics(self):
        """Calculate performance metrics"""
        if self.load_start_time and self.load_end_time:
            # Calculate duration
            duration = self.load_end_time - self.load_start_time
            self.duration_seconds = int(duration.total_seconds())
            
            # Calculate processing rates
            if self.duration_seconds > 0:
                total_records = self.total_records_processed
                if total_records > 0:
                    self.rows_per_second = total_records / self.duration_seconds
                
                # Estimate MB/s based on average record size (rough estimate)
                if total_records > 0:
                    # Assume average record size of 1KB for calculation
                    estimated_mb = (total_records * 1024) / (1024 * 1024)
                    self.mb_per_second = estimated_mb / self.duration_seconds
    
    def add_metadata(self, key: str, value):
        """Add metadata key-value pair"""
        if self.load_metadata is None:
            self.load_metadata = {}
        self.load_metadata[key] = value
    
    def get_metadata(self, key: str, default=None):
        """Get metadata value by key"""
        if self.load_metadata and key in self.load_metadata:
            return self.load_metadata[key]
        return default
    
    def to_summary_dict(self) -> dict:
        """Convert to summary dictionary for reporting"""
        return {
            'load_id': str(self.load_id),
            'batch_id': str(self.batch_id),
            'source_name': self.source_name,
            'load_type': self.load_type.value,
            'target_table': self.target_table,
            'status': self.status.value,
            'records_processed': self.total_records_processed,
            'records_inserted': self.records_inserted,
            'records_updated': self.records_updated,
            'records_deleted': self.records_deleted,
            'records_rejected': self.records_rejected,
            'success_rate': round(self.success_rate, 2),
            'data_quality_score': float(self.data_quality_score) if self.data_quality_score else None,
            'validation_success_rate': round(self.validation_success_rate, 2),
            'duration_seconds': self.duration_seconds,
            'rows_per_second': float(self.rows_per_second) if self.rows_per_second else None,
            'load_start_time': self.load_start_time.isoformat() if self.load_start_time else None,
            'load_end_time': self.load_end_time.isoformat() if self.load_end_time else None,
            'error_details': self.error_details
        }
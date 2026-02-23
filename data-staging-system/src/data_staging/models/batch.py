# src/data_staging/models/batch.py
"""
SQLAlchemy models for batch processing control
"""

from sqlalchemy import (
    Column, Integer, String, BigInteger, DateTime, Text,
    ForeignKey, Index, Enum
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum
import uuid

from .base import StagingMetaBase

class BatchStatus(enum.Enum):
    """Enumeration for batch processing status"""
    PENDING = "PENDING"
    UPLOADED = "UPLOADED" 
    PROCESSING = "PROCESSING"
    VALIDATING = "VALIDATING"
    TRANSFORMING = "TRANSFORMING"
    LOADING = "LOADING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    RETRY = "RETRY"

class BatchControl(StagingMetaBase):
    """
    Model for controlling and tracking batch processing jobs
    
    This table serves as the central control point for all data processing
    batches, tracking their lifecycle from upload to completion.
    """
    
    __tablename__ = 'batch_control'
    
    # Primary key
    batch_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for the batch"
    )
    
    # Source information
    source_name = Column(
        String(100),
        ForeignKey('staging_meta.data_sources.source_name', ondelete='CASCADE'),
        nullable=False,
        comment="Name of the data source"
    )
    
    source_type = Column(
        String(50),
        nullable=False,
        comment="Type of data source (file, api, database, etc.)"
    )
    
    # File information (for file-based sources)
    file_name = Column(
        String(255),
        nullable=True,
        comment="Original filename for file-based sources"
    )
    
    file_path = Column(
        String(500),
        nullable=True,
        comment="Full path to the uploaded/processed file"
    )
    
    file_size = Column(
        BigInteger,
        nullable=True,
        comment="File size in bytes"
    )
    
    # Processing information
    records_count = Column(
        Integer,
        nullable=True,
        comment="Total number of records in the batch"
    )
    
    status = Column(
        Enum(BatchStatus),
        nullable=False,
        default=BatchStatus.PENDING,
        comment="Current status of the batch processing"
    )
    
    # Timing information
    started_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when processing started"
    )
    
    completed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when processing completed"
    )
    
    # Error handling
    error_message = Column(
        Text,
        nullable=True,
        comment="Error message if processing failed"
    )
    
    retry_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of retry attempts"
    )
    
    max_retries = Column(
        Integer,
        nullable=False,
        default=3,
        comment="Maximum number of retry attempts allowed"
    )
    
    # Metadata and configuration
    batch_metadata = Column(
        JSONB,
        nullable=True,
        comment="Additional metadata about the batch"
    )
    
    processing_config = Column(
        JSONB,
        nullable=True,
        comment="Configuration used for processing this batch"
    )
    
    # User information
    created_by = Column(
        String(100),
        nullable=True,
        comment="User who created this batch"
    )
    
    # Relationships
    data_source = relationship(
        "DataSource",
        back_populates="batches"
    )
    
    load_history = relationship(
        "LoadHistory",
        back_populates="batch",
        cascade="all, delete-orphan"
    )
    
    validation_logs = relationship(
        "ValidationLog",
        back_populates="batch",
        cascade="all, delete-orphan"
    )
    
    staging_records = relationship(
        "StagingRecord",
        back_populates="batch",
        cascade="all, delete-orphan"
    )
    
    # Indexes
    __table_args__ = (
        Index('ix_batch_control_source_created', 'source_name', 'created_at'),
        Index('ix_batch_control_status', 'status'),
        Index('ix_batch_control_created', 'created_at'),
        Index('ix_batch_control_started', 'started_at'),
        {'schema': 'staging_meta'}
    )
    
    def __repr__(self):
        return f"<BatchControl(id={self.batch_id}, source='{self.source_name}', status='{self.status}')>"
    
    @property
    def duration_seconds(self) -> int:
        """Calculate processing duration in seconds"""
        if self.started_at and self.completed_at:
            return int((self.completed_at - self.started_at).total_seconds())
        return 0
    
    @property
    def is_completed(self) -> bool:
        """Check if batch processing is completed (success or failure)"""
        return self.status in [BatchStatus.COMPLETED, BatchStatus.FAILED, BatchStatus.CANCELLED]
    
    @property
    def is_processing(self) -> bool:
        """Check if batch is currently being processed"""
        return self.status in [BatchStatus.PROCESSING, BatchStatus.VALIDATING, 
                              BatchStatus.TRANSFORMING, BatchStatus.LOADING]
    
    @property
    def can_retry(self) -> bool:
        """Check if batch can be retried"""
        return (self.status == BatchStatus.FAILED and 
                self.retry_count < self.max_retries)
    
    def start_processing(self):
        """Mark batch as started processing"""
        self.status = BatchStatus.PROCESSING
        self.started_at = func.now()
    
    def complete_successfully(self):
        """Mark batch as completed successfully"""
        self.status = BatchStatus.COMPLETED
        self.completed_at = func.now()
    
    def fail_with_error(self, error_message: str):
        """Mark batch as failed with error message"""
        self.status = BatchStatus.FAILED
        self.error_message = error_message
        self.completed_at = func.now()
    
    def retry(self):
        """Increment retry count and reset for retry"""
        if self.can_retry:
            self.retry_count += 1
            self.status = BatchStatus.RETRY
            self.error_message = None
            self.started_at = None
            self.completed_at = None
            return True
        return False
    
    def cancel(self):
        """Cancel the batch processing"""
        self.status = BatchStatus.CANCELLED
        self.completed_at = func.now()
    
    def update_records_count(self, count: int):
        """Update the records count"""
        self.records_count = count
    
    def add_metadata(self, key: str, value):
        """Add metadata key-value pair"""
        if self.batch_metadata is None:
            self.batch_metadata = {}
        self.batch_metadata[key] = value
    
    def get_metadata(self, key: str, default=None):
        """Get metadata value by key"""
        if self.batch_metadata and key in self.batch_metadata:
            return self.batch_metadata[key]
        return default
    
    def to_status_dict(self) -> dict:
        """Convert to status dictionary for API responses"""
        return {
            'batch_id': str(self.batch_id),
            'source_name': self.source_name,
            'source_type': self.source_type,
            'file_name': self.file_name,
            'file_size': self.file_size,
            'records_count': self.records_count,
            'status': self.status.value,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'duration_seconds': self.duration_seconds,
            'error_message': self.error_message,
            'retry_count': self.retry_count,
            'max_retries': self.max_retries,
            'can_retry': self.can_retry,
            'metadata': self.metadata
        }
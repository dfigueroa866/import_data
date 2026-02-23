# src/data_staging/models/validation.py
"""
SQLAlchemy models for data validation tracking
"""

from sqlalchemy import (
    Column, Integer, String, Text, ForeignKey, Index, Enum
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum
import uuid

from .base import StagingMetaBase, StagingDataBase

class ValidationStatus(enum.Enum):
    """Enumeration for validation status"""
    PENDING = "PENDING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

class ValidationType(enum.Enum):
    """Enumeration for validation types"""
    COMPLETENESS = "completeness"
    UNIQUENESS = "uniqueness"
    DATA_TYPE = "data_type"
    RANGE = "range"
    PATTERN = "pattern"
    BUSINESS_RULE = "business_rule"
    REFERENTIAL_INTEGRITY = "referential_integrity"
    CUSTOM = "custom"
    FORMAT = "format"
    CONSISTENCY = "consistency"

class ValidationLog(StagingMetaBase):
    """
    Model for tracking validation results and logs
    
    This table stores detailed validation results for each batch,
    including which rules were applied and their outcomes.
    """
    
    __tablename__ = 'validation_logs'
    
    # Primary key
    log_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for the validation log entry"
    )
    
    # Foreign key to batch
    batch_id = Column(
        UUID(as_uuid=True),
        ForeignKey('staging_meta.batch_control.batch_id', ondelete='CASCADE'),
        nullable=False,
        comment="Reference to the batch being validated"
    )
    
    # Validation details
    validation_type = Column(
        Enum(ValidationType),
        nullable=False,
        comment="Type of validation performed"
    )
    
    validation_rule = Column(
        String(100),
        nullable=False,
        comment="Name or identifier of the validation rule"
    )
    
    column_name = Column(
        String(100),
        nullable=True,
        comment="Column being validated (if applicable)"
    )
    
    # Results
    status = Column(
        Enum(ValidationStatus),
        nullable=False,
        comment="Result status of the validation"
    )
    
    error_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of records that failed this validation"
    )
    
    total_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Total number of records checked by this validation"
    )
    
    success_rate = Column(
        "success_rate",
        nullable=True,
        comment="Success rate as percentage (0-100)"
    )
    
    # Detailed information
    message = Column(
        Text,
        nullable=True,
        comment="Detailed message about the validation result"
    )
    
    failed_rows = Column(
        ARRAY(Integer),
        nullable=True,
        comment="Array of row indices that failed validation"
    )
    
    rule_config = Column(
        JSONB,
        nullable=True,
        comment="Configuration parameters used for this validation rule"
    )
    
    error_details = Column(
        JSONB,
        nullable=True,
        comment="Detailed error information for failed validations"
    )
    
    # Performance tracking
    execution_time_ms = Column(
        Integer,
        nullable=True,
        comment="Time taken to execute this validation in milliseconds"
    )
    
    # Relationships
    batch = relationship(
        "BatchControl",
        back_populates="validation_logs"
    )
    
    # Indexes
    __table_args__ = (
        Index('ix_validation_logs_batch_id', 'batch_id'),
        Index('ix_validation_logs_created', 'created_at'),
        Index('ix_validation_logs_status', 'status'),
        Index('ix_validation_logs_type', 'validation_type'),
        {'schema': 'staging_meta'}
    )
    
    def __repr__(self):
        return f"<ValidationLog(id={self.log_id}, rule='{self.validation_rule}', status='{self.status}')>"
    
    @property
    def passed(self) -> bool:
        """Check if validation passed"""
        return self.status == ValidationStatus.PASSED
    
    @property
    def failed_percentage(self) -> float:
        """Calculate percentage of failed records"""
        if self.total_count == 0:
            return 0.0
        return (self.error_count / self.total_count) * 100
    
    def calculate_success_rate(self):
        """Calculate and update success rate"""
        if self.total_count > 0:
            self.success_rate = ((self.total_count - self.error_count) / self.total_count) * 100
        else:
            self.success_rate = 100.0
    
    def add_error_detail(self, key: str, value):
        """Add error detail key-value pair"""
        if self.error_details is None:
            self.error_details = {}
        self.error_details[key] = value
    
    def to_result_dict(self) -> dict:
        """Convert to result dictionary"""
        return {
            'log_id': str(self.log_id),
            'batch_id': str(self.batch_id),
            'validation_type': self.validation_type.value,
            'validation_rule': self.validation_rule,
            'column_name': self.column_name,
            'status': self.status.value,
            'passed': self.passed,
            'error_count': self.error_count,
            'total_count': self.total_count,
            'success_rate': float(self.success_rate) if self.success_rate else None,
            'failed_percentage': round(self.failed_percentage, 2),
            'message': self.message,
            'execution_time_ms': self.execution_time_ms,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class StagingRecord(StagingDataBase):
    """
    Base model for staging data records
    
    This serves as a template for staging tables that store raw and processed data
    """
    
    __tablename__ = 'template_staging'
    
    # Primary key
    staging_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for the staging record"
    )
    
    # Foreign key to batch
    batch_id = Column(
        UUID(as_uuid=True),
        ForeignKey('staging_meta.batch_control.batch_id', ondelete='CASCADE'),
        nullable=False,
        comment="Reference to the batch this record belongs to"
    )
    
    # Source information
    source_row_number = Column(
        Integer,
        nullable=True,
        comment="Original row number from source data"
    )
    
    # Data storage
    raw_data = Column(
        JSONB,
        nullable=True,
        comment="Raw data as received from source"
    )
    
    processed_data = Column(
        JSONB,
        nullable=True,
        comment="Data after transformations and cleaning"
    )
    
    # Validation status
    validation_status = Column(
        Enum(ValidationStatus),
        nullable=False,
        default=ValidationStatus.PENDING,
        comment="Overall validation status for this record"
    )
    
    validation_errors = Column(
        JSONB,
        nullable=True,
        comment="Detailed validation errors for this record"
    )
    
    data_quality_score = Column(
        "data_quality_score",
        nullable=True,
        comment="Data quality score for this specific record (0-100)"
    )
    
    # Processing timestamps
    processed_at = Column(
        "processed_at",
        nullable=True,
        comment="Timestamp when record was processed"
    )
    
    loaded_at = Column(
        "loaded_at",
        nullable=True,
        comment="Timestamp when record was loaded to target"
    )
    
    # Relationships
    batch = relationship(
        "BatchControl",
        back_populates="staging_records"
    )
    
    # Indexes
    __table_args__ = (
        Index('ix_staging_record_batch_id', 'batch_id'),
        Index('ix_staging_record_validation_status', 'validation_status'),
        Index('ix_staging_record_created', 'created_at'),
        {'schema': 'staging_data'}
    )
    
    def __repr__(self):
        return f"<StagingRecord(id={self.staging_id}, batch={self.batch_id}, status='{self.validation_status}')>"
    
    @property
    def is_valid(self) -> bool:
        """Check if record passed validation"""
        return self.validation_status == ValidationStatus.PASSED
    
    @property
    def has_errors(self) -> bool:
        """Check if record has validation errors"""
        return self.validation_status in [ValidationStatus.FAILED, ValidationStatus.ERROR, ValidationStatus.CRITICAL]
    
    def add_validation_error(self, field: str, error: str, severity: str = "error"):
        """Add a validation error for this record"""
        if self.validation_errors is None:
            self.validation_errors = {}
        
        if field not in self.validation_errors:
            self.validation_errors[field] = []
        
        self.validation_errors[field].append({
            'error': error,
            'severity': severity,
            'timestamp': func.now().isoformat()
        })
        
        # Update validation status based on severity
        if severity == "critical":
            self.validation_status = ValidationStatus.CRITICAL
        elif severity == "error" and self.validation_status != ValidationStatus.CRITICAL:
            self.validation_status = ValidationStatus.FAILED
        elif severity == "warning" and self.validation_status == ValidationStatus.PENDING:
            self.validation_status = ValidationStatus.WARNING
    
    def mark_as_processed(self, processed_data: dict = None):
        """Mark record as processed"""
        self.processed_at = func.now()
        if processed_data:
            self.processed_data = processed_data
    
    def mark_as_loaded(self):
        """Mark record as loaded to target"""
        self.loaded_at = func.now()
    
    def calculate_quality_score(self) -> float:
        """Calculate data quality score for this record"""
        if not self.validation_errors:
            return 100.0
        
        # Simple scoring: reduce score based on error severity
        score = 100.0
        for field_errors in self.validation_errors.values():
            for error in field_errors:
                severity = error.get('severity', 'error')
                if severity == 'critical':
                    score -= 25
                elif severity == 'error':
                    score -= 10
                elif severity == 'warning':
                    score -= 5
        
        self.data_quality_score = max(0, score)
        return self.data_quality_score
    
    def to_dict(self, include_data: bool = True) -> dict:
        """Convert to dictionary representation"""
        result = {
            'staging_id': str(self.staging_id),
            'batch_id': str(self.batch_id),
            'source_row_number': self.source_row_number,
            'validation_status': self.validation_status.value,
            'data_quality_score': float(self.data_quality_score) if self.data_quality_score else None,
            'is_valid': self.is_valid,
            'has_errors': self.has_errors,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'processed_at': self.processed_at.isoformat() if self.processed_at else None,
            'loaded_at': self.loaded_at.isoformat() if self.loaded_at else None
        }
        
        if include_data:
            result.update({
                'raw_data': self.raw_data,
                'processed_data': self.processed_data,
                'validation_errors': self.validation_errors
            })
        
        return result
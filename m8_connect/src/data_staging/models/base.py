# src/data_staging/models/base.py
"""
Base SQLAlchemy model with common functionality for all models
"""

from sqlalchemy import Column, DateTime, func, MetaData
from sqlalchemy.ext.declarative import declarative_base, declared_attr
from sqlalchemy.orm import declarative_base
from datetime import datetime
from typing import Any, Dict

# Define naming convention for constraints
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

metadata = MetaData(naming_convention=convention)
Base = declarative_base(metadata=metadata)

class TimestampMixin:
    """Mixin to add timestamp fields to models"""
    
    created_at = Column(
        DateTime(timezone=True), 
        server_default=func.now(),
        nullable=False,
        comment="Timestamp when record was created"
    )
    
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Timestamp when record was last updated"
    )

class BaseModel(Base, TimestampMixin):
    """Base model class with common functionality"""
    
    __abstract__ = True
    
    @declared_attr
    def __tablename__(cls):
        """Auto-generate table name from class name"""
        # Convert CamelCase to snake_case
        import re
        name = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', cls.__name__)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', name).lower()
    
    def to_dict(self, exclude_fields: list = None) -> Dict[str, Any]:
        """Convert model instance to dictionary"""
        exclude_fields = exclude_fields or []
        result = {}
        
        for column in self.__table__.columns:
            if column.name not in exclude_fields:
                value = getattr(self, column.name)
                if isinstance(value, datetime):
                    value = value.isoformat()
                result[column.name] = value
                
        return result
    
    def update_from_dict(self, data: Dict[str, Any], exclude_fields: list = None):
        """Update model instance from dictionary"""
        exclude_fields = exclude_fields or ['id', 'created_at', 'updated_at']
        
        for key, value in data.items():
            if hasattr(self, key) and key not in exclude_fields:
                setattr(self, key, value)
    
    def __repr__(self):
        """String representation of model instance"""
        return f"<{self.__class__.__name__}(id={getattr(self, 'id', 'N/A')})>"

class AuditMixin:
    """Mixin to add audit fields to models"""
    
    created_by = Column(
        'created_by',
        nullable=True,
        comment="User who created this record"
    )
    
    updated_by = Column(
        'updated_by', 
        nullable=True,
        comment="User who last updated this record"
    )
    
    version = Column(
        'version',
        default=1,
        nullable=False,
        comment="Version number for optimistic locking"
    )

# Helper for table args
def get_table_args(schema_name):
    return {'schema': schema_name}

# Schema-specific base classes
class StagingMetaBase(BaseModel):
    """Base class for staging_meta schema tables"""
    __abstract__ = True
    
    @declared_attr
    def __table_args__(cls):
        return get_table_args('staging_meta')

class StagingDataBase(BaseModel):
    """Base class for staging_data schema tables"""
    __abstract__ = True
    
    @declared_attr
    def __table_args__(cls):
        return get_table_args('staging_data')

class ProductionBase(BaseModel):
    """Base class for production schema tables"""
    __abstract__ = True
    
    @declared_attr
    def __table_args__(cls):
        return get_table_args('m8_schema')

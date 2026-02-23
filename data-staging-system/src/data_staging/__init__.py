"""
Data Staging System - Production-ready data processing platform

A comprehensive system for ingesting, validating, and processing data
from multiple sources with enterprise-grade quality controls.
"""

__version__ = "2.0.0"
__author__ = "Data Team"
__email__ = "data@company.com"

# Import models
from .models import (
    DataSource,
    LoadHistory,
    ValidationLog,
    BatchControl,
    LoadStatus,
    BatchStatus
)

# Import core components
# from .core.validators.data_validator import EnhancedDataValidator as DataValidator
# from .core.etl.engine import ETLEngine as StagingPipeline
from .database import get_database_manager

__all__ = [
    # Models
    "DataSource",
    "LoadHistory", 
    "ValidationLog",
    "BatchControl",
    "LoadStatus",
    "BatchStatus",
    # Core components
    # "DataValidator",
    # "StagingPipeline",
    "get_database_manager",
]

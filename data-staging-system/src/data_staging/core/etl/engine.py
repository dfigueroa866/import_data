# src/data_staging/core/etl/engine.py - Basic ETL Engine

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Callable, Union
from datetime import datetime
import logging
from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path

from data_staging.core.validators.data_validator import DataValidator
from data_staging.utils.file_handler import FileHandler
from data_staging.database import get_database_manager

logger = logging.getLogger(__name__)

class ETLStage(Enum):
    """ETL processing stages"""
    EXTRACT = "extract"
    TRANSFORM = "transform"
    VALIDATE = "validate"
    LOAD = "load"
    COMPLETE = "complete"
    FAILED = "failed"

@dataclass
class ETLResult:
    """Result of ETL processing"""
    batch_id: str
    stage: ETLStage
    success: bool
    message: str
    records_processed: int = 0
    records_loaded: int = 0
    records_rejected: int = 0
    validation_summary: Optional[Dict[str, Any]] = None
    execution_time: float = 0.0
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

class ETLEngine:
    """Main ETL processing engine"""
    
    def __init__(self):
        self.file_handler = FileHandler()
        self.validator = DataValidator()
        self.transformations = {}
        self._register_default_transformations()
    
    def _register_default_transformations(self):
        """Register default transformation functions"""
        self.transformations = {
            'clean_whitespace': self._clean_whitespace,
            'standardize_case': self._standardize_case,
            'parse_dates': self._parse_dates,
            'convert_types': self._convert_types,
            'handle_nulls': self._handle_nulls,
            'remove_duplicates': self._remove_duplicates,
            'validate_emails': self._validate_emails,
            'normalize_phone': self._normalize_phone,
            'calculate_derived': self._calculate_derived
        }
    
    def process_batch(
        self, 
        batch_id: str, 
        source_config: Dict[str, Any],
        validation_rules: Optional[Dict[str, Any]] = None,
        transformation_rules: Optional[List[Dict[str, Any]]] = None
    ) -> ETLResult:
        """
        Process a complete ETL batch
        
        Args:
            batch_id: Unique batch identifier
            source_config: Source configuration (file path, connection string, etc.)
            validation_rules: Data validation rules
            transformation_rules: Data transformation rules
        
        Returns:
            ETLResult with processing details
        """
        start_time = datetime.now()
        
        try:
            # Stage 1: Extract
            logger.info(f"Starting ETL processing for batch {batch_id}")
            extract_result = self._extract_data(batch_id, source_config)
            
            if not extract_result.success:
                return extract_result
            
            df = extract_result.metadata.get('dataframe')
            if df is None or df.empty:
                return ETLResult(
                    batch_id=batch_id,
                    stage=ETLStage.EXTRACT,
                    success=False,
                    message="No data extracted",
                    execution_time=(datetime.now() - start_time).total_seconds()
                )
            
            # Stage 2: Transform
            transform_result = self._transform_data(batch_id, df, transformation_rules)
            
            if not transform_result.success:
                return transform_result
            
            df = transform_result.metadata.get('dataframe', df)
            
            # Stage 3: Validate
            validation_result = self._validate_data(batch_id, df, validation_rules)
            
            if not validation_result.success:
                return validation_result
            
            # Stage 4: Load
            load_result = self._load_data(batch_id, df, source_config.get('target_table'))
            
            # Final result
            execution_time = (datetime.now() - start_time).total_seconds()
            
            return ETLResult(
                batch_id=batch_id,
                stage=ETLStage.COMPLETE,
                success=load_result.success,
                message="ETL processing completed successfully" if load_result.success else load_result.message,
                records_processed=len(df),
                records_loaded=load_result.records_loaded,
                records_rejected=load_result.records_rejected,
                validation_summary=validation_result.validation_summary,
                execution_time=execution_time,
                metadata={
                    'extract_time': extract_result.execution_time,
                    'transform_time': transform_result.execution_time,
                    'validation_time': validation_result.execution_time,
                    'load_time': load_result.execution_time,
                    'final_columns': list(df.columns),
                    'data_types': df.dtypes.astype(str).to_dict()
                }
            )
            
        except Exception as e:
            logger.error(f"ETL processing failed for batch {batch_id}: {e}")
            return ETLResult(
                batch_id=batch_id,
                stage=ETLStage.FAILED,
                success=False,
                message=f"ETL processing failed: {str(e)}",
                execution_time=(datetime.now() - start_time).total_seconds()
            )
    
    def _extract_data(self, batch_id: str, source_config: Dict[str, Any]) -> ETLResult:
        """Extract data from source"""
        start_time = datetime.now()
        
        try:
            source_type = source_config.get('type', 'file')
            
            if source_type == 'file':
                file_path = source_config.get('file_path')
                if not file_path:
                    return ETLResult(
                        batch_id=batch_id,
                        stage=ETLStage.EXTRACT,
                        success=False,
                        message="File path not specified"
                    )
                
                # Read file
                read_options = source_config.get('read_options', {})
                df = self.file_handler.read_file(file_path, **read_options)
                
                if df is None:
                    return ETLResult(
                        batch_id=batch_id,
                        stage=ETLStage.EXTRACT,
                        success=False,
                        message=f"Could not read file: {file_path}"
                    )
                
                return ETLResult(
                    batch_id=batch_id,
                    stage=ETLStage.EXTRACT,
                    success=True,
                    message=f"Successfully extracted {len(df)} records from file",
                    records_processed=len(df),
                    execution_time=(datetime.now() - start_time).total_seconds(),
                    metadata={'dataframe': df, 'source_path': file_path}
                )
            
            elif source_type == 'database':
                # Database extraction (placeholder)
                return ETLResult(
                    batch_id=batch_id,
                    stage=ETLStage.EXTRACT,
                    success=False,
                    message="Database extraction not yet implemented"
                )
            
            elif source_type == 'api':
                # API extraction (placeholder)
                return ETLResult(
                    batch_id=batch_id,
                    stage=ETLStage.EXTRACT,
                    success=False,
                    message="API extraction not yet implemented"
                )
            
            else:
                return ETLResult(
                    batch_id=batch_id,
                    stage=ETLStage.EXTRACT,
                    success=False,
                    message=f"Unsupported source type: {source_type}"
                )
                
        except Exception as e:
            return ETLResult(
                batch_id=batch_id,
                stage=ETLStage.EXTRACT,
                success=False,
                message=f"Extraction failed: {str(e)}",
                execution_time=(datetime.now() - start_time).total_seconds()
            )
    
    def _transform_data(
        self, 
        batch_id: str, 
        df: pd.DataFrame, 
        transformation_rules: Optional[List[Dict[str, Any]]]
    ) -> ETLResult:
        """Apply data transformations"""
        start_time = datetime.now()
        
        try:
            if not transformation_rules:
                # Apply default transformations
                transformation_rules = [
                    {'name': 'clean_whitespace'},
                    {'name': 'handle_nulls', 'strategy': 'keep'}
                ]
            
            original_count = len(df)
            
            for rule in transformation_rules:
                transformation_name = rule.get('name')
                
                if transformation_name not in self.transformations:
                    logger.warning(f"Unknown transformation: {transformation_name}")
                    continue
                
                try:
                    transformation_func = self.transformations[transformation_name]
                    df = transformation_func(df, rule)
                    logger.debug(f"Applied transformation: {transformation_name}")
                except Exception as e:
                    logger.error(f"Transformation {transformation_name} failed: {e}")
                    # Continue with other transformations
            
            return ETLResult(
                batch_id=batch_id,
                stage=ETLStage.TRANSFORM,
                success=True,
                message=f"Transformations applied successfully. Records: {original_count} -> {len(df)}",
                records_processed=len(df),
                execution_time=(datetime.now() - start_time).total_seconds(),
                metadata={'dataframe': df}
            )
            
        except Exception as e:
            return ETLResult(
                batch_id=batch_id,
                stage=ETLStage.TRANSFORM,
                success=False,
                message=f"Transformation failed: {str(e)}",
                execution_time=(datetime.now() - start_time).total_seconds()
            )
    
    def _validate_data(
        self, 
        batch_id: str, 
        df: pd.DataFrame, 
        validation_rules: Optional[Dict[str, Any]]
    ) -> ETLResult:
        """Validate transformed data"""
        start_time = datetime.now()
        
        try:
            validation_summary = self.validator.validate_dataframe(df, validation_rules)
            
            # Determine if validation passed based on critical errors
            critical_errors = validation_summary.get('critical_issues', 0)
            overall_score = validation_summary.get('score', 0.0)
            success = validation_summary.get('passed', True) and critical_errors == 0
            
            if success:
                message = f"Data validation passed. Quality score: {overall_score:.1f}%"
            else:
                message = f"Data validation failed. Critical errors: {critical_errors}"
            
            return ETLResult(
                batch_id=batch_id,
                stage=ETLStage.VALIDATE,
                success=success,
                message=message,
                records_processed=len(df),
                validation_summary=validation_summary,
                execution_time=(datetime.now() - start_time).total_seconds(),
                metadata={'dataframe': df}
            )
            
        except Exception as e:
            return ETLResult(
                batch_id=batch_id,
                stage=ETLStage.VALIDATE,
                success=False,
                message=f"Validation failed: {str(e)}",
                execution_time=(datetime.now() - start_time).total_seconds()
            )
    
    def _load_data(
        self, 
        batch_id: str, 
        df: pd.DataFrame, 
        target_table: Optional[str]
    ) -> ETLResult:
        """Load data to target destination"""
        start_time = datetime.now()
        
        try:
            if not target_table:
                # If no target table specified, create staging table
                target_table = f"staging_data.batch_{batch_id.replace('-', '_')}"
            
            # For now, just log the load operation
            # In a real implementation, you would save to the database
            logger.info(f"Loading {len(df)} records to {target_table}")
            
            # Simulate successful load
            records_loaded = len(df)
            records_rejected = 0
            
            return ETLResult(
                batch_id=batch_id,
                stage=ETLStage.LOAD,
                success=True,
                message=f"Successfully loaded {records_loaded} records to {target_table}",
                records_processed=len(df),
                records_loaded=records_loaded,
                records_rejected=records_rejected,
                execution_time=(datetime.now() - start_time).total_seconds(),
                metadata={'target_table': target_table}
            )
            
        except Exception as e:
            return ETLResult(
                batch_id=batch_id,
                stage=ETLStage.LOAD,
                success=False,
                message=f"Load failed: {str(e)}",
                execution_time=(datetime.now() - start_time).total_seconds()
            )
    
    # Transformation functions
    def _clean_whitespace(self, df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
        """Clean whitespace from string columns"""
        for col in df.select_dtypes(include=['object']).columns:
            df[col] = df[col].astype(str).str.strip()
        return df
    
    def _standardize_case(self, df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
        """Standardize text case"""
        case_type = config.get('case', 'lower')
        columns = config.get('columns', df.select_dtypes(include=['object']).columns)
        
        for col in columns:
            if col in df.columns:
                if case_type == 'lower':
                    df[col] = df[col].astype(str).str.lower()
                elif case_type == 'upper':
                    df[col] = df[col].astype(str).str.upper()
                elif case_type == 'title':
                    df[col] = df[col].astype(str).str.title()
        
        return df
    
    def _parse_dates(self, df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
        """Parse date columns"""
        date_columns = config.get('columns', [])
        date_format = config.get('format', None)
        
        for col in date_columns:
            if col in df.columns:
                try:
                    df[col] = pd.to_datetime(df[col], format=date_format, errors='coerce')
                except Exception as e:
                    logger.warning(f"Could not parse dates in column {col}: {e}")
        
        return df
    
    def _convert_types(self, df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
        """Convert data types"""
        type_mappings = config.get('mappings', {})
        
        for col, target_type in type_mappings.items():
            if col in df.columns:
                try:
                    if target_type == 'int':
                        df[col] = pd.to_numeric(df[col], errors='coerce').astype('Int64')
                    elif target_type == 'float':
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                    elif target_type == 'string':
                        df[col] = df[col].astype(str)
                    elif target_type == 'bool':
                        df[col] = df[col].astype(bool)
                except Exception as e:
                    logger.warning(f"Could not convert column {col} to {target_type}: {e}")
        
        return df
    
    def _handle_nulls(self, df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
        """Handle null values"""
        strategy = config.get('strategy', 'keep')
        
        if strategy == 'drop_rows':
            df = df.dropna()
        elif strategy == 'drop_columns':
            threshold = config.get('threshold', 0.5)
            null_ratio = df.isnull().sum() / len(df)
            cols_to_drop = null_ratio[null_ratio > threshold].index
            df = df.drop(columns=cols_to_drop)
        elif strategy == 'fill':
            fill_values = config.get('fill_values', {})
            for col, fill_value in fill_values.items():
                if col in df.columns:
                    df[col] = df[col].fillna(fill_value)
        
        return df
    
    def _remove_duplicates(self, df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
        """Remove duplicate rows"""
        subset = config.get('subset', None)
        keep = config.get('keep', 'first')
        
        return df.drop_duplicates(subset=subset, keep=keep)
    
    def _validate_emails(self, df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
        """Mark invalid emails"""
        email_columns = config.get('columns', [])
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        
        for col in email_columns:
            if col in df.columns:
                # Create a new column indicating email validity
                df[f'{col}_valid'] = df[col].astype(str).str.match(email_pattern, na=False)
        
        return df
    
    def _normalize_phone(self, df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
        """Normalize phone numbers"""
        phone_columns = config.get('columns', [])
        
        for col in phone_columns:
            if col in df.columns:
                # Remove non-digit characters
                df[col] = df[col].astype(str).str.replace(r'[^\d]', '', regex=True)
        
        return df
    
    def _calculate_derived(self, df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
        """Calculate derived columns"""
        calculations = config.get('calculations', [])
        
        for calc in calculations:
            target_col = calc.get('target_column')
            expression = calc.get('expression')
            
            if target_col and expression:
                try:
                    df[target_col] = df.eval(expression)
                except Exception as e:
                    logger.warning(f"Could not calculate derived column {target_col}: {e}")
        
        return df

class ETLJobManager:
    """Manager for ETL job execution and monitoring"""
    
    def __init__(self):
        self.engine = ETLEngine()
        self.active_jobs = {}
    
    def submit_job(
        self, 
        batch_id: str, 
        source_config: Dict[str, Any],
        validation_rules: Optional[Dict[str, Any]] = None,
        transformation_rules: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """Submit an ETL job for processing"""
        
        job_id = f"etl_{batch_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Store job info
        self.active_jobs[job_id] = {
            'batch_id': batch_id,
            'status': 'submitted',
            'submitted_at': datetime.now(),
            'source_config': source_config,
            'validation_rules': validation_rules,
            'transformation_rules': transformation_rules
        }
        
        logger.info(f"ETL job {job_id} submitted for batch {batch_id}")
        return job_id
    
    def execute_job(self, job_id: str) -> ETLResult:
        """Execute an ETL job"""
        
        if job_id not in self.active_jobs:
            return ETLResult(
                batch_id="unknown",
                stage=ETLStage.FAILED,
                success=False,
                message=f"Job {job_id} not found"
            )
        
        job_info = self.active_jobs[job_id]
        job_info['status'] = 'running'
        job_info['started_at'] = datetime.now()
        
        try:
            result = self.engine.process_batch(
                batch_id=job_info['batch_id'],
                source_config=job_info['source_config'],
                validation_rules=job_info['validation_rules'],
                transformation_rules=job_info['transformation_rules']
            )
            
            job_info['status'] = 'completed' if result.success else 'failed'
            job_info['completed_at'] = datetime.now()
            job_info['result'] = result
            
            return result
            
        except Exception as e:
            job_info['status'] = 'failed'
            job_info['completed_at'] = datetime.now()
            job_info['error'] = str(e)
            
            return ETLResult(
                batch_id=job_info['batch_id'],
                stage=ETLStage.FAILED,
                success=False,
                message=f"Job execution failed: {str(e)}"
            )
    
    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get status of an ETL job"""
        return self.active_jobs.get(job_id)
    
    def list_jobs(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List ETL jobs with optional status filter"""
        jobs = []
        
        for job_id, job_info in self.active_jobs.items():
            if status is None or job_info['status'] == status:
                job_summary = {
                    'job_id': job_id,
                    'batch_id': job_info['batch_id'],
                    'status': job_info['status'],
                    'submitted_at': job_info['submitted_at'].isoformat(),
                    'started_at': job_info.get('started_at', {}).isoformat() if job_info.get('started_at') else None,
                    'completed_at': job_info.get('completed_at', {}).isoformat() if job_info.get('completed_at') else None
                }
                
                if 'result' in job_info:
                    result = job_info['result']
                    job_summary.update({
                        'records_processed': result.records_processed,
                        'records_loaded': result.records_loaded,
                        'execution_time': result.execution_time,
                        'quality_score': result.validation_summary.overall_score if result.validation_summary else None
                    })
                
                jobs.append(job_summary)
        
        return jobs

# Global ETL job manager instance
etl_manager = ETLJobManager()
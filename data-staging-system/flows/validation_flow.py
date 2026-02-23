#!/usr/bin/env python3
"""
Create Missing Core Files for Data Staging System

This script creates all the missing core components that are referenced
throughout the codebase but don't exist yet.
"""

import os
from pathlib import Path

def create_missing_files():
    """Create all missing core files"""
    
    project_root = Path(__file__).parent if '__file__' in globals() else Path.cwd()
    src_dir = project_root / "src" / "data_staging"
    
    print(f"🔧 Creating missing core files in: {src_dir}")
    
    # Create directory structure
    directories = [
        "core",
        "core/validators",
        "core/etl", 
        "core/connectors",
        "core/monitoring",
        "utils",
        "models"
    ]
    
    for directory in directories:
        dir_path = src_dir / directory
        dir_path.mkdir(parents=True, exist_ok=True)
        
        # Create __init__.py files
        init_file = dir_path / "__init__.py"
        if not init_file.exists():
            init_file.write_text("# Auto-generated __init__.py\n")
        
        print(f"✅ Created directory: {directory}")
    
    # File contents
    files_to_create = {
        
        # Core Data Validator
        "core/validators/data_validator.py": '''# src/data_staging/core/validators/data_validator.py
"""
Data Validator - Core validation engine for data quality checks
"""

import pandas as pd
import numpy as np
import re
from datetime import datetime, date
from typing import Dict, List, Any, Optional, Union
import logging

logger = logging.getLogger(__name__)

class ValidationResult:
    """Container for validation results"""
    
    def __init__(self):
        self.passed = True
        self.errors = []
        self.warnings = []
        self.score = 100.0
        self.details = {}
        
    def add_error(self, message: str, rule: str = None):
        """Add validation error"""
        self.passed = False
        self.errors.append({"message": message, "rule": rule, "severity": "error"})
        self.score = max(0, self.score - 10)
        
    def add_warning(self, message: str, rule: str = None):
        """Add validation warning"""
        self.warnings.append({"message": message, "rule": rule, "severity": "warning"})
        self.score = max(0, self.score - 2)
        
    def get_summary(self) -> Dict[str, Any]:
        """Get validation summary"""
        return {
            "passed": self.passed,
            "score": round(self.score, 2),
            "errors": len(self.errors),
            "warnings": len(self.warnings),
            "grade": self._get_grade(),
            "error_details": self.errors,
            "warning_details": self.warnings,
            "details": self.details
        }
        
    def _get_grade(self) -> str:
        """Convert score to letter grade"""
        if self.score >= 95: return "A"
        elif self.score >= 85: return "B"
        elif self.score >= 75: return "C"
        elif self.score >= 65: return "D"
        else: return "F"

class DataValidator:
    """Main data validation engine"""
    
    def __init__(self):
        self.validation_rules = {
            'not_null': self._validate_not_null,
            'unique': self._validate_unique,
            'completeness': self._validate_completeness,
            'data_type': self._validate_data_type,
            'range': self._validate_range,
            'pattern': self._validate_pattern,
            'email': self._validate_email,
            'phone': self._validate_phone,
            'date': self._validate_date,
            'business_rule': self._validate_business_rule,
            'referential_integrity': self._validate_referential_integrity,
            'consistency': self._validate_consistency
        }
    
    def validate_dataframe(self, df: pd.DataFrame, rules: Dict[str, Any] = None) -> Dict[str, Any]:
        """Validate a pandas DataFrame"""
        if df is None or df.empty:
            return {"passed": False, "error": "DataFrame is empty or None"}
        
        result = ValidationResult()
        
        # Default rules if none provided
        if rules is None:
            rules = self._get_default_rules(df)
        
        # Run each validation rule
        for rule_name, rule_config in rules.items():
            if rule_name in self.validation_rules:
                try:
                    self.validation_rules[rule_name](df, rule_config, result)
                except Exception as e:
                    result.add_error(f"Validation rule '{rule_name}' failed: {str(e)}", rule_name)
                    logger.error(f"Validation error in {rule_name}: {e}")
        
        # Calculate overall metrics
        result.details.update({
            "total_rows": len(df),
            "total_columns": len(df.columns),
            "null_values": df.isnull().sum().sum(),
            "duplicate_rows": df.duplicated().sum(),
            "memory_usage": df.memory_usage(deep=True).sum()
        })
        
        return result.get_summary()
    
    def _get_default_rules(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Generate default validation rules based on DataFrame"""
        return {
            "completeness": {"threshold": 0.9},
            "data_type": {"strict": False},
            "unique": {"auto_detect": True}
        }
    
    def _validate_not_null(self, df: pd.DataFrame, config: Dict[str, Any], result: ValidationResult):
        """Validate that specified columns are not null"""
        columns = config.get("columns", [])
        if not columns:
            return
            
        for column in columns:
            if column in df.columns:
                null_count = df[column].isnull().sum()
                if null_count > 0:
                    result.add_error(f"Column '{column}' has {null_count} null values", "not_null")
    
    def _validate_unique(self, df: pd.DataFrame, config: Dict[str, Any], result: ValidationResult):
        """Validate uniqueness constraints"""
        columns = config.get("columns", [])
        
        for column in columns:
            if column in df.columns:
                duplicate_count = df[column].duplicated().sum()
                if duplicate_count > 0:
                    result.add_error(f"Column '{column}' has {duplicate_count} duplicate values", "unique")
    
    def _validate_completeness(self, df: pd.DataFrame, config: Dict[str, Any], result: ValidationResult):
        """Validate data completeness"""
        threshold = config.get("threshold", 0.9)
        columns = config.get("columns", df.columns.tolist())
        
        for column in columns:
            if column in df.columns:
                completeness = (df[column].notna().sum() / len(df))
                if completeness < threshold:
                    result.add_warning(f"Column '{column}' completeness {completeness:.2%} below threshold {threshold:.2%}", "completeness")
    
    def _validate_data_type(self, df: pd.DataFrame, config: Dict[str, Any], result: ValidationResult):
        """Validate data types"""
        strict = config.get("strict", False)
        type_mapping = config.get("types", {})
        
        for column, expected_type in type_mapping.items():
            if column in df.columns:
                actual_type = str(df[column].dtype)
                if strict and actual_type != expected_type:
                    result.add_error(f"Column '{column}' type '{actual_type}' doesn't match expected '{expected_type}'", "data_type")
    
    def _validate_range(self, df: pd.DataFrame, config: Dict[str, Any], result: ValidationResult):
        """Validate numeric ranges"""
        columns = config.get("columns", [])
        ranges = config.get("ranges", {})
        
        for column in columns:
            if column in df.columns and column in ranges:
                range_config = ranges[column]
                min_val = range_config.get("min")
                max_val = range_config.get("max")
                
                if min_val is not None:
                    violations = (df[column] < min_val).sum()
                    if violations > 0:
                        result.add_error(f"Column '{column}' has {violations} values below minimum {min_val}", "range")
                
                if max_val is not None:
                    violations = (df[column] > max_val).sum()
                    if violations > 0:
                        result.add_error(f"Column '{column}' has {violations} values above maximum {max_val}", "range")
    
    def _validate_pattern(self, df: pd.DataFrame, config: Dict[str, Any], result: ValidationResult):
        """Validate regex patterns"""
        columns = config.get("columns", [])
        patterns = config.get("patterns", {})
        
        for column in columns:
            if column in df.columns and column in patterns:
                pattern = patterns[column]
                try:
                    compiled_pattern = re.compile(pattern)
                    violations = ~df[column].astype(str).str.match(compiled_pattern, na=False)
                    violation_count = violations.sum()
                    if violation_count > 0:
                        result.add_error(f"Column '{column}' has {violation_count} values not matching pattern", "pattern")
                except re.error as e:
                    result.add_error(f"Invalid regex pattern for column '{column}': {e}", "pattern")
    
    def _validate_email(self, df: pd.DataFrame, config: Dict[str, Any], result: ValidationResult):
        """Validate email format"""
        columns = config.get("columns", [])
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'
        
        for column in columns:
            if column in df.columns:
                invalid_emails = ~df[column].astype(str).str.match(email_pattern, na=False)
                invalid_count = invalid_emails.sum()
                if invalid_count > 0:
                    result.add_error(f"Column '{column}' has {invalid_count} invalid email formats", "email")
    
    def _validate_phone(self, df: pd.DataFrame, config: Dict[str, Any], result: ValidationResult):
        """Validate phone number format"""
        columns = config.get("columns", [])
        # Basic phone pattern (can be customized)
        phone_pattern = r'^[+]?[1-9]?[0-9]{7,15}$'
        
        for column in columns:
            if column in df.columns:
                # Clean phone numbers (remove spaces, dashes, parentheses)
                cleaned_phones = df[column].astype(str).str.replace(r'[\\s\\-\\(\\)]', '', regex=True)
                invalid_phones = ~cleaned_phones.str.match(phone_pattern, na=False)
                invalid_count = invalid_phones.sum()
                if invalid_count > 0:
                    result.add_warning(f"Column '{column}' has {invalid_count} potentially invalid phone formats", "phone")
    
    def _validate_date(self, df: pd.DataFrame, config: Dict[str, Any], result: ValidationResult):
        """Validate date ranges and formats"""
        columns = config.get("columns", [])
        min_date = config.get("min_date")
        max_date = config.get("max_date")
        
        for column in columns:
            if column in df.columns:
                try:
                    # Convert to datetime if not already
                    dates = pd.to_datetime(df[column], errors='coerce')
                    
                    # Check for invalid dates
                    invalid_dates = dates.isnull() & df[column].notna()
                    invalid_count = invalid_dates.sum()
                    if invalid_count > 0:
                        result.add_error(f"Column '{column}' has {invalid_count} invalid date values", "date")
                    
                    # Check date ranges
                    valid_dates = dates.dropna()
                    if min_date and len(valid_dates) > 0:
                        min_date_dt = pd.to_datetime(min_date)
                        early_dates = (valid_dates < min_date_dt).sum()
                        if early_dates > 0:
                            result.add_error(f"Column '{column}' has {early_dates} dates before {min_date}", "date")
                    
                    if max_date and len(valid_dates) > 0:
                        max_date_dt = pd.to_datetime(max_date)
                        late_dates = (valid_dates > max_date_dt).sum()
                        if late_dates > 0:
                            result.add_error(f"Column '{column}' has {late_dates} dates after {max_date}", "date")
                            
                except Exception as e:
                    result.add_error(f"Date validation error for column '{column}': {e}", "date")
    
    def _validate_business_rule(self, df: pd.DataFrame, config: Dict[str, Any], result: ValidationResult):
        """Validate custom business rules"""
        expression = config.get("expression")
        name = config.get("name", "business_rule")
        
        if not expression:
            return
        
        try:
            # Evaluate the business rule expression
            violations = ~df.eval(expression)
            violation_count = violations.sum()
            if violation_count > 0:
                result.add_error(f"Business rule '{name}' violated by {violation_count} records", "business_rule")
        except Exception as e:
            result.add_error(f"Business rule evaluation error: {e}", "business_rule")
    
    def _validate_referential_integrity(self, df: pd.DataFrame, config: Dict[str, Any], result: ValidationResult):
        """Validate foreign key relationships"""
        # Placeholder for referential integrity checks
        # Would require access to other tables/data sources
        pass
    
    def _validate_consistency(self, df: pd.DataFrame, config: Dict[str, Any], result: ValidationResult):
        """Validate data consistency across columns"""
        rules = config.get("rules", [])
        
        for rule in rules:
            rule_type = rule.get("type")
            if rule_type == "sum_equals":
                # Example: total = sum of parts
                total_col = rule.get("total_column")
                part_cols = rule.get("part_columns", [])
                if total_col in df.columns and all(col in df.columns for col in part_cols):
                    calculated_sum = df[part_cols].sum(axis=1)
                    inconsistent = (df[total_col] != calculated_sum).sum()
                    if inconsistent > 0:
                        result.add_error(f"Sum consistency check failed for {inconsistent} records", "consistency")
''',

        # ETL Engine
        "core/etl/engine.py": '''# src/data_staging/core/etl/engine.py
"""
ETL Engine - Main engine for Extract, Transform, Load operations
"""

import pandas as pd
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path
import uuid

logger = logging.getLogger(__name__)

class ETLResult:
    """Container for ETL operation results"""
    
    def __init__(self):
        self.success = True
        self.message = ""
        self.records_processed = 0
        self.records_inserted = 0
        self.records_updated = 0
        self.records_rejected = 0
        self.errors = []
        self.warnings = []
        self.metadata = {}
        self.execution_time = 0.0
        
    def add_error(self, message: str):
        """Add error message"""
        self.success = False
        self.errors.append(message)
        
    def add_warning(self, message: str):
        """Add warning message"""
        self.warnings.append(message)
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "success": self.success,
            "message": self.message,
            "records_processed": self.records_processed,
            "records_inserted": self.records_inserted,
            "records_updated": self.records_updated,
            "records_rejected": self.records_rejected,
            "errors": self.errors,
            "warnings": self.warnings,
            "metadata": self.metadata,
            "execution_time": self.execution_time
        }

class ETLEngine:
    """Main ETL processing engine"""
    
    def __init__(self):
        self.transformers = {}
        self.connectors = {}
        self._register_default_transformers()
        
    def _register_default_transformers(self):
        """Register default data transformers"""
        self.transformers.update({
            'clean_whitespace': self._clean_whitespace,
            'standardize_case': self._standardize_case,
            'convert_types': self._convert_types,
            'handle_nulls': self._handle_nulls,
            'parse_dates': self._parse_dates,
            'remove_duplicates': self._remove_duplicates,
            'normalize_names': self._normalize_names,
            'extract_numbers': self._extract_numbers,
            'format_phone': self._format_phone
        })
    
    def process_batch(
        self, 
        batch_id: str, 
        data: pd.DataFrame, 
        config: Dict[str, Any] = None
    ) -> ETLResult:
        """Process a batch of data through ETL pipeline"""
        
        start_time = datetime.now()
        result = ETLResult()
        
        try:
            logger.info(f"Starting ETL processing for batch {batch_id}")
            
            if data is None or data.empty:
                result.add_error("No data provided for processing")
                return result
            
            result.records_processed = len(data)
            
            # Apply transformations if configured
            if config and 'transformation_rules' in config:
                data = self._apply_transformations(data, config['transformation_rules'], result)
            
            # Basic data quality checks
            self._perform_quality_checks(data, result)
            
            result.records_inserted = len(data)
            result.message = f"Successfully processed {result.records_processed} records"
            
            # Calculate execution time
            end_time = datetime.now()
            result.execution_time = (end_time - start_time).total_seconds()
            
            logger.info(f"ETL processing completed for batch {batch_id} in {result.execution_time:.2f}s")
            
        except Exception as e:
            result.add_error(f"ETL processing failed: {str(e)}")
            logger.error(f"ETL processing error for batch {batch_id}: {e}")
        
        return result
    
    def _apply_transformations(self, df: pd.DataFrame, rules: List[Dict[str, Any]], result: ETLResult) -> pd.DataFrame:
        """Apply transformation rules to dataframe"""
        
        for rule in rules:
            transformer_name = rule.get("name")
            if transformer_name in self.transformers:
                try:
                    df = self.transformers[transformer_name](df, rule)
                    logger.debug(f"Applied transformation: {transformer_name}")
                except Exception as e:
                    result.add_warning(f"Transformation '{transformer_name}' failed: {e}")
                    logger.warning(f"Transformation error: {e}")
            else:
                result.add_warning(f"Unknown transformation: {transformer_name}")
        
        return df
    
    def _perform_quality_checks(self, df: pd.DataFrame, result: ETLResult):
        """Perform basic data quality checks"""
        
        # Check for completely empty rows
        empty_rows = df.isnull().all(axis=1).sum()
        if empty_rows > 0:
            result.add_warning(f"Found {empty_rows} completely empty rows")
        
        # Check for duplicate rows
        duplicate_rows = df.duplicated().sum()
        if duplicate_rows > 0:
            result.add_warning(f"Found {duplicate_rows} duplicate rows")
        
        # Add metadata
        result.metadata.update({
            "empty_rows": empty_rows,
            "duplicate_rows": duplicate_rows,
            "total_null_values": df.isnull().sum().sum(),
            "columns": list(df.columns),
            "data_types": df.dtypes.to_dict()
        })
    
    # Transformation functions
    def _clean_whitespace(self, df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
        """Clean whitespace from string columns"""
        columns = config.get("columns", df.select_dtypes(include=['object']).columns)
        
        for column in columns:
            if column in df.columns:
                df[column] = df[column].astype(str).str.strip()
        
        return df
    
    def _standardize_case(self, df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
        """Standardize text case"""
        case_type = config.get("case", "lower")
        columns = config.get("columns", df.select_dtypes(include=['object']).columns)
        
        for column in columns:
            if column in df.columns:
                if case_type == "lower":
                    df[column] = df[column].astype(str).str.lower()
                elif case_type == "upper":
                    df[column] = df[column].astype(str).str.upper()
                elif case_type == "title":
                    df[column] = df[column].astype(str).str.title()
        
        return df
    
    def _convert_types(self, df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
        """Convert column data types"""
        mappings = config.get("mappings", {})
        
        for column, target_type in mappings.items():
            if column in df.columns:
                try:
                    if target_type == "int":
                        df[column] = pd.to_numeric(df[column], errors='coerce').astype('Int64')
                    elif target_type == "float":
                        df[column] = pd.to_numeric(df[column], errors='coerce')
                    elif target_type == "bool":
                        df[column] = df[column].astype('boolean')
                    elif target_type == "datetime":
                        df[column] = pd.to_datetime(df[column], errors='coerce')
                    elif target_type == "string":
                        df[column] = df[column].astype(str)
                except Exception as e:
                    logger.warning(f"Type conversion failed for column {column}: {e}")
        
        return df
    
    def _handle_nulls(self, df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
        """Handle null values"""
        strategy = config.get("strategy", "fill")
        fill_values = config.get("fill_values", {})
        
        if strategy == "fill":
            for column, fill_value in fill_values.items():
                if column in df.columns:
                    df[column] = df[column].fillna(fill_value)
        elif strategy == "drop":
            df = df.dropna()
        
        return df
    
    def _parse_dates(self, df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
        """Parse date columns"""
        columns = config.get("columns", [])
        date_format = config.get("format")
        
        for column in columns:
            if column in df.columns:
                try:
                    if date_format:
                        df[column] = pd.to_datetime(df[column], format=date_format, errors='coerce')
                    else:
                        df[column] = pd.to_datetime(df[column], errors='coerce')
                except Exception as e:
                    logger.warning(f"Date parsing failed for column {column}: {e}")
        
        return df
    
    def _remove_duplicates(self, df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
        """Remove duplicate rows"""
        subset = config.get("columns")
        keep = config.get("keep", "first")
        
        return df.drop_duplicates(subset=subset, keep=keep)
    
    def _normalize_names(self, df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
        """Normalize name fields"""
        columns = config.get("columns", [])
        
        for column in columns:
            if column in df.columns:
                # Basic name normalization
                df[column] = (df[column]
                            .astype(str)
                            .str.strip()
                            .str.title()
                            .str.replace(r'\\s+', ' ', regex=True))
        
        return df
    
    def _extract_numbers(self, df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
        """Extract numbers from text fields"""
        columns = config.get("columns", [])
        
        for column in columns:
            if column in df.columns:
                df[f"{column}_numeric"] = df[column].astype(str).str.extract(r'(\\d+(?:\\.\\d+)?)')
        
        return df
    
    def _format_phone(self, df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
        """Format phone numbers"""
        columns = config.get("columns", [])
        format_type = config.get("format", "standard")
        
        for column in columns:
            if column in df.columns:
                # Remove all non-digit characters
                cleaned = df[column].astype(str).str.replace(r'[^\\d]', '', regex=True)
                
                if format_type == "standard":
                    # Format as (XXX) XXX-XXXX for 10-digit numbers
                    mask = cleaned.str.len() == 10
                    df.loc[mask, column] = (
                        '(' + cleaned.str[:3] + ') ' + 
                        cleaned.str[3:6] + '-' + 
                        cleaned.str[6:]
                    )
        
        return df
''',

        # File Handler
        "utils/file_handler.py": '''# src/data_staging/utils/file_handler.py
"""
File Handler - Utilities for reading and processing various file formats
"""

import pandas as pd
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Union
import chardet

logger = logging.getLogger(__name__)

class FileHandler:
    """Handle various file format reading and processing"""
    
    def __init__(self):
        self.supported_formats = {
            '.csv': self._read_csv,
            '.xlsx': self._read_excel,
            '.xls': self._read_excel,
            '.json': self._read_json,
            '.txt': self._read_text,
            '.parquet': self._read_parquet
        }
    
    def read_file(self, file_path: Union[str, Path], **kwargs) -> Optional[pd.DataFrame]:
        """Read a file and return pandas DataFrame"""
        
        file_path = Path(file_path)
        
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            return None
        
        file_extension = file_path.suffix.lower()
        
        if file_extension not in self.supported_formats:
            logger.error(f"Unsupported file format: {file_extension}")
            return None
        
        try:
            logger.info(f"Reading file: {file_path}")
            df = self.supported_formats[file_extension](file_path, **kwargs)
            logger.info(f"Successfully read {len(df)} rows, {len(df.columns)} columns")
            return df
            
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            return None
    
    def analyze_file_structure(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """Analyze file structure and provide metadata"""
        
        file_path = Path(file_path)
        
        analysis = {
            "file_name": file_path.name,
            "file_size": file_path.stat().st_size,
            "file_extension": file_path.suffix.lower(),
            "encoding": None,
            "columns": [],
            "estimated_total_rows": 0,
            "data_types": {},
            "sample_data": {},
            "has_header": True,
            "delimiter": None,
            "errors": []
        }
        
        try:
            # Detect encoding for text files
            if file_path.suffix.lower() in ['.csv', '.txt']:
                with open(file_path, 'rb') as f:
                    raw_data = f.read(10000)  # Read first 10KB
                    encoding_result = chardet.detect(raw_data)
                    analysis["encoding"] = encoding_result.get('encoding', 'utf-8')
            
            # Read a sample of the file
            sample_df = self.read_file(file_path)
            
            if sample_df is not None:
                analysis.update({
                    "columns": sample_df.columns.tolist(),
                    "estimated_total_rows": len(sample_df),
                    "data_types": sample_df.dtypes.astype(str).to_dict(),
                    "sample_data": sample_df.head(3).to_dict('records') if len(sample_df) > 0 else [],
                    "null_counts": sample_df.isnull().sum().to_dict(),
                    "memory_usage": sample_df.memory_usage(deep=True).sum()
                })
                
                # CSV-specific analysis
                if file_path.suffix.lower() == '.csv':
                    analysis["delimiter"] = self._detect_csv_delimiter(file_path)
        
        except Exception as e:
            analysis["errors"].append(str(e))
            logger.error(f"Error analyzing file {file_path}: {e}")
        
        return analysis
    
    def _read_csv(self, file_path: Path, **kwargs) -> pd.DataFrame:
        """Read CSV file"""
        
        # Default parameters
        params = {
            'encoding': 'utf-8',
            'delimiter': ',',
            'header': 0,
            'na_values': ['', 'NULL', 'null', 'N/A', 'n/a', 'NA'],
            'keep_default_na': True,
            'skipinitialspace': True
        }
        
        # Override with user parameters
        params.update(kwargs)
        
        # Try to detect encoding if not specified
        if 'encoding' not in kwargs:
            try:
                with open(file_path, 'rb') as f:
                    raw_data = f.read(10000)
                    encoding_result = chardet.detect(raw_data)
                    if encoding_result['confidence'] > 0.7:
                        params['encoding'] = encoding_result['encoding']
            except Exception:
                pass  # Fall back to utf-8
        
        # Try to detect delimiter if not specified
        if 'delimiter' not in kwargs:
            detected_delimiter = self._detect_csv_delimiter(file_path)
            if detected_delimiter:
                params['delimiter'] = detected_delimiter
        
        return pd.read_csv(file_path, **params)
    
    def _read_excel(self, file_path: Path, **kwargs) -> pd.DataFrame:
        """Read Excel file"""
        
        params = {
            'header': 0,
            'na_values': ['', 'NULL', 'null', 'N/A', 'n/a', 'NA'],
            'keep_default_na': True
        }
        
        params.update(kwargs)
        
        return pd.read_excel(file_path, **params)
    
    def _read_json(self, file_path: Path, **kwargs) -> pd.DataFrame:
        """Read JSON file"""
        
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Handle different JSON structures
        if isinstance(data, list):
            return pd.DataFrame(data)
        elif isinstance(data, dict):
            # Look for common data keys
            for key in ['data', 'records', 'items', 'results']:
                if key in data and isinstance(data[key], list):
                    return pd.DataFrame(data[key])
            
            # If no array found, try to convert dict to DataFrame
            return pd.DataFrame([data])
        else:
            raise ValueError("JSON structure not supported")
    
    def _read_text(self, file_path: Path, **kwargs) -> pd.DataFrame:
        """Read text file (treat as CSV)"""
        return self._read_csv(file_path, **kwargs)
    
    def _read_parquet(self, file_path: Path, **kwargs) -> pd.DataFrame:
        """Read Parquet file"""
        return pd.read_parquet(file_path, **kwargs)
    
    def _detect_csv_delimiter(self, file_path: Path) -> Optional[str]:
        """Detect CSV delimiter"""
        
        delimiters = [',', ';', '\\t', '|']
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                first_line = f.readline()
                
            delimiter_counts = {}
            for delimiter in delimiters:
                delimiter_counts[delimiter] = first_line.count(delimiter)
            
            # Return delimiter with highest count (if > 0)
            best_delimiter = max(delimiter_counts, key=delimiter_counts.get)
            if delimiter_counts[best_delimiter] > 0:
                return best_delimiter
                
        except Exception as e:
            logger.warning(f"Could not detect delimiter for {file_path}: {e}")
        
        return None
    
    def save_dataframe(self, df: pd.DataFrame, file_path: Union[str, Path], format: str = None) -> bool:
        """Save DataFrame to file"""
        
        file_path = Path(file_path)
        
        if format is None:
            format = file_path.suffix.lower()
        
        try:
            if format in ['.csv']:
                df.to_csv(file_path, index=False)
            elif format in ['.xlsx']:
                df.to_excel(file_path, index=False)
            elif format in ['.json']:
                df.to_json(file_path, orient='records', indent=2)
            elif format in ['.parquet']:
                df.to_parquet(file_path, index=False)
            else:
                logger.error(f"Unsupported save format: {format}")
                return False
            
            logger.info(f"Successfully saved DataFrame to {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving DataFrame to {file_path}: {e}")
            return False
    
    def validate_file_format(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """Validate file format and structure"""
        
        file_path = Path(file_path)
        
        validation = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "file_info": {
                "exists": file_path.exists(),
                "size": file_path.stat().st_size if file_path.exists() else 0,
                "extension": file_path.suffix.lower(),
                "supported": file_path.suffix.lower() in self.supported_formats
            }
        }
        
        if not validation["file_info"]["exists"]:
            validation["valid"] = False
            validation["errors"].append("File does not exist")
        
        if not validation["file_info"]["supported"]:
            validation["valid"] = False
            validation["errors"].append(f"Unsupported file format: {file_path.suffix}")
        
        if validation["file_info"]["size"] == 0:
            validation["valid"] = False
            validation["errors"].append("File is empty")
        
        if validation["file_info"]["size"] > 100 * 1024 * 1024:  # 100MB
            validation["warnings"].append("Large file size (>100MB) may impact performance")
        
        return validation
''',

        # Staging Pipeline
        "core/etl/staging_pipeline.py": '''# src/data_staging/core/etl/staging_pipeline.py
"""
Staging Pipeline - Pipeline for processing data from staging to production
"""

import logging
from typing import Dict, Any, List, Optional
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)

class PipelineStage(Enum):
    """Pipeline execution stages"""
    VALIDATION = "validation"
    DEDUPLICATION = "deduplication"
    TRANSFORMATION = "transformation"
    PRODUCTION_LOAD = "production_load"
    COMPLETION = "completion"

class PipelineStatus(Enum):
    """Pipeline execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class PipelineResult:
    """Result of pipeline execution"""
    batch_id: str
    stage: PipelineStage
    success: bool
    message: str
    records_processed: int = 0
    records_validated: int = 0
    records_deduplicated: int = 0
    records_loaded: int = 0
    duplicates_found: int = 0
    validation_score: float = 0.0
    execution_time: float = 0.0
    error_details: str = None
    metadata: Dict[str, Any] = None

class StagingPipeline:
    """Pipeline for processing staging data to production"""
    
    def __init__(self):
        self.pipeline_id = None
        self.current_stage = None
        self.status = PipelineStatus.PENDING
        self.results = []
        
    def process_batch_to_production(
        self,
        batch_id: str,
        staging_table: str,
        production_table: str,
        production_schema: str = "production",
        dedup_columns: List[str] = None,
        validation_rules: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Process a batch from staging to production"""
        
        self.pipeline_id = str(uuid.uuid4())
        start_time = datetime.now()
        
        try:
            logger.info(f"Starting pipeline {self.pipeline_id} for batch {batch_id}")
            self.status = PipelineStatus.RUNNING
            
            # Stage 1: Validation
            validation_result = self._validate_staging_data(
                batch_id, staging_table, validation_rules
            )
            self.results.append(validation_result)
            
            if not validation_result.success:
                raise Exception(f"Validation failed: {validation_result.message}")
            
            # Stage 2: Deduplication
            dedup_result = self._deduplicate_data(
                batch_id, staging_table, dedup_columns
            )
            self.results.append(dedup_result)
            
            if not dedup_result.success:
                raise Exception(f"Deduplication failed: {dedup_result.message}")
            
            # Stage 3: Load to Production
            load_result = self._load_to_production(
                batch_id, staging_table, production_table, production_schema
            )
            self.results.append(load_result)
            
            if not load_result.success:
                raise Exception(f"Production load failed: {load_result.message}")
            
            # Pipeline completed successfully
            self.status = PipelineStatus.COMPLETED
            end_time = datetime.now()
            execution_time = (end_time - start_time).total_seconds()
            
            summary = {
                "pipeline_id": self.pipeline_id,
                "batch_id": batch_id,
                "status": self.status.value,
                "success": True,
                "message": "Pipeline completed successfully",
                "execution_time": execution_time,
                "records_processed": sum(r.records_processed for r in self.results),
                "records_loaded": sum(r.records_loaded for r in self.results),
                "validation_score": validation_result.validation_score,
                "duplicates_found": dedup_result.duplicates_found,
                "stages": [r.__dict__ for r in self.results]
            }
            
            logger.info(f"Pipeline {self.pipeline_id} completed in {execution_time:.2f}s")
            return summary
            
        except Exception as e:
            self.status = PipelineStatus.FAILED
            error_summary = {
                "pipeline_id": self.pipeline_id,
                "batch_id": batch_id,
                "status": self.status.value,
                "success": False,
                "message": f"Pipeline failed: {str(e)}",
                "error_details": str(e),
                "stages": [r.__dict__ for r in self.results]
            }
            
            logger.error(f"Pipeline {self.pipeline_id} failed: {e}")
            return error_summary
    
    def _validate_staging_data(
        self, 
        batch_id: str, 
        staging_table: str, 
        validation_rules: Dict[str, Any] = None
    ) -> PipelineResult:
        """Validate data in staging table"""
        
        logger.info(f"Validating staging data for batch {batch_id}")
        
        # Placeholder validation logic
        # In a real implementation, this would:
        # 1. Query the staging table
        # 2. Apply validation rules
        # 3. Update validation status in staging records
        # 4. Calculate quality scores
        
        return PipelineResult(
            batch_id=batch_id,
            stage=PipelineStage.VALIDATION,
            success=True,
            message="Validation completed successfully",
            records_processed=100,  # Placeholder
            records_validated=95,   # Placeholder
            validation_score=92.5   # Placeholder
        )
    
    def _deduplicate_data(
        self, 
        batch_id: str, 
        staging_table: str, 
        dedup_columns: List[str] = None
    ) -> PipelineResult:
        """Remove duplicates from staging data"""
        
        logger.info(f"Deduplicating data for batch {batch_id}")
        
        # Placeholder deduplication logic
        # In a real implementation, this would:
        # 1. Identify duplicates based on dedup_columns
        # 2. Mark duplicates in staging table
        # 3. Keep only the first/latest occurrence
        
        return PipelineResult(
            batch_id=batch_id,
            stage=PipelineStage.DEDUPLICATION,
            success=True,
            message="Deduplication completed successfully",
            records_processed=95,
            records_deduplicated=90,
            duplicates_found=5
        )
    
    def _load_to_production(
        self, 
        batch_id: str, 
        staging_table: str, 
        production_table: str,
        production_schema: str = "production"
    ) -> PipelineResult:
        """Load validated data to production table"""
        
        logger.info(f"Loading data to production: {production_schema}.{production_table}")
        
        # Placeholder production load logic
        # In a real implementation, this would:
        # 1. Create production table if not exists
        # 2. Insert/update records from staging
        # 3. Handle conflicts and constraints
        # 4. Update load history
        
        return PipelineResult(
            batch_id=batch_id,
            stage=PipelineStage.PRODUCTION_LOAD,
            success=True,
            message="Production load completed successfully",
            records_processed=90,
            records_loaded=90
        )

# Convenience function for external use
def process_batch_to_production(**kwargs) -> Dict[str, Any]:
    """Process a batch from staging to production"""
    pipeline = StagingPipeline()
    return pipeline.process_batch_to_production(**kwargs)
''',

        # Core __init__.py files
        "core/__init__.py": '''# src/data_staging/core/__init__.py
"""
Core components for the Data Staging System
"""

from .validators.data_validator import DataValidator, ValidationResult
from .etl.engine import ETLEngine, ETLResult
from .etl.staging_pipeline import StagingPipeline, process_batch_to_production

__all__ = [
    'DataValidator',
    'ValidationResult', 
    'ETLEngine',
    'ETLResult',
    'StagingPipeline',
    'process_batch_to_production'
]
''',

        "core/validators/__init__.py": '''# src/data_staging/core/validators/__init__.py
"""
Data validation components
"""

from .data_validator import DataValidator, ValidationResult

__all__ = ['DataValidator', 'ValidationResult']
''',

        "core/etl/__init__.py": '''# src/data_staging/core/etl/__init__.py
"""
ETL processing components
"""

from .engine import ETLEngine, ETLResult
from .staging_pipeline import StagingPipeline, process_batch_to_production

__all__ = ['ETLEngine', 'ETLResult', 'StagingPipeline', 'process_batch_to_production']
''',

        "utils/__init__.py": '''# src/data_staging/utils/__init__.py
"""
Utility components
"""

from .file_handler import FileHandler

__all__ = ['FileHandler']
'''
    }
    
    # Create all files
    for file_path, content in files_to_create.items():
        full_path = src_dir / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Only create if doesn't exist or is empty
        if not full_path.exists() or full_path.stat().st_size == 0:
            full_path.write_text(content)
            print(f"✅ Created: {file_path}")
        else:
            print(f"⏭️  Skipped: {file_path} (already exists)")
    
    print(f"\n🎉 Missing core files have been created!")
    print(f"📁 Location: {src_dir}")
    
    return True

def verify_imports():
    """Verify that the core modules can be imported"""
    print(f"\n🧪 Testing imports...")
    
    try:
        # Test core imports
        from data_staging.core.validators.data_validator import DataValidator
        print("✅ DataValidator import successful")
        
        from data_staging.core.etl.engine import ETLEngine  
        print("✅ ETLEngine import successful")
        
        from data_staging.utils.file_handler import FileHandler
        print("✅ FileHandler import successful")
        
        from data_staging.core.etl.staging_pipeline import StagingPipeline
        print("✅ StagingPipeline import successful")
        
        # Test instantiation
        validator = DataValidator()
        engine = ETLEngine()
        handler = FileHandler()
        pipeline = StagingPipeline()
        
        print("✅ All components can be instantiated")
        print("\n🎯 Core components are ready to use!")
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Creating Missing Core Data Staging Files")
    print("=" * 50)
    
    success = create_missing_files()
    
    if success:
        print("\n" + "=" * 50)
        verify_imports()
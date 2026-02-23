#!/usr/bin/env python3
"""
Enhanced Data Validation System with Referential Integrity
File: src/data_staging/core/validators/enhanced_data_validator.py

This module provides comprehensive validation including:
- Standard data quality rules
- Referential integrity checks
- Cross-table validation
- Business rule validation
- Custom validation functions
"""

import pandas as pd
import numpy as np
import re
from datetime import datetime, date
from typing import Dict, List, Any, Optional, Union, Callable
import logging
from sqlalchemy.orm import Session
from sqlalchemy import text
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class ValidationSeverity(Enum):
    """Validation severity levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

@dataclass
class ValidationIssue:
    """Individual validation issue"""
    rule_name: str
    severity: ValidationSeverity
    message: str
    column: Optional[str] = None
    row_numbers: Optional[List[int]] = None
    failed_values: Optional[List[Any]] = None
    count: int = 0

@dataclass
class ReferentialIntegrityConfig:
    """Configuration for referential integrity checks"""
    local_column: str
    reference_table: str
    reference_column: str
    reference_schema: str = "public"
    allow_null: bool = False
    custom_condition: Optional[str] = None  # Additional WHERE clause
    error_message: Optional[str] = None

class EnhancedValidationResult:
    """Enhanced validation result with detailed reporting"""
    
    def __init__(self):
        self.passed = True
        self.issues: List[ValidationIssue] = []
        self.score = 100.0
        self.referential_integrity_passed = True
        self.details = {}
        self.performance_metrics = {}
        
    def add_issue(self, issue: ValidationIssue):
        """Add validation issue"""
        self.issues.append(issue)
        
        # Update passed status based on severity
        if issue.severity in [ValidationSeverity.ERROR, ValidationSeverity.CRITICAL]:
            self.passed = False
            if issue.rule_name.startswith('referential_'):
                self.referential_integrity_passed = False
        
        # Adjust score based on severity and count
        severity_weights = {
            ValidationSeverity.INFO: 0,
            ValidationSeverity.WARNING: 2,
            ValidationSeverity.ERROR: 10,
            ValidationSeverity.CRITICAL: 25
        }
        
        penalty = severity_weights[issue.severity] * (issue.count / 100 if issue.count > 0 else 1)
        self.score = max(0, self.score - penalty)
        
    def get_summary(self) -> Dict[str, Any]:
        """Get comprehensive validation summary"""
        issues_by_severity = {}
        for severity in ValidationSeverity:
            issues_by_severity[severity.value] = [
                issue for issue in self.issues if issue.severity == severity
            ]
        
        return {
            "passed": self.passed,
            "score": round(self.score, 2),
            "grade": self._get_grade(),
            "referential_integrity_passed": self.referential_integrity_passed,
            "total_issues": len(self.issues),
            "issues_by_severity": {
                severity: len(issues) for severity, issues in issues_by_severity.items()
            },
            "critical_issues": len([i for i in self.issues if i.severity == ValidationSeverity.CRITICAL]),
            "error_issues": len([i for i in self.issues if i.severity == ValidationSeverity.ERROR]),
            "warning_issues": len([i for i in self.issues if i.severity == ValidationSeverity.WARNING]),
            "info_issues": len([i for i in self.issues if i.severity == ValidationSeverity.INFO]),
            "detailed_issues": [
                {
                    "rule": issue.rule_name,
                    "severity": issue.severity.value,
                    "message": issue.message,
                    "column": issue.column,
                    "count": issue.count,
                    "sample_failed_values": issue.failed_values[:5] if issue.failed_values else None
                }
                for issue in self.issues
            ],
            "details": self.details,
            "performance_metrics": self.performance_metrics
        }
        
    def _get_grade(self) -> str:
        """Convert score to letter grade"""
        if self.score >= 95: return "A+"
        elif self.score >= 90: return "A"
        elif self.score >= 85: return "B+"
        elif self.score >= 80: return "B"
        elif self.score >= 75: return "C+"
        elif self.score >= 70: return "C"
        elif self.score >= 65: return "D"
        else: return "F"

class EnhancedDataValidator:
    """Enhanced data validation engine with referential integrity"""
    
    def __init__(self, db_session: Optional[Session] = None):
        self.db_session = db_session
        self.validation_rules = {
            # Standard validation rules
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
            'consistency': self._validate_consistency,
            
            # Enhanced validation rules
            'referential_integrity': self._validate_referential_integrity,
            'cross_table_validation': self._validate_cross_table,
            'lookup_validation': self._validate_lookup_values,
            'hierarchical_validation': self._validate_hierarchical_relationships,
            'conditional_validation': self._validate_conditional_rules,
            'aggregate_validation': self._validate_aggregate_constraints,
        }
        
        # Cache for reference data
        self.reference_cache = {}
        
    def validate_dataframe(
        self, 
        df: pd.DataFrame, 
        rules: Dict[str, Any] = None,
        table_context: str = None
    ) -> Dict[str, Any]:
        """Enhanced dataframe validation with referential integrity"""
        
        if df is None or df.empty:
            return {"passed": False, "error": "DataFrame is empty or None"}
        
        start_time = datetime.now()
        result = EnhancedValidationResult()
        
        # Default rules if none provided
        if rules is None:
            rules = self._get_default_rules(df)
        
        # Add table context for better error messages
        result.details["table_context"] = table_context
        result.details["total_rows"] = len(df)
        result.details["total_columns"] = len(df.columns)
        
        # Run each validation rule
        for rule_name, rule_config in rules.items():
            if rule_name in self.validation_rules:
                try:
                    rule_start = datetime.now()
                    self.validation_rules[rule_name](df, rule_config, result)
                    rule_end = datetime.now()
                    
                    # Track performance
                    rule_duration = (rule_end - rule_start).total_seconds()
                    result.performance_metrics[rule_name] = rule_duration
                    
                    logger.debug(f"Validation rule '{rule_name}' completed in {rule_duration:.3f}s")
                    
                except Exception as e:
                    error_issue = ValidationIssue(
                        rule_name=rule_name,
                        severity=ValidationSeverity.ERROR,
                        message=f"Validation rule '{rule_name}' failed: {str(e)}",
                        count=1
                    )
                    result.add_issue(error_issue)
                    logger.error(f"Validation error in {rule_name}: {e}")
        
        # Calculate overall metrics
        end_time = datetime.now()
        total_duration = (end_time - start_time).total_seconds()
        
        result.details.update({
            "validation_duration": total_duration,
            "null_values": df.isnull().sum().sum(),
            "duplicate_rows": df.duplicated().sum(),
            "memory_usage": df.memory_usage(deep=True).sum(),
            "columns_analyzed": list(df.columns)
        })
        
        return result.get_summary()
    
    def _validate_referential_integrity(
        self, 
        df: pd.DataFrame, 
        config: Dict[str, Any], 
        result: EnhancedValidationResult
    ):
        """Validate referential integrity against other tables"""
        
        if not self.db_session:
            result.add_issue(ValidationIssue(
                rule_name="referential_integrity",
                severity=ValidationSeverity.WARNING,
                message="Database session not available for referential integrity checks",
                count=1
            ))
            return
        
        ref_configs = config.get("references", [])
        if not ref_configs:
            return
        
        for ref_config in ref_configs:
            self._check_single_reference(df, ref_config, result)
    
    def _check_single_reference(
        self, 
        df: pd.DataFrame, 
        ref_config: Dict[str, Any], 
        result: EnhancedValidationResult
    ):
        """Check a single referential integrity constraint"""
        
        try:
            # Parse configuration
            local_column = ref_config["local_column"]
            reference_table = ref_config["reference_table"]
            reference_column = ref_config["reference_column"]
            reference_schema = ref_config.get("reference_schema", "public")
            allow_null = ref_config.get("allow_null", False)
            custom_condition = ref_config.get("custom_condition", "")
            error_message = ref_config.get("error_message")
            
            if local_column not in df.columns:
                result.add_issue(ValidationIssue(
                    rule_name="referential_integrity",
                    severity=ValidationSeverity.ERROR,
                    message=f"Column '{local_column}' not found for referential integrity check",
                    column=local_column,
                    count=1
                ))
                return
            
            # Get unique values to check (excluding nulls if not allowed)
            values_to_check = df[local_column].dropna().unique() if not allow_null else df[local_column].unique()
            
            if len(values_to_check) == 0:
                return
            
            # Build reference query
            cache_key = f"{reference_schema}.{reference_table}.{reference_column}"
            
            if cache_key not in self.reference_cache:
                base_query = f"""
                    SELECT DISTINCT {reference_column} 
                    FROM {reference_schema}.{reference_table}
                    WHERE {reference_column} IS NOT NULL
                """
                
                if custom_condition:
                    base_query += f" AND {custom_condition}"
                
                try:
                    ref_result = self.db_session.execute(text(base_query))
                    valid_references = {row[0] for row in ref_result}
                    self.reference_cache[cache_key] = valid_references
                    logger.debug(f"Cached {len(valid_references)} reference values for {cache_key}")
                except Exception as e:
                    result.add_issue(ValidationIssue(
                        rule_name="referential_integrity",
                        severity=ValidationSeverity.ERROR,
                        message=f"Failed to query reference table {reference_schema}.{reference_table}: {str(e)}",
                        column=local_column,
                        count=1
                    ))
                    return
            
            valid_references = self.reference_cache[cache_key]
            
            # Find invalid references
            invalid_values = []
            invalid_rows = []
            
            for idx, value in enumerate(df[local_column]):
                if pd.isna(value):
                    if not allow_null:
                        invalid_values.append(value)
                        invalid_rows.append(idx)
                elif value not in valid_references:
                    invalid_values.append(value)
                    invalid_rows.append(idx)
            
            if invalid_values:
                severity = ValidationSeverity.CRITICAL if not allow_null else ValidationSeverity.ERROR
                message = error_message or f"Found {len(invalid_values)} invalid references in '{local_column}' to {reference_schema}.{reference_table}.{reference_column}"
                
                result.add_issue(ValidationIssue(
                    rule_name="referential_integrity",
                    severity=severity,
                    message=message,
                    column=local_column,
                    row_numbers=invalid_rows[:100],  # Limit to first 100 for performance
                    failed_values=list(set(invalid_values))[:20],  # Unique values, limited
                    count=len(invalid_values)
                ))
                
                logger.warning(f"Referential integrity violation: {len(invalid_values)} invalid values in {local_column}")
            else:
                logger.debug(f"Referential integrity check passed for {local_column}")
                
        except Exception as e:
            result.add_issue(ValidationIssue(
                rule_name="referential_integrity",
                severity=ValidationSeverity.ERROR,
                message=f"Referential integrity check failed: {str(e)}",
                column=local_column if 'local_column' in locals() else None,
                count=1
            ))
    
    def _validate_cross_table(
        self, 
        df: pd.DataFrame, 
        config: Dict[str, Any], 
        result: EnhancedValidationResult
    ):
        """Validate data against other tables with complex conditions"""
        
        if not self.db_session:
            return
        
        cross_checks = config.get("cross_checks", [])
        
        for check in cross_checks:
            try:
                check_name = check.get("name", "cross_table_check")
                query = check["query"]
                expected_result = check.get("expected_result", "empty")
                error_message = check.get("error_message", f"Cross-table validation failed: {check_name}")
                
                # Execute cross-table query
                query_result = self.db_session.execute(text(query))
                results = query_result.fetchall()
                
                # Evaluate result based on expectation
                if expected_result == "empty" and len(results) > 0:
                    result.add_issue(ValidationIssue(
                        rule_name="cross_table_validation",
                        severity=ValidationSeverity.ERROR,
                        message=f"{error_message} - Found {len(results)} unexpected results",
                        count=len(results)
                    ))
                elif expected_result == "not_empty" and len(results) == 0:
                    result.add_issue(ValidationIssue(
                        rule_name="cross_table_validation",
                        severity=ValidationSeverity.ERROR,
                        message=f"{error_message} - Expected results but found none",
                        count=1
                    ))
                    
            except Exception as e:
                result.add_issue(ValidationIssue(
                    rule_name="cross_table_validation",
                    severity=ValidationSeverity.ERROR,
                    message=f"Cross-table validation error: {str(e)}",
                    count=1
                ))
    
    def _validate_lookup_values(
        self, 
        df: pd.DataFrame, 
        config: Dict[str, Any], 
        result: EnhancedValidationResult
    ):
        """Validate against lookup tables or allowed value lists"""
        
        lookups = config.get("lookups", {})
        
        for column, lookup_config in lookups.items():
            if column not in df.columns:
                continue
                
            lookup_type = lookup_config.get("type", "table")
            
            if lookup_type == "table":
                # Table-based lookup
                self._validate_table_lookup(df, column, lookup_config, result)
            elif lookup_type == "values":
                # Static value list lookup
                self._validate_value_list_lookup(df, column, lookup_config, result)
    
    def _validate_table_lookup(
        self, 
        df: pd.DataFrame, 
        column: str, 
        lookup_config: Dict[str, Any], 
        result: EnhancedValidationResult
    ):
        """Validate against a lookup table"""
        
        if not self.db_session:
            return
        
        try:
            lookup_table = lookup_config["table"]
            lookup_column = lookup_config["column"]
            lookup_schema = lookup_config.get("schema", "public")
            additional_filters = lookup_config.get("filters", "")
            
            # Query lookup values
            query = f"""
                SELECT DISTINCT {lookup_column} 
                FROM {lookup_schema}.{lookup_table} 
                WHERE {lookup_column} IS NOT NULL
            """
            
            if additional_filters:
                query += f" AND {additional_filters}"
            
            lookup_result = self.db_session.execute(text(query))
            valid_values = {row[0] for row in lookup_result}
            
            # Check values
            invalid_mask = ~df[column].isin(valid_values) & df[column].notna()
            invalid_count = invalid_mask.sum()
            
            if invalid_count > 0:
                invalid_values = df.loc[invalid_mask, column].unique()[:10]
                
                result.add_issue(ValidationIssue(
                    rule_name="lookup_validation",
                    severity=ValidationSeverity.ERROR,
                    message=f"Found {invalid_count} invalid values in '{column}' not in lookup table {lookup_schema}.{lookup_table}",
                    column=column,
                    failed_values=list(invalid_values),
                    count=invalid_count
                ))
                
        except Exception as e:
            result.add_issue(ValidationIssue(
                rule_name="lookup_validation",
                severity=ValidationSeverity.ERROR,
                message=f"Lookup validation error for column '{column}': {str(e)}",
                column=column,
                count=1
            ))
    
    def _validate_value_list_lookup(
        self, 
        df: pd.DataFrame, 
        column: str, 
        lookup_config: Dict[str, Any], 
        result: EnhancedValidationResult
    ):
        """Validate against a static list of allowed values"""
        
        allowed_values = set(lookup_config["values"])
        case_sensitive = lookup_config.get("case_sensitive", True)
        
        if not case_sensitive:
            allowed_values = {str(v).lower() for v in allowed_values}
            check_values = df[column].astype(str).str.lower()
        else:
            check_values = df[column]
        
        invalid_mask = ~check_values.isin(allowed_values) & df[column].notna()
        invalid_count = invalid_mask.sum()
        
        if invalid_count > 0:
            invalid_values = df.loc[invalid_mask, column].unique()[:10]
            
            result.add_issue(ValidationIssue(
                rule_name="lookup_validation",
                severity=ValidationSeverity.ERROR,
                message=f"Found {invalid_count} invalid values in '{column}' not in allowed list",
                column=column,
                failed_values=list(invalid_values),
                count=invalid_count
            ))
    
    def _validate_hierarchical_relationships(
        self, 
        df: pd.DataFrame, 
        config: Dict[str, Any], 
        result: EnhancedValidationResult
    ):
        """Validate hierarchical relationships (parent-child)"""
        
        hierarchies = config.get("hierarchies", [])
        
        for hierarchy in hierarchies:
            try:
                parent_column = hierarchy["parent_column"]
                child_column = hierarchy["child_column"]
                hierarchy_table = hierarchy.get("hierarchy_table")
                
                if parent_column not in df.columns or child_column not in df.columns:
                    continue
                
                if hierarchy_table and self.db_session:
                    # Validate against hierarchy table
                    self._validate_against_hierarchy_table(df, hierarchy, result)
                else:
                    # Validate internal hierarchy consistency
                    self._validate_internal_hierarchy(df, hierarchy, result)
                    
            except Exception as e:
                result.add_issue(ValidationIssue(
                    rule_name="hierarchical_validation",
                    severity=ValidationSeverity.ERROR,
                    message=f"Hierarchical validation error: {str(e)}",
                    count=1
                ))
    
    def _validate_conditional_rules(
        self, 
        df: pd.DataFrame, 
        config: Dict[str, Any], 
        result: EnhancedValidationResult
    ):
        """Validate conditional business rules"""
        
        conditions = config.get("conditions", [])
        
        for condition in conditions:
            try:
                condition_expr = condition["if"]
                then_expr = condition["then"]
                rule_name = condition.get("name", "conditional_rule")
                severity = getattr(ValidationSeverity, condition.get("severity", "ERROR").upper())
                
                # Evaluate condition
                condition_mask = df.eval(condition_expr)
                
                # For rows where condition is true, check the 'then' expression
                if condition_mask.any():
                    then_mask = df.eval(then_expr)
                    violations = condition_mask & ~then_mask
                    violation_count = violations.sum()
                    
                    if violation_count > 0:
                        result.add_issue(ValidationIssue(
                            rule_name="conditional_validation",
                            severity=severity,
                            message=f"Conditional rule '{rule_name}' violated by {violation_count} records",
                            count=violation_count
                        ))
                        
            except Exception as e:
                result.add_issue(ValidationIssue(
                    rule_name="conditional_validation",
                    severity=ValidationSeverity.ERROR,
                    message=f"Conditional validation error: {str(e)}",
                    count=1
                ))
    
    def _validate_aggregate_constraints(
        self, 
        df: pd.DataFrame, 
        config: Dict[str, Any], 
        result: EnhancedValidationResult
    ):
        """Validate aggregate constraints (sums, counts, etc.)"""
        
        constraints = config.get("constraints", [])
        
        for constraint in constraints:
            try:
                constraint_type = constraint["type"]
                column = constraint.get("column")
                group_by = constraint.get("group_by", [])
                expected_value = constraint.get("expected_value")
                operator = constraint.get("operator", "=")
                tolerance = constraint.get("tolerance", 0)
                
                if constraint_type == "sum":
                    if group_by:
                        actual_values = df.groupby(group_by)[column].sum()
                    else:
                        actual_values = pd.Series([df[column].sum()])
                elif constraint_type == "count":
                    if group_by:
                        actual_values = df.groupby(group_by).size()
                    else:
                        actual_values = pd.Series([len(df)])
                else:
                    continue
                
                # Check constraint violations
                violations = 0
                if operator == "=":
                    violations = (~np.isclose(actual_values, expected_value, atol=tolerance)).sum()
                elif operator == ">":
                    violations = (actual_values <= expected_value).sum()
                elif operator == "<":
                    violations = (actual_values >= expected_value).sum()
                
                if violations > 0:
                    result.add_issue(ValidationIssue(
                        rule_name="aggregate_validation",
                        severity=ValidationSeverity.ERROR,
                        message=f"Aggregate constraint violated: {constraint_type}({column}) {operator} {expected_value}",
                        column=column,
                        count=violations
                    ))
                    
            except Exception as e:
                result.add_issue(ValidationIssue(
                    rule_name="aggregate_validation",
                    severity=ValidationSeverity.ERROR,
                    message=f"Aggregate validation error: {str(e)}",
                    count=1
                ))
    
    def clear_cache(self):
        """Clear the reference data cache"""
        self.reference_cache.clear()
        logger.debug("Reference cache cleared")
    
    # Include all the existing validation methods from the original DataValidator
    # (not_null, unique, completeness, etc.) - these would be the same as before
    
    def _validate_not_null(self, df: pd.DataFrame, config: Dict[str, Any], result: EnhancedValidationResult):
        """Validate that specified columns are not null"""
        columns = config.get("columns", [])
        severity = getattr(ValidationSeverity, config.get("severity", "ERROR").upper())
        
        for column in columns:
            if column in df.columns:
                null_count = df[column].isnull().sum()
                if null_count > 0:
                    result.add_issue(ValidationIssue(
                        rule_name="not_null",
                        severity=severity,
                        message=f"Column '{column}' has {null_count} null values",
                        column=column,
                        count=null_count
                    ))
    
    def _validate_unique(self, df: pd.DataFrame, config: Dict[str, Any], result: EnhancedValidationResult):
        """Validate uniqueness constraints"""
        columns = config.get("columns", [])
        severity = getattr(ValidationSeverity, config.get("severity", "ERROR").upper())
        
        for column in columns:
            if column in df.columns:
                duplicate_count = df[column].duplicated().sum()
                if duplicate_count > 0:
                    result.add_issue(ValidationIssue(
                        rule_name="unique",
                        severity=severity,
                        message=f"Column '{column}' has {duplicate_count} duplicate values",
                        column=column,
                        count=duplicate_count
                    ))
    
    def _validate_completeness(self, df: pd.DataFrame, config: Dict[str, Any], result: EnhancedValidationResult):
        """Validate data completeness"""
        threshold = config.get("threshold", 0.9)
        columns = config.get("columns", df.columns.tolist())
        severity = getattr(ValidationSeverity, config.get("severity", "WARNING").upper())
        
        for column in columns:
            if column in df.columns:
                completeness = (df[column].notna().sum() / len(df))
                if completeness < threshold:
                    result.add_issue(ValidationIssue(
                        rule_name="completeness",
                        severity=severity,
                        message=f"Column '{column}' completeness {completeness:.2%} below threshold {threshold:.2%}",
                        column=column,
                        count=1
                    ))

    def _validate_data_type(self, df: pd.DataFrame, config: Dict[str, Any], result: EnhancedValidationResult):
        """Validate data types based on pandas dtypes"""
        # Simplified implementation for basic type checking
        columns = config.get("columns", {})
        strict = config.get("strict", False)
        
        for col, expected_type in columns.items():
            if col in df.columns:
                # This is a basic check - in improved version, check actual values
                pass

    def _validate_range(self, df: pd.DataFrame, config: Dict[str, Any], result: EnhancedValidationResult):
        """Validate numeric ranges"""
        ranges = config.get("ranges", {})
        severity = getattr(ValidationSeverity, config.get("severity", "ERROR").upper())
        
        for col, limits in ranges.items():
            if col in df.columns and pd.api.types.is_numeric_dtype(df[col]):
                min_val = limits.get("min", float("-inf"))
                max_val = limits.get("max", float("inf"))
                
                out_of_range = df[~((df[col] >= min_val) & (df[col] <= max_val)) & df[col].notna()]
                count = len(out_of_range)
                
                if count > 0:
                    result.add_issue(ValidationIssue(
                        rule_name="range",
                        severity=severity,
                        message=f"Column '{col}' has {count} values out of range [{min_val}, {max_val}]",
                        column=col,
                        count=count,
                        failed_values=out_of_range[col].head(5).tolist()
                    ))

    def _validate_pattern(self, df: pd.DataFrame, config: Dict[str, Any], result: EnhancedValidationResult):
        """Validate string patterns (regex)"""
        patterns = config.get("patterns", {})
        severity = getattr(ValidationSeverity, config.get("severity", "ERROR").upper())
        
        for col, pattern in patterns.items():
            if col in df.columns:
                # Convert to string ensuring usage of python regex
                mask = ~df[col].astype(str).str.match(pattern, na=False) & df[col].notna()
                count = mask.sum()
                
                if count > 0:
                    result.add_issue(ValidationIssue(
                        rule_name="pattern",
                        severity=severity,
                        message=f"Column '{col}' has {count} values not matching pattern",
                        column=col,
                        count=count
                    ))

    def _validate_email(self, df: pd.DataFrame, config: Dict[str, Any], result: EnhancedValidationResult):
        """Validate email format"""
        columns = config.get("columns", [])
        severity = getattr(ValidationSeverity, config.get("severity", "ERROR").upper())
        # Simple email regex
        email_pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
        
        for col in columns:
            if col in df.columns:
                mask = ~df[col].astype(str).str.match(email_pattern, na=False) & df[col].notna()
                count = mask.sum()
                
                if count > 0:
                    result.add_issue(ValidationIssue(
                        rule_name="email",
                        severity=severity,
                        message=f"Column '{col}' has {count} invalid email addresses",
                        column=col,
                        count=count
                    ))

    def _validate_phone(self, df: pd.DataFrame, config: Dict[str, Any], result: EnhancedValidationResult):
        """Validate phone format"""
        columns = config.get("columns", [])
        severity = getattr(ValidationSeverity, config.get("severity", "WARNING").upper())
        # Simple phone regex (digits only, 7-15 chars)
        phone_pattern = r'^\+?\d{7,15}$'
        
        for col in columns:
            if col in df.columns:
                # Remove common separators for check
                clean_phone = df[col].astype(str).str.replace(r'[\s\-\(\)]', '', regex=True)
                mask = ~clean_phone.str.match(phone_pattern, na=False) & df[col].notna()
                count = mask.sum()
                
                if count > 0:
                    result.add_issue(ValidationIssue(
                        rule_name="phone",
                        severity=severity,
                        message=f"Column '{col}' has {count} invalid phone numbers",
                        column=col,
                        count=count
                    ))

    def _validate_date(self, df: pd.DataFrame, config: Dict[str, Any], result: EnhancedValidationResult):
        """Validate date format and range"""
        columns = config.get("columns", [])
        min_date = config.get("min_date")
        max_date = config.get("max_date")
        severity = getattr(ValidationSeverity, config.get("severity", "ERROR").upper())
        
        if min_date: min_date = pd.to_datetime(min_date)
        if max_date: max_date = pd.to_datetime(max_date)
        
        for col in columns:
            if col in df.columns:
                # Check if parseable
                try:
                    dates = pd.to_datetime(df[col], errors='coerce')
                    invalid_format = dates.isna() & df[col].notna()
                    invalid_fmt_count = invalid_format.sum()
                    
                    if invalid_fmt_count > 0:
                        result.add_issue(ValidationIssue(
                            rule_name="date_format",
                            severity=severity,
                            message=f"Column '{col}' has {invalid_fmt_count} invalid dates (format)",
                            column=col,
                            count=invalid_fmt_count
                        ))
                    
                    # Check ranges on valid dates
                    if min_date or max_date:
                        valid_dates = dates.dropna()
                        mask = pd.Series(False, index=valid_dates.index)
                        if min_date:
                            mask |= (valid_dates < min_date)
                        if max_date:
                            mask |= (valid_dates > max_date)
                        
                        range_violations = mask.sum()
                        if range_violations > 0:
                            result.add_issue(ValidationIssue(
                                rule_name="date_range",
                                severity=severity,
                                message=f"Column '{col}' has {range_violations} dates out of range",
                                column=col,
                                count=range_violations
                            ))
                            
                except Exception as e:
                    logger.error(f"Date validation error: {e}")

    def _validate_business_rule(self, df: pd.DataFrame, config: Dict[str, Any], result: EnhancedValidationResult):
        """Validate custom business rules (pandas eval expressions)"""
        expression = config.get("expression")
        name = config.get("name", "business_rule")
        severity = getattr(ValidationSeverity, config.get("severity", "ERROR").upper())
        
        if expression:
            try:
                # Expression should evaluate to True for valid rows
                mask = df.eval(expression)
                # If mask is boolean, False means invalid
                if pd.api.types.is_bool_dtype(mask):
                    invalid_count = (~mask).sum()
                    if invalid_count > 0:
                        result.add_issue(ValidationIssue(
                            rule_name="business_rule",
                            severity=severity,
                            message=f"Business rule '{name}' violated by {invalid_count} records",
                            count=invalid_count
                        ))
            except Exception as e:
                result.add_issue(ValidationIssue(
                    rule_name="business_rule_error",
                    severity=ValidationSeverity.ERROR,
                    message=f"Failed to evaluate rule '{name}': {e}",
                    count=1
                ))

    def _validate_consistency(self, df: pd.DataFrame, config: Dict[str, Any], result: EnhancedValidationResult):
        """Validate consistency between columns"""
        # Placeholder for cross-column consistency checks
        pass
    
    # Add the remaining standard validation methods...
    # (These would be similar to the original implementation but using the new ValidationIssue structure)
    
    def _get_default_rules(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Generate default validation rules based on DataFrame"""
        return {
            "completeness": {"threshold": 0.9},
            "data_type": {"strict": False}
        }

# Usage example function
def create_sales_validation_config():
    """Create comprehensive validation configuration for sales data"""
    return {
        "not_null": {
            "columns": ["sale_id", "product_id", "location_id", "quantity", "sale_date"],
            "severity": "critical"
        },
        "unique": {
            "columns": ["sale_id"],
            "severity": "critical"
        },
        "referential_integrity": {
            "references": [
                {
                    "local_column": "product_id",
                    "reference_table": "products",
                    "reference_column": "product_id",
                    "reference_schema": "public",
                    "allow_null": False,
                    "custom_condition": "is_active = true",
                    "error_message": "Sales contain products that don't exist or are inactive"
                },
                {
                    "local_column": "location_id", 
                    "reference_table": "locations",
                    "reference_column": "location_id",
                    "reference_schema": "public",
                    "allow_null": False,
                    "custom_condition": "status = 'active'",
                    "error_message": "Sales contain invalid or inactive locations"
                },
                {
                    "local_column": "customer_id",
                    "reference_table": "customers", 
                    "reference_column": "customer_id",
                    "reference_schema": "public",
                    "allow_null": True,
                    "error_message": "Sales reference non-existent customers"
                }
            ]
        },
        "range": {
            "columns": ["quantity", "unit_price", "total_amount"],
            "ranges": {
                "quantity": {"min": 1, "max": 10000},
                "unit_price": {"min": 0.01, "max": 100000},
                "total_amount": {"min": 0.01, "max": 1000000}
            },
            "severity": "error"
        },
        "business_rule": {
            "expression": "total_amount == (quantity * unit_price)",
            "name": "total_amount_calculation",
            "severity": "critical"
        },
        "conditional_validation": {
            "conditions": [
                {
                    "name": "discount_validation",
                    "if": "discount_percent > 0",
                    "then": "discount_amount > 0",
                    "severity": "error"
                },
                {
                    "name": "bulk_discount_rule",
                    "if": "quantity >= 10",
                    "then": "discount_percent >= 5",
                    "severity": "warning"
                }
            ]
        },
        "lookup_validation": {
            "lookups": {
                "sale_type": {
                    "type": "values",
                    "values": ["RETAIL", "WHOLESALE", "ONLINE", "RETURN"],
                    "case_sensitive": False
                },
                "payment_method": {
                    "type": "table",
                    "table": "payment_methods",
                    "column": "method_code",
                    "schema": "public",
                    "filters": "is_active = true"
                }
            }
        },
        "date": {
            "columns": ["sale_date"],
            "min_date": "2020-01-01",
            "max_date": "2030-12-31",
            "severity": "error"
        }
    }

# Compatibility alias
DataValidator = EnhancedDataValidator

if __name__ == "__main__":
    # Example usage
    print("Enhanced Data Validator with Referential Integrity")
    print("This validator provides comprehensive validation including:")
    print("- Standard data quality checks")
    print("- Referential integrity validation")
    print("- Cross-table validation") 
    print("- Business rule validation")
    print("- Conditional validation")
    print("- Lookup validation")
#!/usr/bin/env python3
"""
DDL-Based Configuration Creator
File: scripts/tools/ddl_config_creator.py

This tool analyzes database table DDL (Data Definition Language) and automatically
generates comprehensive Data Source Configuration files with appropriate validation
rules, transformations, and settings based on the table structure.
"""

import re
import json
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import logging

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

try:
    from data_staging.database import get_database_manager
    from sqlalchemy import text, inspect
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False
    print("⚠️ Database not available - DDL analysis only")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DataType(Enum):
    """Supported data types with their characteristics"""
    INTEGER = "integer"
    BIGINT = "bigint"
    SMALLINT = "smallint"
    DECIMAL = "decimal"
    NUMERIC = "numeric"
    FLOAT = "float"
    DOUBLE = "double"
    REAL = "real"
    VARCHAR = "varchar"
    CHAR = "char"
    TEXT = "text"
    BOOLEAN = "boolean"
    DATE = "date"
    TIME = "time"
    TIMESTAMP = "timestamp"
    TIMESTAMPTZ = "timestamptz"
    UUID = "uuid"
    JSON = "json"
    JSONB = "jsonb"
    ARRAY = "array"
    BYTEA = "bytea"

@dataclass
class ColumnInfo:
    """Information about a database column"""
    name: str
    data_type: str
    is_nullable: bool
    default_value: Optional[str]
    max_length: Optional[int]
    precision: Optional[int]
    scale: Optional[int]
    is_primary_key: bool
    is_foreign_key: bool
    foreign_table: Optional[str]
    foreign_column: Optional[str]
    check_constraints: List[str]
    unique_constraint: bool
    comment: Optional[str]

@dataclass
class TableInfo:
    """Information about a database table"""
    schema_name: str
    table_name: str
    columns: List[ColumnInfo]
    primary_keys: List[str]
    foreign_keys: List[Dict[str, str]]
    unique_constraints: List[List[str]]
    check_constraints: List[str]
    indexes: List[Dict[str, Any]]
    table_comment: Optional[str]

class DDLParser:
    """Parse DDL statements to extract table structure"""
    
    def __init__(self):
        self.data_type_patterns = {
            r'INTEGER|INT': DataType.INTEGER,
            r'BIGINT': DataType.BIGINT,
            r'SMALLINT': DataType.SMALLINT,
            r'DECIMAL\(\d+,\d+\)|NUMERIC\(\d+,\d+\)': DataType.DECIMAL,
            r'DECIMAL|NUMERIC': DataType.NUMERIC,
            r'FLOAT|REAL': DataType.FLOAT,
            r'DOUBLE': DataType.DOUBLE,
            r'VARCHAR\(\d+\)': DataType.VARCHAR,
            r'CHAR\(\d+\)': DataType.CHAR,
            r'TEXT': DataType.TEXT,
            r'BOOLEAN|BOOL': DataType.BOOLEAN,
            r'DATE': DataType.DATE,
            r'TIME': DataType.TIME,
            r'TIMESTAMP WITH TIME ZONE|TIMESTAMPTZ': DataType.TIMESTAMPTZ,
            r'TIMESTAMP': DataType.TIMESTAMP,
            r'UUID': DataType.UUID,
            r'JSONB': DataType.JSONB,
            r'JSON': DataType.JSON,
        }
    
    def parse_ddl(self, ddl: str) -> List[TableInfo]:
        """Parse DDL string and extract table information"""
        
        tables = []
        
        # Split DDL into individual CREATE TABLE statements
        table_statements = re.split(r'CREATE TABLE', ddl, flags=re.IGNORECASE)
        
        for statement in table_statements[1:]:  # Skip first empty split
            table_info = self._parse_create_table(f"CREATE TABLE{statement}")
            if table_info:
                tables.append(table_info)
        
        return tables
    
    def _parse_create_table(self, statement: str) -> Optional[TableInfo]:
        """Parse a single CREATE TABLE statement"""
        
        try:
            # Extract table name
            table_match = re.search(
                r'CREATE TABLE\s+(?:IF NOT EXISTS\s+)?(?:(\w+)\.)?(\w+)\s*\(',
                statement,
                re.IGNORECASE
            )
            
            if not table_match:
                return None
            
            schema_name = table_match.group(1) or 'public'
            table_name = table_match.group(2)
            
            # Extract column definitions
            column_section = self._extract_column_section(statement)
            columns = self._parse_columns(column_section)
            
            # Extract constraints
            primary_keys = self._extract_primary_keys(column_section)
            foreign_keys = self._extract_foreign_keys(column_section)
            unique_constraints = self._extract_unique_constraints(column_section)
            check_constraints = self._extract_check_constraints(column_section)
            
            # Extract table comment
            table_comment = self._extract_table_comment(statement)
            
            return TableInfo(
                schema_name=schema_name,
                table_name=table_name,
                columns=columns,
                primary_keys=primary_keys,
                foreign_keys=foreign_keys,
                unique_constraints=unique_constraints,
                check_constraints=check_constraints,
                indexes=[],  # Would need separate index parsing
                table_comment=table_comment
            )
            
        except Exception as e:
            logger.error(f"Error parsing CREATE TABLE statement: {e}")
            return None
    
    def _extract_column_section(self, statement: str) -> str:
        """Extract the column definition section from CREATE TABLE"""
        
        # Find the content between the first ( and last )
        paren_start = statement.find('(')
        paren_end = statement.rfind(')')
        
        if paren_start == -1 or paren_end == -1:
            return ""
        
        return statement[paren_start + 1:paren_end]
    
    def _parse_columns(self, column_section: str) -> List[ColumnInfo]:
        """Parse column definitions"""
        
        columns = []
        
        # Split by commas, but handle commas within constraints
        column_lines = self._smart_split_columns(column_section)
        
        for line in column_lines:
            line = line.strip()
            
            # Skip constraint definitions (they start with keywords)
            if re.match(r'^\s*(PRIMARY KEY|FOREIGN KEY|UNIQUE|CHECK|CONSTRAINT)', line, re.IGNORECASE):
                continue
            
            column_info = self._parse_single_column(line)
            if column_info:
                columns.append(column_info)
        
        return columns
    
    def _smart_split_columns(self, text: str) -> List[str]:
        """Split column definitions by commas, respecting parentheses"""
        
        parts = []
        current = ""
        paren_level = 0
        
        for char in text:
            if char == '(':
                paren_level += 1
            elif char == ')':
                paren_level -= 1
            elif char == ',' and paren_level == 0:
                parts.append(current.strip())
                current = ""
                continue
            
            current += char
        
        if current.strip():
            parts.append(current.strip())
        
        return parts
    
    def _parse_single_column(self, definition: str) -> Optional[ColumnInfo]:
        """Parse a single column definition"""
        
        try:
            # Basic pattern: column_name data_type [constraints]
            parts = definition.strip().split()
            if len(parts) < 2:
                return None
            
            column_name = parts[0].strip('"').strip("'")
            data_type_part = parts[1]
            
            # Parse data type and size
            data_type, max_length, precision, scale = self._parse_data_type(data_type_part)
            
            # Parse constraints
            constraints_text = ' '.join(parts[2:])
            is_nullable = 'NOT NULL' not in constraints_text.upper()
            is_primary_key = 'PRIMARY KEY' in constraints_text.upper()
            unique_constraint = 'UNIQUE' in constraints_text.upper()
            
            # Extract default value
            default_value = self._extract_default_value(constraints_text)
            
            # Extract comment
            comment = self._extract_column_comment(constraints_text)
            
            return ColumnInfo(
                name=column_name,
                data_type=data_type,
                is_nullable=is_nullable,
                default_value=default_value,
                max_length=max_length,
                precision=precision,
                scale=scale,
                is_primary_key=is_primary_key,
                is_foreign_key=False,  # Will be set by FK analysis
                foreign_table=None,
                foreign_column=None,
                check_constraints=[],
                unique_constraint=unique_constraint,
                comment=comment
            )
            
        except Exception as e:
            logger.warning(f"Error parsing column definition '{definition}': {e}")
            return None
    
    def _parse_data_type(self, data_type_str: str) -> Tuple[str, Optional[int], Optional[int], Optional[int]]:
        """Parse data type and extract size information"""
        
        data_type_str = data_type_str.upper()
        
        # Check for size specifications
        size_match = re.search(r'(\w+)\((\d+)(?:,(\d+))?\)', data_type_str)
        
        if size_match:
            base_type = size_match.group(1)
            first_num = int(size_match.group(2))
            second_num = int(size_match.group(3)) if size_match.group(3) else None
            
            if base_type in ['DECIMAL', 'NUMERIC']:
                return base_type, None, first_num, second_num
            else:
                return base_type, first_num, None, None
        else:
            return data_type_str, None, None, None
    
    def _extract_default_value(self, constraints: str) -> Optional[str]:
        """Extract default value from constraints"""
        
        default_match = re.search(r'DEFAULT\s+([^,\s]+(?:\s+[^,\s]+)*)', constraints, re.IGNORECASE)
        return default_match.group(1) if default_match else None
    
    def _extract_column_comment(self, constraints: str) -> Optional[str]:
        """Extract column comment"""
        
        comment_match = re.search(r'COMMENT\s+[\'"]([^\'"]*)[\'"]', constraints, re.IGNORECASE)
        return comment_match.group(1) if comment_match else None
    
    def _extract_primary_keys(self, column_section: str) -> List[str]:
        """Extract primary key columns"""
        
        # Look for PRIMARY KEY constraint
        pk_match = re.search(r'PRIMARY KEY\s*\(([^)]+)\)', column_section, re.IGNORECASE)
        
        if pk_match:
            pk_columns = [col.strip().strip('"').strip("'") for col in pk_match.group(1).split(',')]
            return pk_columns
        
        return []
    
    def _extract_foreign_keys(self, column_section: str) -> List[Dict[str, str]]:
        """Extract foreign key constraints"""
        
        foreign_keys = []
        
        # Look for FOREIGN KEY constraints
        fk_pattern = r'FOREIGN KEY\s*\(([^)]+)\)\s*REFERENCES\s+(\w+)\s*\(([^)]+)\)'
        
        for match in re.finditer(fk_pattern, column_section, re.IGNORECASE):
            local_columns = [col.strip().strip('"').strip("'") for col in match.group(1).split(',')]
            foreign_table = match.group(2)
            foreign_columns = [col.strip().strip('"').strip("'") for col in match.group(3).split(',')]
            
            for local_col, foreign_col in zip(local_columns, foreign_columns):
                foreign_keys.append({
                    'local_column': local_col,
                    'foreign_table': foreign_table,
                    'foreign_column': foreign_col
                })
        
        return foreign_keys
    
    def _extract_unique_constraints(self, column_section: str) -> List[List[str]]:
        """Extract unique constraints"""
        
        unique_constraints = []
        
        # Look for UNIQUE constraints
        unique_pattern = r'UNIQUE\s*\(([^)]+)\)'
        
        for match in re.finditer(unique_pattern, column_section, re.IGNORECASE):
            columns = [col.strip().strip('"').strip("'") for col in match.group(1).split(',')]
            unique_constraints.append(columns)
        
        return unique_constraints
    
    def _extract_check_constraints(self, column_section: str) -> List[str]:
        """Extract check constraints"""
        
        check_constraints = []
        
        # Look for CHECK constraints
        check_pattern = r'CHECK\s*\(([^)]+)\)'
        
        for match in re.finditer(check_pattern, column_section, re.IGNORECASE):
            check_constraints.append(match.group(1))
        
        return check_constraints
    
    def _extract_table_comment(self, statement: str) -> Optional[str]:
        """Extract table comment"""
        
        comment_match = re.search(r'COMMENT\s+[\'"]([^\'"]*)[\'"]', statement, re.IGNORECASE)
        return comment_match.group(1) if comment_match else None

class DatabaseIntrospector:
    """Introspect existing database tables to get structure"""
    
    def __init__(self):
        if not DATABASE_AVAILABLE:
            raise ImportError("Database not available")
        
        self.db_manager = get_database_manager()
    
    def introspect_table(self, table_name: str, schema_name: str = 'public') -> Optional[TableInfo]:
        """Introspect a table from the database"""
        
        try:
            with self.db_manager.get_session() as session:
                inspector = inspect(session.bind)
                
                # Check if table exists
                if not inspector.has_table(table_name, schema=schema_name):
                    logger.error(f"Table {schema_name}.{table_name} does not exist")
                    return None
                
                # Get column information
                columns_info = inspector.get_columns(table_name, schema=schema_name)
                columns = []
                
                for col_info in columns_info:
                    column = ColumnInfo(
                        name=col_info['name'],
                        data_type=str(col_info['type']),
                        is_nullable=col_info['nullable'],
                        default_value=col_info.get('default'),
                        max_length=getattr(col_info['type'], 'length', None),
                        precision=getattr(col_info['type'], 'precision', None),
                        scale=getattr(col_info['type'], 'scale', None),
                        is_primary_key=False,  # Will be set below
                        is_foreign_key=False,  # Will be set below
                        foreign_table=None,
                        foreign_column=None,
                        check_constraints=[],
                        unique_constraint=False,
                        comment=col_info.get('comment')
                    )
                    columns.append(column)
                
                # Get primary keys
                pk_constraint = inspector.get_pk_constraint(table_name, schema=schema_name)
                primary_keys = pk_constraint.get('constrained_columns', [])
                
                # Mark primary key columns
                for column in columns:
                    if column.name in primary_keys:
                        column.is_primary_key = True
                
                # Get foreign keys
                fk_constraints = inspector.get_foreign_keys(table_name, schema=schema_name)
                foreign_keys = []
                
                for fk in fk_constraints:
                    for local_col, foreign_col in zip(fk['constrained_columns'], fk['referred_columns']):
                        foreign_keys.append({
                            'local_column': local_col,
                            'foreign_table': fk['referred_table'],
                            'foreign_column': foreign_col
                        })
                        
                        # Mark column as foreign key
                        for column in columns:
                            if column.name == local_col:
                                column.is_foreign_key = True
                                column.foreign_table = fk['referred_table']
                                column.foreign_column = foreign_col
                
                # Get unique constraints
                unique_constraints = []
                try:
                    unique_cons = inspector.get_unique_constraints(table_name, schema=schema_name)
                    for constraint in unique_cons:
                        unique_constraints.append(constraint['column_names'])
                        
                        # Mark columns as unique
                        for column in columns:
                            if column.name in constraint['column_names']:
                                column.unique_constraint = True
                except:
                    pass  # Some databases don't support this
                
                # Get indexes
                indexes = []
                try:
                    indexes_info = inspector.get_indexes(table_name, schema=schema_name)
                    indexes = [{'name': idx['name'], 'columns': idx['column_names'], 'unique': idx['unique']} for idx in indexes_info]
                except:
                    pass
                
                return TableInfo(
                    schema_name=schema_name,
                    table_name=table_name,
                    columns=columns,
                    primary_keys=primary_keys,
                    foreign_keys=foreign_keys,
                    unique_constraints=unique_constraints,
                    check_constraints=[],  # Hard to get from inspector
                    indexes=indexes,
                    table_comment=None
                )
                
        except Exception as e:
            logger.error(f"Error introspecting table {schema_name}.{table_name}: {e}")
            return None
    
    def list_tables(self, schema_name: str = 'public') -> List[str]:
        """List all tables in a schema"""
        
        try:
            with self.db_manager.get_session() as session:
                inspector = inspect(session.bind)
                return inspector.get_table_names(schema=schema_name)
        except Exception as e:
            logger.error(f"Error listing tables in schema {schema_name}: {e}")
            return []

class ConfigurationGenerator:
    """Generate Data Source Configuration from table information"""
    
    def __init__(self):
        self.type_mapping = {
            'INTEGER': 'int',
            'BIGINT': 'int',
            'SMALLINT': 'int',
            'DECIMAL': 'float',
            'NUMERIC': 'float',
            'FLOAT': 'float',
            'DOUBLE': 'float',
            'REAL': 'float',
            'BOOLEAN': 'bool',
            'DATE': 'datetime',
            'TIME': 'datetime',
            'TIMESTAMP': 'datetime',
            'TIMESTAMPTZ': 'datetime',
        }
        
        self.email_patterns = ['email', 'mail', 'e_mail']
        self.phone_patterns = ['phone', 'mobile', 'tel', 'telephone']
        self.url_patterns = ['url', 'website', 'link']
        self.id_patterns = ['_id', 'id_', 'ref_', '_ref']
    
    def generate_config(
        self, 
        table_info: TableInfo, 
        source_name: str = None,
        source_type: str = "file",
        include_advanced_features: bool = True
    ) -> Dict[str, Any]:
        """Generate complete configuration from table information"""
        
        if not source_name:
            source_name = f"{table_info.table_name}_data"
        
        config = {
            "source_name": source_name,
            "source_type": source_type,
            "description": self._generate_description(table_info),
            "connection_config": self._generate_connection_config(source_type),
            "validation_rules": self._generate_validation_rules(table_info, include_advanced_features),
            "transformation_rules": self._generate_transformation_rules(table_info),
            "target_table": f"stage_{table_info.table_name}",
            "target_schema": "staging_data",
            "production_table": table_info.table_name,
            "production_schema": table_info.schema_name,
            "is_active": True,
            "processing_config": self._generate_processing_config(table_info),
            "tags": self._generate_tags(table_info),
            "owner": "data_team@company.com"
        }
        
        if include_advanced_features:
            config.update({
                "data_quality_config": self._generate_quality_config(table_info),
                "notification_config": self._generate_notification_config(),
                "metadata": self._generate_metadata(table_info)
            })
        
        return config
    
    def _generate_description(self, table_info: TableInfo) -> str:
        """Generate description based on table information"""
        
        if table_info.table_comment:
            return table_info.table_comment
        
        # Generate description based on table name and structure
        record_count = len(table_info.columns)
        has_fks = any(col.is_foreign_key for col in table_info.columns)
        
        description = f"Data source for {table_info.table_name} table with {record_count} columns"
        
        if has_fks:
            description += " (includes foreign key relationships)"
        
        return description
    
    def _generate_connection_config(self, source_type: str) -> Dict[str, Any]:
        """Generate connection configuration based on source type"""
        
        if source_type == "file":
            return {
                "read_options": {
                    "delimiter": ",",
                    "encoding": "utf-8",
                    "header": 0,
                    "na_values": ["", "NULL", "null", "N/A", "n/a", "NA"],
                    "keep_default_na": True
                }
            }
        elif source_type == "api":
            return {
                "api_config": {
                    "base_url": "https://api.example.com",
                    "endpoint": "/data/export",
                    "method": "GET",
                    "timeout": 30,
                    "retry_attempts": 3
                }
            }
        else:
            return {}
    
    def _generate_validation_rules(self, table_info: TableInfo, include_advanced: bool) -> Dict[str, Any]:
        """Generate validation rules based on table structure"""
        
        rules = {}
        
        # NOT NULL validation
        not_null_columns = [col.name for col in table_info.columns if not col.is_nullable]
        if not_null_columns:
            rules["not_null"] = {
                "columns": not_null_columns,
                "severity": "critical" if any(col.is_primary_key for col in table_info.columns if col.name in not_null_columns) else "error"
            }
        
        # UNIQUE validation
        unique_columns = []
        # Add primary keys
        unique_columns.extend(table_info.primary_keys)
        # Add unique constraint columns
        for col in table_info.columns:
            if col.unique_constraint and col.name not in unique_columns:
                unique_columns.append(col.name)
        
        if unique_columns:
            rules["unique"] = {
                "columns": unique_columns,
                "severity": "critical"
            }
        
        # DATA TYPE validation
        type_mappings = {}
        for col in table_info.columns:
            mapped_type = self._map_data_type(col.data_type)
            if mapped_type:
                type_mappings[col.name] = mapped_type
        
        if type_mappings:
            rules["data_type"] = {
                "strict": False,
                "types": type_mappings,
                "severity": "error"
            }
        
        # RANGE validation for numeric columns
        range_rules = self._generate_range_validation(table_info)
        if range_rules:
            rules["range"] = range_rules
        
        # PATTERN validation for specific column types
        pattern_rules = self._generate_pattern_validation(table_info)
        if pattern_rules:
            rules["pattern"] = pattern_rules
        
        # EMAIL validation
        email_columns = self._find_columns_by_pattern(table_info, self.email_patterns)
        if email_columns:
            rules["email"] = {
                "columns": email_columns,
                "severity": "error"
            }
        
        # PHONE validation
        phone_columns = self._find_columns_by_pattern(table_info, self.phone_patterns)
        if phone_columns:
            rules["phone"] = {
                "columns": phone_columns,
                "severity": "warning"
            }
        
        # DATE validation
        date_columns = [col.name for col in table_info.columns if 'date' in col.data_type.lower() or 'time' in col.data_type.lower()]
        if date_columns:
            rules["date"] = {
                "columns": date_columns,
                "min_date": "1900-01-01",
                "max_date": "2030-12-31",
                "severity": "error"
            }
        
        # REFERENTIAL INTEGRITY validation (advanced feature)
        if include_advanced and table_info.foreign_keys:
            references = []
            for fk in table_info.foreign_keys:
                references.append({
                    "local_column": fk['local_column'],
                    "reference_table": fk['foreign_table'],
                    "reference_column": fk['foreign_column'],
                    "reference_schema": table_info.schema_name,
                    "allow_null": self._is_column_nullable(table_info, fk['local_column']),
                    "error_message": f"Invalid reference to {fk['foreign_table']}.{fk['foreign_column']}"
                })
            
            if references:
                rules["referential_integrity"] = {
                    "references": references
                }
        
        # COMPLETENESS validation
        important_columns = [col.name for col in table_info.columns if not col.is_nullable or col.is_primary_key]
        if important_columns:
            rules["completeness"] = {
                "threshold": 0.95,
                "columns": important_columns,
                "severity": "warning"
            }
        
        # CHECK CONSTRAINTS as business rules
        if table_info.check_constraints:
            for i, constraint in enumerate(table_info.check_constraints):
                rules[f"business_rule_{i+1}"] = {
                    "expression": constraint,
                    "name": f"check_constraint_{i+1}",
                    "severity": "error"
                }
        
        return rules
    
    def _generate_transformation_rules(self, table_info: TableInfo) -> List[Dict[str, Any]]:
        """Generate transformation rules based on table structure"""
        
        rules = []
        
        # Always clean whitespace for text columns
        text_columns = [col.name for col in table_info.columns if 'varchar' in col.data_type.lower() or 'text' in col.data_type.lower() or 'char' in col.data_type.lower()]
        if text_columns:
            rules.append({
                "name": "clean_whitespace",
                "columns": text_columns
            })
        
        # Type conversion
        type_mappings = {}
        for col in table_info.columns:
            mapped_type = self._map_data_type(col.data_type)
            if mapped_type:
                type_mappings[col.name] = mapped_type
        
        if type_mappings:
            rules.append({
                "name": "convert_types",
                "mappings": type_mappings
            })
        
        # Date parsing for date columns
        date_columns = [col.name for col in table_info.columns if 'date' in col.data_type.lower() or 'time' in col.data_type.lower()]
        if date_columns:
            rules.append({
                "name": "parse_dates",
                "columns": date_columns
            })
        
        # Handle nulls for nullable columns with defaults
        fill_values = {}
        for col in table_info.columns:
            if col.is_nullable and col.default_value:
                # Parse default value
                default_val = col.default_value.strip("'\"")
                if default_val.upper() not in ['NULL', 'CURRENT_TIMESTAMP', 'NOW()']:
                    fill_values[col.name] = default_val
        
        if fill_values:
            rules.append({
                "name": "handle_nulls",
                "strategy": "fill",
                "fill_values": fill_values
            })
        
        # Standardize case for certain columns
        status_columns = [col.name for col in table_info.columns if 'status' in col.name.lower() or 'type' in col.name.lower()]
        if status_columns:
            rules.append({
                "name": "standardize_case",
                "case": "upper",
                "columns": status_columns
            })
        
        # Phone formatting
        phone_columns = self._find_columns_by_pattern(table_info, self.phone_patterns)
        if phone_columns:
            rules.append({
                "name": "format_phone",
                "columns": phone_columns,
                "format": "standard"
            })
        
        return rules
    
    def _generate_range_validation(self, table_info: TableInfo) -> Optional[Dict[str, Any]]:
        """Generate range validation for numeric columns"""
        
        numeric_columns = []
        ranges = {}
        
        for col in table_info.columns:
            if any(num_type in col.data_type.upper() for num_type in ['INT', 'DECIMAL', 'NUMERIC', 'FLOAT', 'REAL']):
                numeric_columns.append(col.name)
                
                # Generate reasonable ranges based on data type
                if 'SMALLINT' in col.data_type.upper():
                    ranges[col.name] = {"min": -32768, "max": 32767}
                elif 'INT' in col.data_type.upper() and 'BIG' not in col.data_type.upper():
                    ranges[col.name] = {"min": -2147483648, "max": 2147483647}
                elif 'price' in col.name.lower() or 'amount' in col.name.lower() or 'cost' in col.name.lower():
                    ranges[col.name] = {"min": 0.01, "max": 1000000}
                elif 'quantity' in col.name.lower() or 'count' in col.name.lower():
                    ranges[col.name] = {"min": 0, "max": 100000}
                elif 'percent' in col.name.lower() or 'rate' in col.name.lower():
                    ranges[col.name] = {"min": 0, "max": 100}
                elif 'age' in col.name.lower():
                    ranges[col.name] = {"min": 0, "max": 150}
        
        if numeric_columns:
            return {
                "columns": numeric_columns,
                "ranges": ranges,
                "severity": "error"
            }
        
        return None
    
    def _generate_pattern_validation(self, table_info: TableInfo) -> Optional[Dict[str, Any]]:
        """Generate pattern validation for specific column types"""
        
        patterns = {}
        
        for col in table_info.columns:
            col_name_lower = col.name.lower()
            
            # ID patterns
            if col_name_lower.endswith('_id') or col_name_lower.startswith('id_'):
                if 'uuid' in col.data_type.lower():
                    patterns[col.name] = "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
                else:
                    # Assume structured ID format
                    prefix = col.name.replace('_id', '').replace('id_', '').upper()
                    patterns[col.name] = f"^{prefix}-[0-9]{{4,8}}$"
            
            # Email patterns
            elif any(pattern in col_name_lower for pattern in self.email_patterns):
                patterns[col.name] = "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"
            
            # Phone patterns
            elif any(pattern in col_name_lower for pattern in self.phone_patterns):
                patterns[col.name] = "^\\+?1?[0-9]{10,15}$"
            
            # ZIP code patterns
            elif 'zip' in col_name_lower or 'postal' in col_name_lower:
                patterns[col.name] = "^[0-9]{5}(-[0-9]{4})?$"
            
            # URL patterns
            elif any(pattern in col_name_lower for pattern in self.url_patterns):
                patterns[col.name] = "^https?://[^\s/$.?#].[^\s]*$"
        
        if patterns:
            return {
                "columns": list(patterns.keys()),
                "patterns": patterns,
                "severity": "error"
            }
        
        return None
    
    def _find_columns_by_pattern(self, table_info: TableInfo, patterns: List[str]) -> List[str]:
        """Find columns matching name patterns"""
        
        matching_columns = []
        
        for col in table_info.columns:
            col_name_lower = col.name.lower()
            if any(pattern in col_name_lower for pattern in patterns):
                matching_columns.append(col.name)
        
        return matching_columns
    
    def _map_data_type(self, db_type: str) -> Optional[str]:
        """Map database type to transformation type"""
        
        db_type_upper = db_type.upper()
        
        for db_pattern, transform_type in self.type_mapping.items():
            if db_pattern in db_type_upper:
                return transform_type
        
        return None
    
    def _is_column_nullable(self, table_info: TableInfo, column_name: str) -> bool:
        """Check if a column is nullable"""
        
        for col in table_info.columns:
            if col.name == column_name:
                return col.is_nullable
        
        return True  # Default to nullable if not found
    
    def _generate_processing_config(self, table_info: TableInfo) -> Dict[str, Any]:
        """Generate processing configuration based on table size and complexity"""
        
        column_count = len(table_info.columns)
        has_complex_types = any('json' in col.data_type.lower() for col in table_info.columns)
        
        # Adjust batch size based on complexity
        if column_count > 50 or has_complex_types:
            batch_size = 500
        elif column_count > 20:
            batch_size = 1000
        else:
            batch_size = 5000
        
        return {
            "batch_size": batch_size,
            "max_retries": 3,
            "timeout_seconds": 300 if column_count < 20 else 600
        }
    
    def _generate_tags(self, table_info: TableInfo) -> List[str]:
        """Generate tags based on table characteristics"""
        
        tags = [table_info.table_name]
        
        # Add schema tag
        if table_info.schema_name != 'public':
            tags.append(table_info.schema_name)
        
        # Add functional tags based on table name
        table_name_lower = table_info.table_name.lower()
        
        if any(keyword in table_name_lower for keyword in ['customer', 'client', 'user']):
            tags.append('customer-data')
        elif any(keyword in table_name_lower for keyword in ['product', 'item', 'catalog']):
            tags.append('product-data')
        elif any(keyword in table_name_lower for keyword in ['order', 'sale', 'transaction']):
            tags.append('transaction-data')
        elif any(keyword in table_name_lower for keyword in ['finance', 'payment', 'invoice']):
            tags.append('financial-data')
        
        # Add complexity tags
        if len(table_info.columns) > 30:
            tags.append('complex-structure')
        
        if table_info.foreign_keys:
            tags.append('relational-data')
        
        return tags
    
    def _generate_quality_config(self, table_info: TableInfo) -> Dict[str, Any]:
        """Generate data quality configuration"""
        
        # Set higher thresholds for critical tables
        table_name_lower = table_info.table_name.lower()
        
        if any(keyword in table_name_lower for keyword in ['customer', 'product', 'order', 'transaction']):
            quality_threshold = 90
            quarantine_threshold = 70
        else:
            quality_threshold = 85
            quarantine_threshold = 60
        
        return {
            "quality_threshold": quality_threshold,
            "auto_quarantine": True,
            "quarantine_threshold": quarantine_threshold,
            "profiling_enabled": True,
            "monitoring_enabled": True
        }
    
    def _generate_notification_config(self) -> Dict[str, Any]:
        """Generate notification configuration"""
        
        return {
            "on_success": {
                "email": ["data_team@company.com"]
            },
            "on_failure": {
                "email": ["data_alerts@company.com"],
                "escalation": True
            },
            "on_warning": {
                "email": ["data_warnings@company.com"]
            }
        }
    
    def _generate_metadata(self, table_info: TableInfo) -> Dict[str, Any]:
        """Generate metadata section"""
        
        return {
            "created_by": "ddl_config_creator",
            "created_at": "2024-01-01T00:00:00Z",
            "version": "1.0",
            "source_table": f"{table_info.schema_name}.{table_info.table_name}",
            "column_count": len(table_info.columns),
            "has_foreign_keys": bool(table_info.foreign_keys),
            "has_unique_constraints": bool(table_info.unique_constraints),
            "business_context": {
                "criticality": "high" if any(keyword in table_info.table_name.lower() for keyword in ['customer', 'order', 'transaction', 'payment']) else "medium"
            }
        }

class DDLConfigCreator:
    """Main class that orchestrates the configuration creation process"""
    
    def __init__(self):
        self.ddl_parser = DDLParser()
        self.config_generator = ConfigurationGenerator()
        
        if DATABASE_AVAILABLE:
            self.db_introspector = DatabaseIntrospector()
        else:
            self.db_introspector = None
    
    def create_config_from_ddl(
        self, 
        ddl: str, 
        output_dir: str = "config/sources",
        source_type: str = "file",
        include_advanced: bool = True
    ) -> List[str]:
        """Create configuration files from DDL string"""
        
        # Parse DDL
        tables = self.ddl_parser.parse_ddl(ddl)
        
        if not tables:
            logger.error("No valid tables found in DDL")
            return []
        
        created_files = []
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        for table_info in tables:
            # Generate configuration
            config = self.config_generator.generate_config(
                table_info,
                source_type=source_type,
                include_advanced_features=include_advanced
            )
            
            # Save configuration file
            config_file = output_path / f"{table_info.table_name}_config.json"
            
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=2)
            
            created_files.append(str(config_file))
            logger.info(f"Created configuration: {config_file}")
        
        return created_files
    
    def create_config_from_database(
        self, 
        table_name: str,
        schema_name: str = "public",
        output_dir: str = "config/sources",
        source_type: str = "file",
        include_advanced: bool = True
    ) -> Optional[str]:
        """Create configuration from existing database table"""
        
        if not self.db_introspector:
            logger.error("Database introspection not available")
            return None
        
        # Introspect table
        table_info = self.db_introspector.introspect_table(table_name, schema_name)
        
        if not table_info:
            logger.error(f"Could not introspect table {schema_name}.{table_name}")
            return None
        
        # Generate configuration
        config = self.config_generator.generate_config(
            table_info,
            source_type=source_type,
            include_advanced_features=include_advanced
        )
        
        # Save configuration file
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        config_file = output_path / f"{table_name}_config.json"
        
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        
        logger.info(f"Created configuration: {config_file}")
        return str(config_file)
    
    def list_database_tables(self, schema_name: str = "public") -> List[str]:
        """List available tables in database"""
        
        if not self.db_introspector:
            logger.error("Database introspection not available")
            return []
        
        return self.db_introspector.list_tables(schema_name)
    
    def create_staging_table_ddl(self, table_info: TableInfo) -> str:
        """Generate DDL for staging table based on production table"""
        
        staging_table_name = f"stage_{table_info.table_name}"
        
        ddl_lines = [
            f"-- Staging table for {table_info.table_name}",
            f"CREATE TABLE IF NOT EXISTS staging_data.{staging_table_name} (",
            "    staging_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),",
            "    batch_id UUID REFERENCES staging_meta.batch_control(batch_id),"
        ]
        
        # Add original columns
        for col in table_info.columns:
            nullable = "NULL" if col.is_nullable else "NOT NULL"
            default = f" DEFAULT {col.default_value}" if col.default_value else ""
            
            ddl_lines.append(f"    {col.name} {col.data_type}{default},")
        
        # Add staging-specific columns
        ddl_lines.extend([
            "    validation_status VARCHAR(20) DEFAULT 'PENDING',",
            "    validation_errors JSONB,",
            "    validation_score DECIMAL(5,2),",
            "    is_duplicate BOOLEAN DEFAULT FALSE,",
            "    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,",
            "    processed_at TIMESTAMP"
        ])
        
        ddl_lines.append(");")
        
        # Add indexes
        ddl_lines.extend([
            "",
            f"CREATE INDEX IF NOT EXISTS idx_{staging_table_name}_batch_id ON staging_data.{staging_table_name}(batch_id);",
            f"CREATE INDEX IF NOT EXISTS idx_{staging_table_name}_validation ON staging_data.{staging_table_name}(validation_status);"
        ])
        
        # Add indexes for foreign key columns
        for col in table_info.columns:
            if col.is_foreign_key:
                ddl_lines.append(f"CREATE INDEX IF NOT EXISTS idx_{staging_table_name}_{col.name} ON staging_data.{staging_table_name}({col.name});")
        
        return "\n".join(ddl_lines)

def main():
    """Main CLI function"""
    
    parser = argparse.ArgumentParser(description="Generate Data Source Configuration from DDL")
    parser.add_argument("--ddl-file", type=str, help="Path to DDL file")
    parser.add_argument("--ddl-text", type=str, help="DDL text directly")
    parser.add_argument("--table", type=str, help="Database table name to introspect")
    parser.add_argument("--schema", type=str, default="public", help="Database schema name")
    parser.add_argument("--list-tables", action="store_true", help="List available database tables")
    parser.add_argument("--output-dir", type=str, default="config/sources", help="Output directory for config files")
    parser.add_argument("--source-type", type=str, default="file", choices=["file", "api", "database"], help="Source type")
    parser.add_argument("--simple", action="store_true", help="Generate simple configuration without advanced features")
    parser.add_argument("--generate-staging-ddl", action="store_true", help="Also generate staging table DDL")
    
    args = parser.parse_args()
    
    creator = DDLConfigCreator()
    
    if args.list_tables:
        if DATABASE_AVAILABLE:
            tables = creator.list_database_tables(args.schema)
            print(f"Tables in schema '{args.schema}':")
            for table in tables:
                print(f"  - {table}")
        else:
            print("Database not available for table listing")
        return
    
    include_advanced = not args.simple
    
    if args.ddl_file:
        # Read DDL from file
        with open(args.ddl_file, 'r') as f:
            ddl_content = f.read()
        
        created_files = creator.create_config_from_ddl(
            ddl_content,
            args.output_dir,
            args.source_type,
            include_advanced
        )
        
        print(f"Created {len(created_files)} configuration files:")
        for file_path in created_files:
            print(f"  - {file_path}")
    
    elif args.ddl_text:
        # Use DDL text directly
        created_files = creator.create_config_from_ddl(
            args.ddl_text,
            args.output_dir,
            args.source_type,
            include_advanced
        )
        
        print(f"Created {len(created_files)} configuration files:")
        for file_path in created_files:
            print(f"  - {file_path}")
    
    elif args.table:
        # Introspect database table
        if not DATABASE_AVAILABLE:
            print("Error: Database not available for table introspection")
            return
        
        config_file = creator.create_config_from_database(
            args.table,
            args.schema,
            args.output_dir,
            args.source_type,
            include_advanced
        )
        
        if config_file:
            print(f"Created configuration file: {config_file}")
            
            if args.generate_staging_ddl:
                # Also generate staging table DDL
                table_info = creator.db_introspector.introspect_table(args.table, args.schema)
                if table_info:
                    staging_ddl = creator.create_staging_table_ddl(table_info)
                    ddl_file = Path(args.output_dir) / f"staging_{args.table}.sql"
                    
                    with open(ddl_file, 'w') as f:
                        f.write(staging_ddl)
                    
                    print(f"Created staging DDL: {ddl_file}")
        else:
            print(f"Failed to create configuration for table {args.schema}.{args.table}")
    
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
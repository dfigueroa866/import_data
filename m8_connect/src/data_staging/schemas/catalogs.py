# src/data_staging/schemas/catalogs.py
"""Catalog definitions Pydantic schemas."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class CatalogDefinitionPayload(BaseModel):
    name: str
    label: str
    target_schema: str = "public"
    target_table: Optional[str] = None
    config_file: Optional[str] = None
    is_active: bool = True
    required_columns: List[str] = Field(default_factory=list)
    optional_columns: List[str] = Field(default_factory=list)
    required_mapping_columns: List[str] = Field(default_factory=list)
    unique_keys: List[str] = Field(default_factory=list)
    ignored_file_headers: List[str] = Field(default_factory=list)
    non_mappable_targets: List[str] = Field(default_factory=list)
    column_aliases: Dict[str, List[str]] = Field(default_factory=dict)
    enums: Dict[str, List[str]] = Field(default_factory=dict)
    defaults: Dict[str, Any] = Field(default_factory=dict)
    validation_hints: List[str] = Field(default_factory=list)

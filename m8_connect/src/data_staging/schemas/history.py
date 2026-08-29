"""Pydantic schemas for history definition admin API."""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ProcessTypeConfig(BaseModel):
    key: str = Field(..., min_length=1, description="Identificador interno (p. ej. Weekly)")
    label: str = Field(..., min_length=1, description="Texto en el dropdown del paso 1")
    granularity: str = Field(..., min_length=1, description="Valor en columna granularity (p. ej. week)")
    date_truncate: str = Field(..., min_length=2, description="Intervalo Polars dt.truncate (p. ej. 1w)")


class HistoryDefinitionPayload(BaseModel):
    name: Optional[str] = None
    label: Optional[str] = None
    unique_keys: List[str] = Field(default_factory=list)
    required_mapping_columns: List[str] = Field(default_factory=list)
    optional_columns: List[str] = Field(default_factory=list)
    non_mappable_targets: List[str] = Field(default_factory=list)
    ignored_file_headers: List[str] = Field(default_factory=list)
    sku_mapping_targets: List[str] = Field(default_factory=list)
    logical_columns: List[str] = Field(default_factory=list)
    sales_channel_default: str = "SELL_IN"
    process_types: List[ProcessTypeConfig] = Field(default_factory=list)
    validation_hints: List[str] = Field(default_factory=list)
    defaults: Dict[str, str] = Field(default_factory=dict)

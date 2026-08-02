"""Pydantic schemas for incremental load API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class IncrementalSchedulePayload(BaseModel):
    enabled: bool = True
    cron_expression: str = "0 22 * * 0"
    timezone: str = "America/Mexico_City"
    retention_years: int = Field(3, ge=1, le=50)


class IncrementalScheduleResponse(IncrementalSchedulePayload):
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None


class IncrementalOrgProfilePayload(BaseModel):
    organization_id: str
    organization_name: str
    enabled: bool = True
    source_path: str = Field("", description="Ruta origen de archivos; se autocompleta si vacío")
    notification_emails: List[str] = Field(default_factory=list)
    default_granularity: Optional[str] = None


class IncrementalOrgProfileResponse(IncrementalOrgProfilePayload):
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class IncrementalOrgTablePayload(BaseModel):
    load_kind: str
    catalog_slug: Optional[str] = None
    enabled: bool = True
    granularity: Optional[str] = None


class IncrementalRunResponse(BaseModel):
    run_id: str
    organization_id: str
    organization_name: Optional[str] = None
    load_date: date
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    status: str
    error_message: Optional[str] = None
    total_processed: int = 0
    total_inserted: int = 0
    total_updated: int = 0
    total_rejected: int = 0
    batch_ids: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class IncrementalTriggerPayload(BaseModel):
    organization_id: Optional[str] = None


class IncrementalRunsDeletePayload(BaseModel):
    run_ids: List[str] = Field(..., min_length=1, max_length=100)

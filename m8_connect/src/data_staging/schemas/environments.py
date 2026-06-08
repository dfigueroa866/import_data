# src/data_staging/schemas/environments.py
"""Environment profile Pydantic schemas."""

from typing import Optional
from pydantic import BaseModel

class EnvironmentProfile(BaseModel):
    name: str               # Friendly label
    db_url: str             # Full PostgreSQL connection string
    description: Optional[str] = ""
    color: Optional[str] = "#6366f1"   # UI accent colour (hex)

class EnvironmentProfileDB(EnvironmentProfile):
    id: str
    is_active: bool = False
    created_at: str
    last_tested: Optional[str] = None
    test_status: Optional[str] = None  # "ok" | "error" | None

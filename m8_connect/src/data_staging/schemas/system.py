# src/data_staging/schemas/system.py
"""System related Pydantic schemas."""

from pydantic import BaseModel

class DatabaseConfig(BaseModel):
    database_url: str

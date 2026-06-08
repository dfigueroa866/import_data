# src/data_staging/schemas/upload.py
"""File upload and mapping Pydantic schemas."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel

class BulkDeleteRequest(BaseModel):
    batch_ids: List[str] = []

class BulkDeleteFiltersRequest(BaseModel):
    status: Optional[str] = None
    search: Optional[str] = None

class ColumnMapping(BaseModel):
    """Mapeo de columnas para transformación de datos."""
    source: Optional[str] = None  # Nombre de columna en el archivo
    default: Optional[Any] = None  # Valor por defecto si no existe o es null

class ProcessRequest(BaseModel):
    """Request para procesar un batch con configuración avanzada."""
    columns: Optional[List[str]] = None  # Lista de columnas a procesar
    column_mapping: Optional[Dict[str, ColumnMapping]] = None  # Mapeo de columnas
    direct_load: bool = False  # Si es true, carga directamente a producción (bypass staging)
    auto_production: bool = False  # Si es true, encola PROMOTE_BATCH al final automáticamente

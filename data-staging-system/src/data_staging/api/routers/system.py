
import os
import logging
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from data_staging.config import settings
from data_staging.database import get_database_manager, get_database_session

router = APIRouter(
    prefix="/system",
    tags=["system"],
    responses={404: {"description": "Not found"}},
)

logger = logging.getLogger(__name__)

class DatabaseConfig(BaseModel):
    database_url: str
    supabase_url: Optional[str] = None
    supabase_anon_key: Optional[str] = None
    supabase_service_role_key: Optional[str] = None

@router.get("/config/database")
async def get_database_config():
    """Get current database configuration (masked)."""
    db_url = settings.database_url
    # Mask password
    if db_url:
        try:
            # Simple masking for display
            parts = db_url.split("@")
            if len(parts) > 1:
                prefix = parts[0].split(":")
                if len(prefix) > 2:
                     # postgresql://user:pass
                     masked_prefix = f"{prefix[0]}:{prefix[1]}:******"
                     db_url = f"{masked_prefix}@{parts[1]}"
        except Exception:
            pass

    return {
        "database_url": db_url,
        "supabase_url": settings.supabase_url,
        "is_supabase": settings.is_supabase,
        "environment": settings.environment
    }

@router.post("/config/database")
async def update_database_config(config: DatabaseConfig):
    """Update database configuration in .env file and reload."""
    try:
        # 1. Update .env file
        env_path = Path(__file__).parent.parent.parent.parent / '.env'
        
        # Read existing content
        lines = []
        if env_path.exists():
            with open(env_path, 'r') as f:
                lines = f.readlines()
        
        # Update or add keys
        new_lines = []
        keys_updated = set()
        
        updates = {
            "DATABASE_URL": config.database_url,
        }
        if config.supabase_url:
            updates["SUPABASE_URL"] = config.supabase_url
        if config.supabase_anon_key:
            updates["SUPABASE_ANON_KEY"] = config.supabase_anon_key
        if config.supabase_service_role_key:
            updates["SUPABASE_SERVICE_ROLE_KEY"] = config.supabase_service_role_key
            
        for line in lines:
            key = line.split('=')[0].strip() if '=' in line else None
            if key in updates:
                new_lines.append(f"{key}={updates[key]}\n")
                keys_updated.add(key)
            else:
                new_lines.append(line)
        
        # Add missing keys
        for key, value in updates.items():
            if key not in keys_updated and value:
                new_lines.append(f"\n{key}={value}\n")
        
        # Write back
        with open(env_path, 'w') as f:
            f.writelines(new_lines)
            
        # 2. Reload settings
        # Force reload environment variables
        os.environ["DATABASE_URL"] = config.database_url
        if config.supabase_url:
            os.environ["SUPABASE_URL"] = config.supabase_url
            
        settings.reload()
        
        # 3. Recreate database engine
        db_manager = get_database_manager()
        db_manager.recreate_engine()
        
        return {"status": "success", "message": "Database configuration updated and reloaded"}
        
    except Exception as e:
        logger.error(f"Failed to update config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# NEW ENDPOINTS FOR UPLOAD WIZARD
# ============================================================================

@router.get("/schemas")
async def get_schemas(db: Session = Depends(get_database_session)):
    """
    Get list of available database schemas for the upload wizard.
    Excludes system schemas (pg_*, information_schema).
    """
    try:
        from sqlalchemy import text
        
        if settings.is_clickhouse:
            query = text("""
                SELECT name 
                FROM system.databases 
                WHERE name NOT IN ('system', 'INFORMATION_SCHEMA', 'information_schema')
                ORDER BY name
            """)
        else:
            query = text("""
                SELECT schema_name 
                FROM information_schema.schemata 
                WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'pg_toast', 'pg_temp_1', 'pg_toast_temp_1')
                AND schema_name NOT LIKE 'pg_temp_%'
                AND schema_name NOT LIKE 'pg_toast_temp_%'
                ORDER BY schema_name
            """)
        
        result = db.execute(query).fetchall()
        schemas = [row[0] for row in result]
        
        logger.info(f"Retrieved {len(schemas)} schemas")
        return {"schemas": schemas, "count": len(schemas)}
        
    except Exception as e:
        logger.error(f"Error retrieving schemas: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve schemas: {str(e)}")


@router.get("/tables")
async def get_tables(
    schema: str,
    db: Session = Depends(get_database_session)
):
    """
    Get list of tables in a specific schema for the upload wizard.
    """
    try:
        from sqlalchemy import text
        
        if settings.is_clickhouse:
            query = text("""
                SELECT 
                    name as table_name,
                    (SELECT COUNT(*) 
                     FROM system.columns 
                     WHERE database = :schema 
                     AND table = t.name) as column_count
                FROM system.tables t
                WHERE database = :schema
                ORDER BY name
            """)
        else:
            query = text("""
                SELECT 
                    table_name,
                    (SELECT COUNT(*) 
                     FROM information_schema.columns 
                     WHERE table_schema = :schema 
                     AND table_name = t.table_name) as column_count
                FROM information_schema.tables t
                WHERE table_schema = :schema
                AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """)
        
        result = db.execute(query, {"schema": schema}).fetchall()
        
        tables = [
            {
                "table_name": row[0],
                "column_count": row[1]
            }
            for row in result
        ]
        
        logger.info(f"Retrieved {len(tables)} tables from schema '{schema}'")
        return {"schema": schema, "tables": tables, "count": len(tables)}
        
    except Exception as e:
        logger.error(f"Error retrieving tables for schema '{schema}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve tables: {str(e)}")


@router.get("/catalog-tables")
async def get_catalog_tables():
    """
    List catalog tables (skus, location) for the catalog upload wizard.
    Duplicated under /upload for convenience; kept here for clients hitting system API.
    """
    try:
        from data_staging.catalog.catalog_registry import list_catalog_tables

        return {"tables": list_catalog_tables()}
    except Exception as e:
        logger.error(f"Error listing catalog tables: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list catalog tables: {str(e)}")


@router.get("/table-columns")
async def get_table_columns(
    schema: str = Query(..., description="The database schema (e.g., public)"),
    table: str = Query(..., description="The table name"),
    db: Session = Depends(get_database_session),
):
    """Get columns for a specific table in any schema."""
    try:
        from sqlalchemy import text

        query = text("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = :schema
            AND table_name = :table
            ORDER BY ordinal_position
        """)

        result = db.execute(query, {"schema": schema, "table": table}).fetchall()

        if not result:
            return {
                "columns": [],
                "error": f"Table {schema}.{table} not found or has no columns",
            }

        columns = [
            {
                "name": row.column_name,
                "type": row.data_type,
                "nullable": row.is_nullable == "YES",
                "default": row.column_default,
            }
            for row in result
        ]

        return {"columns": columns, "schema": schema, "table": table}

    except Exception as e:
        logger.error(f"Error fetching columns for {schema}.{table}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


"""
Main FastAPI application for M8 Connect.
"""

import logging
import sys
import os
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Add src to path for imports
current_dir = Path(__file__).parent
src_dir = current_dir.parent.parent
sys.path.insert(0, str(src_dir))

from data_staging.config import settings
from data_staging.database import get_database_manager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management."""
    # Startup
    logger.info("Starting M8 Connect API")
    
    # Test database connection
    try:
        db_manager = get_database_manager()
        connection_info = db_manager.test_connection()
        if connection_info.get("status") == "connected":
            logger.info(f"Database connected: {connection_info.get('database')}")
        else:
            logger.warning("Database connection failed")
    except Exception as e:
        logger.error(f"Database connection error: {e}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down M8 Connect API")


# Create FastAPI application
app = FastAPI(
    title="M8 Connect",
    description="M8 Connect — plataforma de ingesta, validación y promoción de datos",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers with error handling
try:
    from data_staging.api.v1 import upload
    app.include_router(upload.router, prefix="/api/v1/upload", tags=["Upload"])
    logger.info("Upload router included")
except Exception as e:
    logger.error(f"Failed to import upload router: {e}", exc_info=True)

try:
    from data_staging.api.routers.monitoring import router as monitoring_router
    app.include_router(monitoring_router, prefix="/api/v1")
    logger.info("Monitoring router included")
except ImportError as e:
    logger.warning(f"Could not import monitoring router: {e}")

try:
    from data_staging.api.routers.system import router as system_router
    app.include_router(system_router, prefix="/api/v1")
    logger.info("System router included")
except ImportError as e:
    logger.warning(f"Could not import system router: {e}")

try:
    from data_staging.api.routers.auth import router as auth_router
    app.include_router(auth_router, prefix="/api/v1")
    logger.info("Auth router included")
except Exception as e:
    logger.error(f"Could not import auth router: {e}", exc_info=True)

try:
    from data_staging.api.routers.catalogs import router as catalogs_router
    app.include_router(catalogs_router, prefix="/api/v1")
    logger.info("Catalogs admin router included")
except Exception as e:
    logger.error(f"Could not import catalogs router: {e}", exc_info=True)

try:
    from data_staging.api.routers.history import router as history_router
    app.include_router(history_router, prefix="/api/v1")
    logger.info("History admin router included")
except Exception as e:
    logger.error(f"Could not import history router: {e}", exc_info=True)

try:
    from data_staging.api.routers.roles import router as roles_router
    app.include_router(roles_router, prefix="/api/v1")
    logger.info("Roles router included")
except Exception as e:
    logger.error(f"Could not import roles router: {e}", exc_info=True)

try:
    from data_staging.api.routers.incremental import router as incremental_router
    app.include_router(incremental_router, prefix="/api/v1")
    logger.info("Incremental router included")
except Exception as e:
    logger.warning(f"Could not import incremental router: {e}")

try:
    from data_staging.api.v1.environments import router as environments_router
    app.include_router(environments_router, prefix="/api/v1", tags=["Environments"])
    logger.info("Environments router included")
except ImportError as e:
    logger.warning(f"Could not import environments router: {e}")


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "M8 Connect",
        "version": "2.0.0",
        "status": "operational",
        "timestamp": datetime.now().isoformat(),
        "endpoints": {
            "docs": "/docs",
            "health": "/health",
            "upload": "/api/v1/upload/file",
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        # Test database connection
        db_manager = get_database_manager()
        db_info = db_manager.test_connection()
        
        is_healthy = db_info.get("status") == "connected"
        
        return {
            "status": "healthy" if is_healthy else "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "version": "2.0.0",
            "database": {
                "status": "connected" if is_healthy else "disconnected",
                "type": db_info.get("database_type", "unknown")
            },
            "environment": settings.ENVIRONMENT
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            }
        )


@app.get("/api/v1/sources")
async def list_sources():
    """List configured data sources"""
    try:
        from data_staging.database import get_database_manager
        from sqlalchemy import text
        
        db_manager = get_database_manager()
        
        with db_manager.get_session() as session:
            result = session.execute(text("""
                SELECT source_id, source_name, source_type, target_table, is_active, created_at
                FROM staging_meta.data_sources
                ORDER BY created_at DESC
            """))
            
            sources = []
            for row in result:
                sources.append({
                    "source_id": row.source_id,
                    "source_name": row.source_name,
                    "source_type": row.source_type,
                    "target_table": row.target_table,
                    "is_active": row.is_active,
                    "created_at": row.created_at.isoformat() if row.created_at else None
                })
        
        return {
            "sources": sources,
            "total": len(sources)
        }
        
    except Exception as e:
        logger.error(f"Error listing sources: {e}")
        return {
            "sources": [],
            "total": 0,
            "error": str(e)
        }


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": str(exc) if settings.DEBUG else "An unexpected error occurred",
            "timestamp": datetime.now().isoformat()
        }
    )


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "data_staging.api.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
        workers=1
    )

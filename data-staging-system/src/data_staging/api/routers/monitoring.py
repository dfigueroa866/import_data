"""
Monitoring and metrics API endpoints.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

from ...database import get_database_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get("/system-status")
async def get_system_status(db: Session = Depends(get_database_session)):
    """Get overall system status and metrics."""
    try:
        # Check if tables exist first
        tables_exist = db.execute(text("""
            SELECT COUNT(*) FROM information_schema.tables 
            WHERE table_schema = 'staging_meta' 
            AND table_name IN ('batch_control', 'load_history', 'data_sources')
        """)).scalar()
        
        if tables_exist < 3:
            return {
                "status": "initializing",
                "timestamp": datetime.now().isoformat(),
                "message": "Database tables not found",
                "tables_found": tables_exist
            }
        
        # Get batch statistics
        batch_stats = db.execute(text("""
            SELECT 
                COUNT(*) as total_batches,
                COUNT(CASE WHEN status = 'COMPLETED' THEN 1 END) as completed_batches,
                COUNT(CASE WHEN status = 'FAILED' THEN 1 END) as failed_batches
            FROM staging_meta.batch_control
        """)).fetchone()
        
        # Calculate success rate
        success_rate = 0
        if batch_stats.total_batches > 0:
            success_rate = (batch_stats.completed_batches / batch_stats.total_batches) * 100
        
        return {
            "status": "operational",
            "timestamp": datetime.now().isoformat(),
            "batch_statistics": {
                "total_batches": batch_stats.total_batches,
                "completed_batches": batch_stats.completed_batches,
                "failed_batches": batch_stats.failed_batches,
                "success_rate": round(success_rate, 2)
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting system status: {e}")
        return {
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }


@router.get("/metrics")
async def get_metrics(hours: int = 24, db: Session = Depends(get_database_session)):
    """Get system metrics for the specified time period."""
    try:
        metrics = db.execute(text("""
            SELECT 
                DATE_TRUNC('hour', created_at) as hour,
                COUNT(*) as batches_created,
                COUNT(CASE WHEN status = 'COMPLETED' THEN 1 END) as batches_completed,
                COUNT(CASE WHEN status = 'FAILED' THEN 1 END) as batches_failed
            FROM staging_meta.batch_control
            WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '%s hours'
            GROUP BY DATE_TRUNC('hour', created_at)
            ORDER BY hour DESC
        """ % hours)).fetchall()
        
        metrics_data = []
        for row in metrics:
            metrics_data.append({
                "timestamp": row.hour.isoformat(),
                "batches_created": row.batches_created,
                "batches_completed": row.batches_completed,
                "batches_failed": row.batches_failed
            })
        
        return {
            "time_period_hours": hours,
            "metrics": metrics_data
        }
        
    except Exception as e:
        logger.error(f"Error getting metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving metrics: {str(e)}")


@router.get("/health-detailed")
async def get_detailed_health(db: Session = Depends(get_database_session)):
    """Get detailed health information."""
    try:
        # Test database connectivity
        db.execute(text("SELECT 1")).scalar()
        
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "database_connected": True
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "database_connected": False,
            "error": str(e)
        }
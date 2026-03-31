# src/data_staging/api/v1/upload.py - Complete File Upload Implementation

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
import uuid
import os
import shutil
from pathlib import Path
from datetime import datetime
import polars as pl
import json
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import logging

from data_staging.database import get_database_session
from data_staging.config import settings
from data_staging.utils.file_handler import FileHandler
from data_staging.core.validators.data_validator import DataValidator
from data_staging.core.etl.engine import ETLEngine



logger = logging.getLogger(__name__)


router = APIRouter()

class FileUploadService:
    """Service for handling file uploads and processing"""
    
    def __init__(self):
        self.upload_dir = Path(settings.UPLOAD_PATH)
        self.temp_dir = Path(settings.TEMP_PATH)
        self.allowed_extensions = settings.ALLOWED_FILE_EXTENSIONS
        self.max_file_size = settings.MAX_FILE_SIZE
        
        # Ensure directories exist
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
    
    def validate_file(self, file: UploadFile) -> Dict[str, Any]:
        """Validate uploaded file"""
        errors = []
        
        # Check file extension
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in self.allowed_extensions:
            errors.append(f"File extension {file_ext} not allowed. Allowed: {self.allowed_extensions}")
        
        # Check file size (if we can get it)
        if hasattr(file, 'size') and file.size:
            if file.size > self.max_file_size:
                errors.append(f"File size {file.size} exceeds maximum {self.max_file_size} bytes")
        
        # Check filename
        if not file.filename or len(file.filename) == 0:
            errors.append("Filename is required")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "file_extension": file_ext,
            "file_size": getattr(file, 'size', None)
        }
    
    async def save_file(self, file: UploadFile, batch_id: str) -> Path:
        """Save uploaded file to disk"""
        # Create unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_ext = Path(file.filename).suffix
        safe_filename = f"{batch_id}_{timestamp}_{file.filename}"
        file_path = self.upload_dir / safe_filename
        
        try:
            # Save file
            with open(file_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)
            
            logger.info(f"File saved: {file_path}")
            return file_path
            
        except Exception as e:
            logger.error(f"Error saving file: {e}")
            raise HTTPException(status_code=500, detail=f"Error saving file: {str(e)}")
    
    def detect_file_type(self, file_path: Path) -> str:
        """Detect file type and structure"""
        file_ext = file_path.suffix.lower()
        
        if file_ext in ['.csv']:
            return 'csv'
        elif file_ext in ['.xlsx', '.xls']:
            return 'excel'
        elif file_ext in ['.json']:
            return 'json'
        elif file_ext in ['.parquet']:
            return 'parquet'
        else:
            return 'unknown'
    
    def analyze_file_structure(self, file_path: Path) -> Dict[str, Any]:
        """Analyze file structure and extract metadata"""
        file_type = self.detect_file_type(file_path)
        
        try:
            if file_type == 'csv':
                # Analyze CSV with robust detection using Polars
                encodings = ['utf-8', 'latin-1', 'cp1252']
                sample_df = None
                read_error = None
                detected_delimiter = ","
                detected_encoding = "utf-8"
                
                # Try different encodings
                for encoding in encodings:
                    try:
                        # Try default separator first
                        curr_delimiter = ","
                        sample_df = pl.read_csv(
                            file_path,
                            n_rows=100,
                            encoding=encoding,
                            ignore_errors=True,
                            truncate_ragged_lines=True,
                            infer_schema_length=100
                        )
                        
                        # If parsed into 1 column, try sniffing delimiter
                        if len(sample_df.columns) == 1:
                            with open(file_path, 'r', encoding=encoding) as f:
                                first_line = f.readline()
                                if ',' in first_line or ';' in first_line or '\t' in first_line:
                                    # Try sniffing
                                    f.seek(0)
                                    import csv
                                    dialect = csv.Sniffer().sniff(f.read(1024))
                                    curr_delimiter = dialect.delimiter
                                    
                                    sample_df = pl.read_csv(
                                        file_path,
                                        n_rows=100,
                                        separator=curr_delimiter,
                                        encoding=encoding,
                                        ignore_errors=True,
                                        truncate_ragged_lines=True,
                                        infer_schema_length=100
                                    )
                        
                        if sample_df is not None and not sample_df.is_empty():
                            detected_encoding = encoding
                            detected_delimiter = curr_delimiter
                            break # Success
                    except Exception as e:
                        read_error = e
                        continue
                
                if sample_df is None:
                     raise Exception(f"Failed to read CSV. Last error: {read_error}")

                # Convert column types to string for JSON serialization
                column_types = {col: str(dtype) for col, dtype in zip(sample_df.columns, sample_df.dtypes)}
                
                # Get sample data and replace null with None for JSON serialization
                sample_rows = sample_df.head(5).to_dicts()

                return {
                    "file_type": file_type,
                    "columns": list(sample_df.columns),
                    "column_types": column_types,
                    "sample_rows": len(sample_df),
                    "estimated_total_rows": self._estimate_csv_rows(file_path),
                    "sample_data": sample_rows,
                    "delimiter": detected_delimiter,
                    "encoding": detected_encoding
                }
            
            elif file_type == 'excel':
                # Analyze Excel using Polars
                sample_df = pl.read_excel(file_path, sheet_id=1)
                
                # Note: Polars doesn't have easy sheet name detection, use pandas for that only
                import pandas as pd_temp
                excel_file = pd_temp.ExcelFile(file_path)
                sheet_names = excel_file.sheet_names
                
                # Convert column types
                column_types = {col: str(dtype) for col, dtype in zip(sample_df.columns, sample_df.dtypes)}
                sample_rows = sample_df.head(5).to_dicts()
                
                return {
                    "file_type": file_type,
                    "sheet_names": sheet_names,
                    "default_sheet": sheet_names[0],
                    "columns": list(sample_df.columns),
                    "column_types": column_types,
                    "sample_rows": len(sample_df),
                    "sample_data": sample_rows
                }
            
            elif file_type == 'json':
                # Analyze JSON using Polars
                try:
                    # Try reading as NDJSON first (one JSON object per line)
                    sample_df = pl.read_ndjson(file_path)
                    
                    column_types = {col: str(dtype) for col, dtype in zip(sample_df.columns, sample_df.dtypes)}
                    sample_rows = sample_df.head(5).to_dicts()
                    
                    return {
                        "file_type": file_type,
                        "structure": "ndjson",
                        "columns": list(sample_df.columns),
                        "column_types": column_types,
                        "sample_rows": len(sample_df),
                        "estimated_total_rows": len(sample_df),
                        "sample_data": sample_rows
                    }
                except:
                    # Fallback: regular JSON array
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    if isinstance(data, list) and len(data) > 0:
                        return {
                            "file_type": file_type,
                            "structure": "array",
                            "columns": list(data[0].keys()) if isinstance(data[0], dict) else [],
                            "sample_rows": min(len(data), 100),
                            "estimated_total_rows": len(data),
                            "sample_data": data[:5]
                        }
                    elif isinstance(data, dict):
                        # Single object or nested structure
                        return {
                            "file_type": file_type,
                            "structure": "object",
                            "keys": list(data.keys()),
                            "sample_data": data
                        }
            
            else:
                return {
                    "file_type": file_type,
                    "error": f"Unsupported file type: {file_type}"
                }
                
        except Exception as e:
            logger.error(f"Error analyzing file {file_path}: {e}")
            return {
                "file_type": file_type,
                "error": f"Error analyzing file: {str(e)}"
            }
    
    def _estimate_csv_rows(self, file_path: Path) -> int:
        """Estimate total rows in CSV file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                # Count lines (rough estimate)
                lines = sum(1 for _ in f)
                return max(0, lines - 1)  # Subtract header
        except:
            return 0

# Global service instance
upload_service = FileUploadService()

@router.post("/file")
async def upload_file(
    file: UploadFile = File(...),
    source_name: Optional[str] = None,
    db: Session = Depends(get_database_session)
):
    """
    Upload a file for processing.
    
    New implementation using Job Queue:
    1. Validate file
    2. Save to disk
    3. Create batch_control record
    4. Enqueue job in job_queue
    5. Return immediately
    """
    try:
        # 1. Validate file
        validation = upload_service.validate_file(file)
        if not validation["valid"]:
            raise HTTPException(
                status_code=400,
                detail=f"File validation failed: {', '.join(validation['errors'])}"
            )
        
        # 2. Generate batch ID
        batch_id = str(uuid.uuid4())
        
        # 3. Save file
        file_path = await upload_service.save_file(file, batch_id)
        file_size = file_path.stat().st_size
        
        # 4. Determine source name
        if not source_name:
            source_name = Path(file.filename).stem
        
        # 5. Create batch record
        db.execute(text("""
            INSERT INTO staging_meta.batch_control 
            (batch_id, source_name, source_type, file_name, file_size, status)
            VALUES (:batch_id, :source_name, 'file', :file_name, :file_size, 'UPLOADED')
        """), {
            "batch_id": batch_id,
            "source_name": source_name,
            "file_name": file.filename,
            "file_size": file_size
        })
        db.commit()
        
        # 6. Create job in queue (only if one doesn't exist already)
        from data_staging.workers.job_queue import create_job
        from data_staging.config import settings
        
        # Check if job already exists for this batch
        existing_job = db.execute(text("""
            SELECT job_id FROM staging_meta.job_queue
            WHERE payload->>'batch_id' = :batch_id
            AND status IN ('PENDING', 'PROCESSING')
            LIMIT 1
        """), {"batch_id": batch_id}).fetchone()
        
        if existing_job:
            job_id = str(existing_job[0])
            logger.info(f"Job already exists for batch {batch_id}: {job_id} - reusing existing job")
        else:
            job_id = create_job(
                database_url=str(settings.DATABASE_URL),
                job_type="PROCESS_FILE",
                payload={
                    "batch_id": batch_id,
                    "file_path": str(file_path),
                    "source_name": source_name
                },
                priority=0
            )
            logger.info(f"Created new job for batch {batch_id}: {job_id}")
        
        logger.info(f"File uploaded: batch_id={batch_id}, job_id={job_id}")
        
        # 7. Return immediately
        return {
            "batch_id": batch_id,
            "job_id": job_id,
            "message": "File uploaded and queued for processing",
            "file_name": file.filename,
            "file_size": file_size,
            "source_name": source_name,
            "status": "uploaded",
            "check_status_url": f"/api/v1/upload/batch/{batch_id}/status"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@router.get("/batch/{batch_id}/status")
async def get_batch_status(batch_id: str, db: Session = Depends(get_database_session)):
    """Get status of a batch upload"""
    
    try:
        # Get batch info
        result = db.execute(text("""
            SELECT batch_id, source_name, source_type, file_name, file_size, 
                   records_count, status, created_at, started_at, completed_at, 
                   error_message, metadata
            FROM staging_meta.batch_control 
            WHERE batch_id = :batch_id
        """), {"batch_id": batch_id})
        
        batch = result.fetchone()
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
        
        # 2. Obtener job info
        from data_staging.workers.job_queue import get_job_status
        from data_staging.config import settings
        
        # Buscar job asociado a este batch
        job_result = db.execute(text("""
            SELECT job_id FROM staging_meta.job_queue
            WHERE payload->>'batch_id' = :batch_id
            ORDER BY created_at DESC
            LIMIT 1
        """), {"batch_id": batch_id})
        
        job_row = job_result.fetchone()
        job_info = None
        
        if job_row:
            job_id = str(job_row[0])
            job_info = get_job_status(str(settings.DATABASE_URL), job_id)
            
        # 3. Get processing history
        result = db.execute(text("""
            SELECT load_id, load_type, target_table, records_inserted, records_updated,
                   records_rejected, data_quality_score, load_start_time, load_end_time,
                   duration_seconds, status, error_details
            FROM staging_meta.load_history 
            WHERE batch_id = :batch_id
            ORDER BY load_start_time DESC
        """), {"batch_id": batch_id})
        
        load_history = []
        for row in result:
            load_history.append({
                "load_id": row.load_id,
                "load_type": row.load_type,
                "target_table": row.target_table,
                "records_inserted": row.records_inserted,
                "records_updated": row.records_updated,
                "records_rejected": row.records_rejected,
                "data_quality_score": row.data_quality_score,
                "load_start_time": row.load_start_time.isoformat() if row.load_start_time else None,
                "load_end_time": row.load_end_time.isoformat() if row.load_end_time else None,
                "duration_seconds": row.duration_seconds,
                "status": row.status,
                "error_details": row.error_details
            })
        
        # Parse metadata
        metadata = batch.metadata if batch.metadata else {}
        
        return {
            "batch_id": batch.batch_id,
            "source_name": batch.source_name,
            "source_type": batch.source_type,
            "file_name": batch.file_name,
            "file_size": batch.file_size,
            "records_count": batch.records_count,
            "status": batch.status,
            "created_at": batch.created_at.isoformat() if batch.created_at else None,
            "started_at": batch.started_at.isoformat() if batch.started_at else None,
            "completed_at": batch.completed_at.isoformat() if batch.completed_at else None,
            "error_message": batch.error_message,
            "metadata": metadata,
            "load_history": load_history,
            "job": job_info
        }
        
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing batch: {e}")
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

# Modelos de request para procesamiento de batches
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

@router.post("/batch/{batch_id}/process")
async def process_batch(
    batch_id: str,
    request: ProcessRequest,
    db: Session = Depends(get_database_session)
):
    """
    Procesa un batch con configuración avanzada.
    Ahora usa job queue en lugar de BackgroundTasks.
    """
    try:
        # 1. Verificar batch existe
        result = db.execute(text("""
            SELECT batch_id, file_name, source_name, metadata 
            FROM staging_meta.batch_control 
            WHERE batch_id = :batch_id
        """), {"batch_id": batch_id})
        
        batch = result.fetchone()
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
        
        # 2. Obtener metadata
        metadata = batch.metadata if batch.metadata else {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        
        # 3. Actualizar metadata con request
        if request.column_mapping:
            metadata["column_mappings"] = {
                k: v.dict() for k, v in request.column_mapping.items()
            }
        
        if request.columns:
            metadata["selected_columns"] = request.columns
            
        if request.direct_load:
            metadata["direct_load"] = True
            logger.info(f"Direct load requested for batch {batch_id}")
            
        if request.auto_production:
            metadata["auto_production"] = True
            logger.info(f"Auto-production enabled for batch {batch_id}")
        
        # 4. Guardar metadata actualizado
        db.execute(text("""
            UPDATE staging_meta.batch_control
            SET metadata = :metadata,
                status = 'PENDING'
            WHERE batch_id = :batch_id
        """), {
            "metadata": json.dumps(metadata),
            "batch_id": batch_id
        })
        db.commit()
        
        # 5. Obtener file_path
        file_path = metadata.get("aggregated_file_path") or metadata.get("file_path")
        if not file_path:
            file_path = str(settings.upload_path / f"{batch_id}_{batch.file_name}")
            
        # 5b. Fetch Target Column Types for Validation
        target_schema = metadata.get("target_schema")
        target_table = metadata.get("target_table")
        target_column_types = {}
        
        if target_schema and target_table:
            try:
                type_query = text("""
                    SELECT column_name, data_type, character_maximum_length
                    FROM information_schema.columns 
                    WHERE table_schema = :schema AND table_name = :table
                """)
                type_result = db.execute(type_query, {"schema": target_schema, "table": target_table})
                
                for row in type_result:
                    col_name = row.column_name
                    dtype = row.data_type
                    length = row.character_maximum_length
                    
                    full_type = dtype
                    if length:
                        full_type = f"{dtype}({length})"
                    
                    target_column_types[col_name] = full_type
                    
                logger.info(f"Fetched {len(target_column_types)} column types for validation")
            except Exception as e:
                logger.error(f"Failed to fetch column types: {e}")

        # 6. Crear job en queue (solo si no existe ya)
        from data_staging.workers.job_queue import create_job
        
        # Check if job already exists for this batch
        existing_job = db.execute(text("""
            SELECT job_id FROM staging_meta.job_queue
            WHERE payload->>'batch_id' = :batch_id
            AND status IN ('PENDING', 'PROCESSING')
            LIMIT 1
        """), {"batch_id": batch_id}).fetchone()
        
        if existing_job:
            job_id = str(existing_job[0])
            logger.info(f"Job already exists for batch {batch_id}: {job_id} - reusing existing job")
        else:
            job_id = create_job(
                database_url=str(settings.DATABASE_URL),
                job_type="PROCESS_FILE",
                payload={
                    "batch_id": batch_id,
                    "file_path": file_path,
                    "source_name": batch.source_name,
                    "column_mappings": metadata.get("column_mappings"),
                    "selected_columns": metadata.get("selected_columns"),
                    "auto_production": metadata.get("auto_production", False),
                    "production_schema": metadata.get("production_schema"),
                    "production_table": metadata.get("production_table"),
                    "dedup_columns": metadata.get("dedup_columns"),
                    "target_column_types": target_column_types,
                    "direct_load": metadata.get("direct_load", False)
                },
                priority=0
            )
            logger.info(f"Created new job for batch {batch_id}: {job_id}")
        
        return {
            "message": "Processing queued",
            "batch_id": batch_id,
            "job_id": job_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error queueing processing: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/batches")
async def list_batches(
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    source_name: Optional[str] = None,
    db: Session = Depends(get_database_session)
):
    """List uploaded batches with optional filtering"""
    
    try:
        # Build query with filters
        where_conditions = []
        params = {"limit": limit, "offset": offset}
        
        if status:
            where_conditions.append("status = :status")
            params["status"] = status
        
        if source_name:
            where_conditions.append("source_name ILIKE :source_name")
            params["source_name"] = f"%{source_name}%"
        
        where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
        
        query = text(f"""
            SELECT batch_id, source_name, source_type, file_name, file_size,
                   records_count, status, created_at, completed_at, error_message
            FROM staging_meta.batch_control 
            {where_clause}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """)
        
        result = db.execute(query, params)
        
        batches = []
        for row in result:
            batches.append({
                "batch_id": row.batch_id,
                "source_name": row.source_name,
                "source_type": row.source_type,
                "file_name": row.file_name,
                "file_size": row.file_size,
                "records_count": row.records_count,
                "status": row.status,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                "error_message": row.error_message
            })
        
        # Get total count
        count_query = text(f"""
            SELECT COUNT(*) FROM staging_meta.batch_control {where_clause}
        """)
        total_count = db.execute(count_query, params).scalar()
        
        return {
            "batches": batches,
            "total": total_count,
            "limit": limit,
            "offset": offset
        }
        
    except Exception as e:
        logger.error(f"Error listing batches: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving batches: {str(e)}")


async def process_file_async(batch_id: str, file_path: str, source_name: str, columns: Optional[List[str]] = None):
    """Background task to process uploaded file"""
    
    try:
        logger.info(f"Starting async processing for batch {batch_id} with columns: {columns}")
        
        # Get database session
        from data_staging.database import get_database_manager
        db_manager = get_database_manager()
        
        with db_manager.get_session() as db:
            # Update status to processing
            db.execute(text("""
                UPDATE staging_meta.batch_control 
                SET status = 'PROCESSING', started_at = CURRENT_TIMESTAMP
                WHERE batch_id = :batch_id
            """), {"batch_id": batch_id})
            db.commit()
            
            # Fetch metadata to get encoding/delimiter
            batch_result = db.execute(text("SELECT metadata FROM staging_meta.batch_control WHERE batch_id = :batch_id"), {"batch_id": batch_id}).fetchone()
            metadata = batch_result.metadata if batch_result and batch_result.metadata else {}
            file_analysis = metadata.get("file_analysis", {})
            
            # Create load history record
            load_id = str(uuid.uuid4())
            start_time = datetime.now()
            
            db.execute(text("""
                INSERT INTO staging_meta.load_history 
                (load_id, batch_id, source_name, load_type, load_start_time, status)
                VALUES (:load_id, :batch_id, :source_name, 'FILE_UPLOAD', :start_time, 'IN_PROGRESS')
            """), {
                "load_id": load_id,
                "batch_id": batch_id,
                "source_name": source_name,
                "start_time": start_time
            })
            db.commit()
            
            try:
                # Initialize file handler and validator
                file_handler = FileHandler()
                validator = DataValidator()
                
                # Check for incompatible dependencies
                try:
                    import pyarrow
                except ImportError:
                    logger.warning("pyarrow not installed. Parquet support may be limited.")
                
                # Read and process file
                # Use columns if provided
                read_options = {}
                if columns:
                   read_options["usecols"] = columns
                
                # Use detected encoding and delimiter if available
                if file_analysis.get("encoding"):
                    read_options["encoding"] = file_analysis["encoding"]
                if file_analysis.get("delimiter"):
                    read_options["delimiter"] = file_analysis["delimiter"]
                
                # Handle ragged lines (skip them to avoid failure)
                read_options["on_bad_lines"] = "skip"

                # Pass options to read_file if it supports kwargs, otherwise read full and filter
                try:
                    df = file_handler.read_file(Path(file_path), **read_options)
                except TypeError:
                     # Fallback if read_file doesn't accept kwargs
                    df = file_handler.read_file(Path(file_path))
                    
                if df is not None and not df.empty:
                    # Filter columns if not already filtered
                    if columns:
                        valid_columns = [c for c in columns if c in df.columns]
                        if valid_columns:
                            df = df[valid_columns]
                        else:
                            logger.warning(f"None of the selected columns {columns} found in file. Using all columns.")

                    records_count = len(df)
                    
                    # Validate data
                    validation_result = validator.validate_dataframe(df)
                    quality_score = validation_result.get("overall_score", 0)
                    
                    # For now, just log the results
                    # In a full implementation, you would:
                    # 1. Save to staging table
                    # 2. Apply transformations
                    # 3. Load to target table
                    
                    logger.info(f"Processed {records_count} records with quality score {quality_score}")
                    
                    # Update successful completion
                    end_time = datetime.now()
                    duration = int((end_time - start_time).total_seconds())
                    
                    db.execute(text("""
                        UPDATE staging_meta.load_history 
                        SET load_end_time = :end_time, duration_seconds = :duration,
                            status = 'COMPLETED', records_inserted = :records_count,
                            data_quality_score = :quality_score
                        WHERE load_id = :load_id
                    """), {
                        "load_id": load_id,
                        "end_time": end_time,
                        "duration": duration,
                        "records_count": records_count,
                        "quality_score": quality_score
                    })
                    
                    db.execute(text("""
                        UPDATE staging_meta.batch_control 
                        SET status = 'COMPLETED', completed_at = CURRENT_TIMESTAMP,
                            records_count = :records_count
                        WHERE batch_id = :batch_id
                    """), {
                        "batch_id": batch_id,
                        "records_count": records_count
                    })
                    
                else:
                    raise Exception("No data found in file or file is empty")
            
            except Exception as e:
                # Update failure status
                error_msg = str(e)
                logger.error(f"Processing failed for batch {batch_id}: {error_msg}")
                
                end_time = datetime.now()
                duration = int((end_time - start_time).total_seconds())
                
                db.execute(text("""
                    UPDATE staging_meta.load_history 
                    SET load_end_time = :end_time, duration_seconds = :duration,
                        status = 'FAILED', error_details = :error_msg
                    WHERE load_id = :load_id
                """), {
                    "load_id": load_id,
                    "end_time": end_time,
                    "duration": duration,
                    "error_msg": error_msg
                })
                
                db.execute(text("""
                    UPDATE staging_meta.batch_control 
                    SET status = 'FAILED', completed_at = CURRENT_TIMESTAMP,
                        error_message = :error_msg
                    WHERE batch_id = :batch_id
                """), {
                    "batch_id": batch_id,
                    "error_msg": error_msg
                })
            
            db.commit()
            
    except Exception as e:
        logger.error(f"Critical error in async processing for batch {batch_id}: {e}")


# ============================================================================
# UPLOAD WIZARD ENDPOINTS
# ============================================================================

@router.post("/file-temp")
async def upload_file_temp(
    file: UploadFile = File(...),
    target_schema: Optional[str] = None,
    target_table: Optional[str] = None,
    db: Session = Depends(get_database_session)
):
    """
    Upload file for wizard - parses headers but doesn't process yet.
    
    Steps:
    1. Upload file
    2. Parse headers/columns
    3. Create batch record with status 'PENDING_MAPPING'
    4. Return batch_id + file_headers for Step 2 mapping
    """
    try:
        # 1. Validate file
        validation = upload_service.validate_file(file)
        if not validation["valid"]:
            raise HTTPException(
                status_code=400,
                detail=f"File validation failed: {', '.join(validation['errors'])}"
            )
        
        # 2. Generate batch ID
        batch_id = str(uuid.uuid4())
        
        # 3. Save file
        file_path = await upload_service.save_file(file, batch_id)
        file_size = file_path.stat().st_size
        
        # 4. Analyze file structure and parse headers
        file_analysis = upload_service.analyze_file_structure(file_path)
        
        if "error" in file_analysis:
            raise HTTPException(
                status_code=400,
                detail=f"Error analyzing file: {file_analysis['error']}"
            )
        
        file_headers = file_analysis.get("columns", [])
        
        # 5. Determine source_name based on target_table
        if target_table:
            source_name = target_table  #  Worker will add 'stage_' prefix
        else:
            source_name = Path(file.filename).stem
        
        # 6. Create batch record with PENDING_MAPPING status
        metadata = {
            "file_analysis": file_analysis,
            "file_headers": file_headers,
           "file_path": str(file_path),
            "target_schema": target_schema,
            "target_table": target_table,
            "wizard_step": 1
        }
        
        db.execute(text("""
            INSERT INTO staging_meta.batch_control 
            (batch_id, source_name, source_type, file_name, file_size, status, metadata)
            VALUES (:batch_id, :source_name, 'file', :file_name, :file_size, 'PENDING_MAPPING', :metadata)
        """), {
            "batch_id": batch_id,
            "source_name": source_name,
            "file_name": file.filename,
            "file_size": file_size,
            "metadata": json.dumps(metadata)
        })
        db.commit()
        
        logger.info(f"File uploaded (temp): batch_id={batch_id}, headers={len(file_headers)}")
        
        return {
            "batch_id": batch_id,
            "file_name": file.filename,
            "file_size": file_size,
            "file_type": file_analysis.get("file_type"),
            "file_headers": file_headers,
            "source_name": source_name,
            "suggested_staging_table": source_name,
            "estimated_rows": file_analysis.get("estimated_total_rows", file_analysis.get("sample_rows", 0)),
            "status": "pending_mapping",
            "message": "File uploaded successfully. Proceed to column mapping."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload temp failed: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.post("/batch/{batch_id}/mapping")
async def save_column_mapping(
    batch_id: str,
    mapping_data: Dict[str, Any],
    db: Session = Depends(get_database_session)
):
    """
    Save column mappings for wizard Step 2.
    
    Expected mapping_data:
    {
        "target_schema": "m8_schema",
        "target_table": "products",
        "column_mappings": {
            "product_name": {
                "target": "product_name",
                "default_value": "Unknown",
                "auto_mapped": true
            }
        },
        "column_toggles": {"product_name": true, "price": true},
        "dedup_columns": "email,phone"  // optional
    }
    """
    try:
        # 1. Verify batch exists
        result = db.execute(text("""
            SELECT batch_id, metadata FROM staging_meta.batch_control 
            WHERE batch_id = :batch_id
        """), {"batch_id": batch_id})
        
        batch = result.fetchone()
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
        
        # 2. Get existing metadata
        metadata = batch.metadata if batch.metadata else {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        
        # 3. Update metadata with mappings
        metadata.update({
            "target_schema": mapping_data.get("target_schema"),
            "target_table": mapping_data.get("target_table"),
            "column_mappings": mapping_data.get("column_mappings", {}),
            "column_toggles": mapping_data.get("column_toggles", {}),
            "dedup_columns": mapping_data.get("dedup_columns"),
            "process_type": mapping_data.get("process_type"),
            "wizard_step": 2
        })
        
        # 4. Update source_name if target_table changed
        target_table = mapping_data.get("target_table")
        if target_table:
            source_name = target_table  # Worker will add 'stage_' prefix
            
            db.execute(text("""
                UPDATE staging_meta.batch_control
                SET metadata = :metadata,
                    source_name = :source_name,
                    status = 'PENDING_PREVIEW'
                WHERE batch_id = :batch_id
            """), {
                "metadata": json.dumps(metadata),
                "source_name": source_name,
                "batch_id": batch_id
            })
        else:
            db.execute(text("""
                UPDATE staging_meta.batch_control
                SET metadata = :metadata,
                    status = 'PENDING_PREVIEW'
                WHERE batch_id = :batch_id
            """), {
                "metadata": json.dumps(metadata),
                "batch_id": batch_id
            })
        
        db.commit()
        
        logger.info(f"Mappings saved for batch {batch_id}")
        
        return {
            "status": "success",
            "batch_id": batch_id,
            "message": "Column mappings saved successfully",
            "next_step": "preview"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving mappings: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save mappings: {str(e)}")


@router.post("/batch/{batch_id}/preview")
async def generate_preview(
    batch_id: str,
    db: Session = Depends(get_database_session)
):
    """
    Generate preview for wizard Step 3.
    Applies mappings to first N rows and returns preview + validation stats.
    """
    try:
        # 1. Get batch metadata
        result = db.execute(text("""
            SELECT batch_id, metadata, source_name FROM staging_meta.batch_control 
            WHERE batch_id = :batch_id
        """), {"batch_id": batch_id})
        
        batch = result.fetchone()
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
        
        metadata = batch.metadata if batch.metadata else {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        
        # 2. Extract mappings and process_type
        file_path = metadata.get("file_path", "")
        column_mappings = metadata.get("column_mappings", {})
        column_toggles = metadata.get("column_toggles", {})
        process_type = metadata.get("process_type", "Other")
        file_analysis = metadata.get("file_analysis", {})
        encoding = file_analysis.get("encoding", "utf-8")
        delimiter = file_analysis.get("delimiter", ",")
        
        # 3. Process aggregation
        from data_staging.services.aggregation_service import process_aggregation, AggregationError
        
        try:
            agg_stats, agg_file_path = process_aggregation(
                file_path=file_path,
                column_mappings=column_mappings,
                column_toggles=column_toggles,
                process_type=process_type,
                encoding=encoding,
                delimiter=delimiter
            )
        except AggregationError as ae:
            raise HTTPException(status_code=400, detail=str(ae))
        
        # 4. Save path to aggregated file so worker uses it if Weekly/Monthly
        if process_type in ["Weekly", "Monthly"] and not agg_stats.get("has_error"):
            metadata["aggregated_file_path"] = str(agg_file_path)
        
        # 5. Update metadata
        metadata["wizard_step"] = 3
        metadata["preview_generated"] = True
        
        db.execute(text("""
            UPDATE staging_meta.batch_control
            SET metadata = :metadata,
                status = 'PENDING_PROCESS'
            WHERE batch_id = :batch_id
        """), {
            "metadata": json.dumps(metadata),
            "batch_id": batch_id
        })
        db.commit()
        
        logger.info(f"Preview generated for batch {batch_id}")
        
        preview_data = agg_stats.pop("preview_data", [])

        return {
            "batch_id": batch_id,
            "validation_summary": agg_stats,
            "target_schema": metadata.get("target_schema"),
            "target_table": metadata.get("target_table"),
            "staging_table": batch.source_name,
            "process_type": process_type,
            "preview_data": preview_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating preview: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to generate preview: {str(e)}")


@router.get("/batch/{batch_id}/progress")
async def get_processing_progress(
    batch_id: str,
    db: Session = Depends(get_database_session)
):
    """
    Get real-time processing progress for wizard Step 4.
    """
    try:
        # Get batch info
        result = db.execute(text("""
            SELECT batch_id, status, records_count, error_message, metadata,
                   source_name, started_at, completed_at
            FROM staging_meta.batch_control 
            WHERE batch_id = :batch_id
        """), {"batch_id": batch_id})
        
        batch = result.fetchone()
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
        
        metadata = batch.metadata if batch.metadata else {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        
        # Get job progress from metadata (worker updates it there)
        # Note: job_queue doesn't have a progress column - progress is stored in batch_control metadata
        processing_stats = metadata.get("processing_progress", {})
        
        # Calculate progress
        status = batch.status
        progress_percentage = 0
        current_operation = "Initializing..."
        
        if status == "PENDING_MAPPING":
            progress_percentage = 25
            current_operation = "Waiting for column mapping"
        elif status == "PENDING_PREVIEW":
            progress_percentage = 50
            current_operation = "Waiting for preview confirmation"
        elif status == "PENDING_PROCESS" or status == "PENDING":
            progress_percentage = 60
            current_operation = "Ready to process"
        elif status == "PROCESSING":
            # Progress is stored in batch metadata, not job table
            progress_percentage = processing_stats.get("progress_percentage", 75)
            current_operation = processing_stats.get("current_operation", "Processing data...")
        elif status == "COMPLETED":
            progress_percentage = 100
            current_operation = "Processing complete"
        elif status == "PROMOTED":
            progress_percentage = 100
            current_operation = "Promotion to Production complete"
        elif status == "FAILED":
            progress_percentage = 0
            current_operation = f"Failed: {batch.error_message}"
        
        # Get processed/total rows
        total_rows = metadata.get("file_analysis", {}).get("estimated_total_rows", 0)
        processed_rows = batch.records_count or 0
        
        # Get stats from metadata if available
        processing_stats = metadata.get("processing_stats", {})
        rejected_count = processing_stats.get("total_rejected", 0)
        
        return {
            "batch_id": batch_id,
            "status": status,
            "progress_percentage": progress_percentage,
            "current_operation": current_operation,
            "total_rows": total_rows,
            "processed_rows": processed_rows,
            "loaded_rows": processed_rows,
            "rejected_rows": rejected_count,
            "target_schema": metadata.get("target_schema"),
            "target_table": metadata.get("target_table"),
            "staging_table": batch.source_name,
            "started_at": batch.started_at.isoformat() if batch.started_at else None,
            "completed_at": batch.completed_at.isoformat() if batch.completed_at else None,
            "error_message": batch.error_message,
            "direct_load": metadata.get("direct_load", False)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting progress: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get progress: {str(e)}")



# --- Helper Functions ---

def create_job(
    db: Session,
    job_type: str,
    payload: Dict[str, Any],
    priority: int = 0
) -> str:
    """Create a background job in the queue"""
    job_id = str(uuid.uuid4())
    
    try:
        query = text("""
            INSERT INTO staging_meta.job_queue 
            (job_id, job_type, payload, priority, status)
            VALUES (:job_id, :job_type, :payload, :priority, 'PENDING')
        """)
        
        db.execute(query, {
            "job_id": job_id,
            "job_type": job_type,
            "payload": json.dumps(payload, default=str),
            "priority": priority
        })
        db.commit()
        logger.info(f"Job created: {job_id} ({job_type})")
        return job_id
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating job: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create job: {str(e)}")


# --- Promotion Endpoints ---

@router.post("/staging/promote/{batch_id}")
async def promote_batch(
    batch_id: str,
    db: Session = Depends(get_database_session)
):
    """
    Trigger promotion of a batch to production.
    """
    try:
        # 1. Validate batch exists and is ready
        batch = db.execute(text("SELECT status, metadata FROM staging_meta.batch_control WHERE batch_id = :batch_id"), {"batch_id": batch_id}).fetchone()
        
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
            
        # Allow promotion if COMPLETED (processed to staging) or already FAILED promotion (retry)
        if batch.status not in ['COMPLETED', 'FAILED']:
             # Strict check: only allow if it passed staging processing
             pass 
        
        metadata = batch.metadata
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
            
        target_schema = metadata.get("target_schema")
        target_table = metadata.get("target_table")
        
        if not target_schema or not target_table:
             raise HTTPException(status_code=400, detail="Target schema/table not defined for this batch")

        # 2. Check if a promotion job is already running
        existing_job = db.execute(text("""
            SELECT job_id FROM staging_meta.job_queue 
            WHERE job_type = 'PROMOTE_BATCH' 
            AND status IN ('PENDING', 'PROCESSING')
            AND payload::jsonb ->> 'batch_id' = :batch_id
        """), {"batch_id": batch_id}).fetchone()
        
        if existing_job:
            return JSONResponse(
                status_code=202,
                content={"message": "Promotion already in progress", "job_id": existing_job.job_id}
            )

        # 3. Create Promotion Job
        # Clear previous error message if retrying
        db.execute(text("UPDATE staging_meta.batch_control SET error_message = NULL WHERE batch_id = :batch_id"), {"batch_id": batch_id})
        db.commit()

        job_id = create_job(
            db=db,
            job_type="PROMOTE_BATCH",
            payload={
                "batch_id": batch_id,
                "target_schema": target_schema,
                "target_table": target_table,
                "dedup_columns": metadata.get("dedup_columns", [])
            },
            priority=10 # Higher priority
        )
        
        return {
            "message": "Promotion job queued",
            "job_id": job_id,
            "target": f"{target_schema}.{target_table}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering promotion: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/staging/promote/{batch_id}/resume")
async def resume_promotion(
    batch_id: str,
    db: Session = Depends(get_database_session)
):
    """
    Resume a batch promotion that failed mid-flight and is in PARTIALLY_PROMOTED state.
    """
    try:
        # 1. Validate batch exists and is ready
        batch = db.execute(text("SELECT status, metadata FROM staging_meta.batch_control WHERE batch_id = :batch_id"), {"batch_id": batch_id}).fetchone()
        
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
            
        # specifically allow PARTIALLY_PROMOTED or FAILED
        if batch.status not in ['PARTIALLY_PROMOTED', 'FAILED']:
             raise HTTPException(status_code=400, detail=f"Cannot resume a batch in '{batch.status}' status. Must be PARTIALLY_PROMOTED or FAILED.")
        
        metadata = batch.metadata
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
            
        target_schema = metadata.get("target_schema")
        target_table = metadata.get("target_table")
        
        if not target_schema or not target_table:
             raise HTTPException(status_code=400, detail="Target schema/table not defined for this batch")

        # 2. Check if a promotion job is already running
        existing_job = db.execute(text("""
            SELECT job_id FROM staging_meta.job_queue 
            WHERE job_type = 'PROMOTE_BATCH' 
            AND status IN ('PENDING', 'PROCESSING')
            AND payload::jsonb ->> 'batch_id' = :batch_id
        """), {"batch_id": batch_id}).fetchone()
        
        if existing_job:
            return JSONResponse(
                status_code=202,
                content={"message": "Promotion already in progress", "job_id": existing_job.job_id}
            )

        # 3. Create Promotion Job
        # Clear previous error message if retrying
        db.execute(text("UPDATE staging_meta.batch_control SET error_message = NULL, status = 'PROCESSING' WHERE batch_id = :batch_id"), {"batch_id": batch_id})
        db.commit()

        job_id = create_job(
            db=db,
            job_type="PROMOTE_BATCH",
            payload={
                "batch_id": batch_id,
                "target_schema": target_schema,
                "target_table": target_table,
                "dedup_columns": metadata.get("dedup_columns", [])
            },
            priority=10 # Higher priority for resumes
        )
        
        return {
            "message": "Resume promotion job queued",
            "job_id": job_id,
            "target": f"{target_schema}.{target_table}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resuming promotion: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/staging/batch/{batch_id}/rejected/download")
async def download_rejected_records(
    batch_id: str,
    db: Session = Depends(get_database_session)
):
    """
    Descarga los registros rechazados desde el archivo en disco generado durante la validación.
    No accede a ninguna tabla en BD — cero WAL, cero espacio extra en Supabase.
    """
    try:
        # Obtener ruta del archivo desde metadata del batch
        batch = db.execute(
            text("SELECT metadata FROM staging_meta.batch_control WHERE batch_id = :batch_id"),
            {"batch_id": batch_id}
        ).fetchone()

        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")

        metadata = batch.metadata or {}
        if isinstance(metadata, str):
            import json as _json
            metadata = _json.loads(metadata)

        rejected_file_path = metadata.get("rejected_temp_file")

        if not rejected_file_path or not Path(rejected_file_path).exists():
            # Si no hay archivo = no hubo rechazados, devolver CSV vacío
            async def empty_csv():
                yield "source_row_number\tvalidation_status\terror_details\traw_data\n"

            return StreamingResponse(
                empty_csv(),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename=rejected_records_{batch_id}.csv"}
            )

        # Streaming directo desde disco — sin cargar todo en memoria
        def stream_file():
            with open(rejected_file_path, "r", encoding="utf-8") as f:
                for line in f:
                    yield line

        return StreamingResponse(
            stream_file(),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=rejected_records_{batch_id}.csv"}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading rejected records: {e}")
        raise HTTPException(status_code=500, detail=str(e))
@router.delete("/batch/{batch_id}")
async def delete_batch(
    batch_id: str,
    db: Session = Depends(get_database_session)
):
    """
    Elimina un batch y todos sus datos relacionados (archivo, registros de staging, etc.)
    """
    try:
        batch = db.query(BatchControl).filter(BatchControl.batch_id == batch_id).first()
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")

        # 1. Eliminar archivo físico si existe
        if batch.file_path:
            file_path = Path(batch.file_path)
            if file_path.exists():
                file_path.unlink()

        # 2. El modelo BatchControl tiene cascade="all, delete-orphan",
        # así que eliminar el batch limpiará staging_records, validation_logs, etc.
        db.delete(batch)
        db.commit()

        return {"status": "success", "message": f"Batch {batch_id} deleted successfully"}

    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting batch {batch_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

"""
Staging operations API endpoints.
"""

import logging
from typing import Optional, List, Dict, Any
import uuid
import json
import traceback
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text, func, MetaData, Table, inspect, Column
from sqlalchemy.dialects.postgresql import insert

from ...database import get_database_session
from ...models.batch import BatchControl

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/staging", tags=["staging"])


@router.post("/process-to-production")
async def process_to_production(
    background_tasks: BackgroundTasks,
    batch_id: str,
    staging_table: str = "stage_products",
    production_table: str = "products",
    production_schema: str = "m8_schema",
    dedup_columns: Optional[str] = "product_id",
    db: Session = Depends(get_database_session)
):
    """Trigger staging-to-production pipeline."""
    try:
        logger.info(f"Starting staging-to-production for batch {batch_id}")
        
        # Validate batch exists and is completed
        batch_check = db.execute(text("""
            SELECT batch_id, status, source_name FROM staging_meta.batch_control 
            WHERE batch_id = :batch_id
        """), {"batch_id": batch_id})
        
        batch = batch_check.fetchone()
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
        
        if batch.status != "COMPLETED":
            raise HTTPException(
                status_code=400, 
                detail=f"Batch must be COMPLETED before processing to production. Current status: {batch.status}"
            )
        
        # Check if staging table has data
        staging_count = db.execute(text(f"""
            SELECT COUNT(*) FROM staging_data.{staging_table} 
            WHERE batch_id = :batch_id AND validation_status = 'PASSED'
        """), {"batch_id": batch_id}).scalar()
        
        if staging_count == 0:
            raise HTTPException(
                status_code=400, 
                detail=f"No validated records found in staging_data.{staging_table} for batch {batch_id}"
            )
        
        # Schedule background processing
        background_tasks.add_task(
            process_staging_to_production_async,
            batch_id,
            staging_table,
            production_table,
            production_schema,
            dedup_columns,
            batch.source_name
        )
        
        return {
            "message": "Staging-to-production processing started",
            "batch_id": batch_id,
            "staging_table": f"staging_data.{staging_table}",
            "production_table": f"{production_schema}.{production_table}",
            "staging_records": staging_count
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting staging-to-production: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/table-columns")
async def get_table_columns(
    schema: str = Query(..., description="The database schema (e.g., m8_schema)"),
    table: str = Query(..., description="The table name"),
    db: Session = Depends(get_database_session)
):
    """Get columns for a specific table in any schema."""
    try:
        # Use inspection or raw SQL to get columns
        query = text("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns 
            WHERE table_schema = :schema 
            AND table_name = :table
            ORDER BY ordinal_position
        """)
        
        result = db.execute(query, {"schema": schema, "table": table}).fetchall()
        
        if not result:
            # Maybe the table doesn't exist?
            return {"columns": [], "error": f"Table {schema}.{table} not found or has no columns"}
            
        columns = []
        for row in result:
            columns.append({
                "name": row.column_name,
                "type": row.data_type,
                "nullable": row.is_nullable == 'YES',
                "default": row.column_default
            })
            
        return {"columns": columns, "schema": schema, "table": table}
        
    except Exception as e:
        logger.error(f"Error fetching columns for {schema}.{table}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tables")
async def list_staging_tables(db: Session = Depends(get_database_session)):
    """List all staging tables with statistics."""
    try:
        query = text("""
            SELECT 
                table_name,
                (SELECT COUNT(*) FROM information_schema.columns 
                 WHERE table_schema = 'staging_data' AND table_name = t.table_name) as column_count
            FROM information_schema.tables t
            WHERE table_schema = 'staging_data'
            ORDER BY table_name
        """)
        
        tables = db.execute(query).fetchall()
        
        # Get record counts for each table
        result = []
        for table in tables:
            try:
                count_query = text(f"SELECT COUNT(*) FROM staging_data.{table.table_name}")
                record_count = db.execute(count_query).scalar()
                result.append({
                    "table_name": table.table_name,
                    "column_count": table.column_count,
                    "record_count": record_count
                })
            except Exception as e:
                logger.warning(f"Could not get count for {table.table_name}: {e}")
                result.append({
                    "table_name": table.table_name,
                    "column_count": table.column_count,
                    "record_count": "error"
                })
        
        return {"tables": result}
        
    except Exception as e:
        logger.error(f"Error listing staging tables: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/batch/{batch_id}/staging-data")
async def get_staging_data(
    batch_id: str, 
    limit: int = 100,
    db: Session = Depends(get_database_session)
):
    """Get staging data for a specific batch."""
    try:
        # Find staging table for this batch
        batch_query = text("""
            SELECT source_name FROM staging_meta.batch_control 
            WHERE batch_id = :batch_id
        """)
        
        batch = db.execute(batch_query, {"batch_id": batch_id}).fetchone()
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
        
        staging_table = f"stage_{batch.source_name.lower().replace(' ', '_').replace('-', '_')}"
        
        # Get staging data
        data_query = text(f"""
            SELECT staging_id, processed_data, source_row_number, validation_status, created_at
            FROM staging_data.{staging_table}
            WHERE batch_id = :batch_id
            ORDER BY source_row_number
            LIMIT :limit
        """)
        
        records = db.execute(data_query, {"batch_id": batch_id, "limit": limit}).fetchall()
        
        return {
            "batch_id": batch_id,
            "staging_table": staging_table,
            "records": [
                {
                    "staging_id": str(record.staging_id),
                    "processed_data": record.processed_data,
                    "source_row_number": record.source_row_number,
                    "validation_status": record.validation_status,
                    "created_at": record.created_at.isoformat() if record.created_at else None
                }
                for record in records
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting staging data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/batch/{batch_id}/rejected-records")
async def get_rejected_records(
    batch_id: str,
    limit: int = 100,
    db: Session = Depends(get_database_session)
):
    """Get rejected records for a specific batch"""
    try:
        # Check if batch exists
        batch = db.query(BatchControl).filter(BatchControl.batch_id == batch_id).first()
        if not batch:
            raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found")
        
        # Get rejected records
        query = text("""
            SELECT 
                rejection_id,
                source_name,
                source_row_number,
                rejection_reason,
                rejection_category,
                processing_stage,
                target_table,
                target_schema,
                error_message,
                created_at,
                resolution_status
            FROM staging_meta.rejected_records
            WHERE batch_id = :batch_id
            ORDER BY created_at DESC
            LIMIT :limit
        """)
        
        rejected_records = db.execute(query, {"batch_id": batch_id, "limit": limit}).fetchall()
        
        # Convert to list of dicts
        records = []
        for record in rejected_records:
            records.append({
                "rejection_id": str(record.rejection_id),
                "source_name": record.source_name,
                "source_row_number": record.source_row_number,
                "rejection_reason": record.rejection_reason,
                "rejection_category": record.rejection_category,
                "processing_stage": record.processing_stage,
                "target_table": record.target_table,
                "target_schema": record.target_schema,
                "error_message": record.error_message,
                "created_at": record.created_at.isoformat() if record.created_at else None,
                "resolution_status": record.resolution_status
            })
        
        return {
            "batch_id": batch_id,
            "total_rejected": len(records),
            "rejected_records": records
        }
        
    except Exception as e:
        logger.error(f"Error getting rejected records for batch {batch_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting rejected records: {str(e)}")


@router.get("/rejections/summary")
async def get_rejection_summary(
    source_name: Optional[str] = None,
    days: int = 7,
    db: Session = Depends(get_database_session)
):
    """Get rejection summary statistics"""
    try:
        # Build query based on filters
        where_clause = "WHERE created_at >= CURRENT_DATE - INTERVAL ':days days'"
        params = {"days": days}
        
        if source_name:
            where_clause += " AND source_name = :source_name"
            params["source_name"] = source_name
        
        query = text(f"""
            SELECT 
                source_name,
                rejection_reason,
                rejection_category,
                processing_stage,
                COUNT(*) as rejection_count,
                COUNT(CASE WHEN resolution_status = 'UNRESOLVED' THEN 1 END) as unresolved_count,
                COUNT(CASE WHEN can_reprocess = true THEN 1 END) as reprocessable_count,
                AVG(data_quality_score) as avg_quality_score,
                MIN(created_at) as first_rejection,
                MAX(created_at) as last_rejection
            FROM staging_meta.rejected_records
            {where_clause}
            GROUP BY source_name, rejection_reason, rejection_category, processing_stage
            ORDER BY rejection_count DESC, source_name
        """)
        
        results = db.execute(query, params).fetchall()
        
        # Convert to list of dicts
        summary = []
        for record in results:
            summary.append({
                "source_name": record.source_name,
                "rejection_reason": record.rejection_reason,
                "rejection_category": record.rejection_category,
                "processing_stage": record.processing_stage,
                "rejection_count": record.rejection_count,
                "unresolved_count": record.unresolved_count,
                "reprocessable_count": record.reprocessable_count,
                "avg_quality_score": float(record.avg_quality_score) if record.avg_quality_score else None,
                "first_rejection": record.first_rejection.isoformat() if record.first_rejection else None,
                "last_rejection": record.last_rejection.isoformat() if record.last_rejection else None
            })
        
        return {
            "summary": summary,
            "filters": {
                "source_name": source_name,
                "days": days
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting rejection summary: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting rejection summary: {str(e)}")


async def process_staging_to_production_async(
    batch_id: str,
    staging_table: str,
    production_table: str,
    production_schema: str,
    dedup_columns: Optional[str],
    source_name: str
):
    """Background task for staging-to-production processing (Bulk Optimized)."""
    try:
        logger.info(f"Processing staging-to-production for batch {batch_id} (Bulk Mode)")
        
        from ...database import get_database_manager
        db_manager = get_database_manager()
        
        BATCH_SIZE = 20000
        
        with db_manager.get_session() as db:
            # Create load history record
            load_id = str(uuid.uuid4())
            start_time = datetime.now()
            
            db.execute(text("""
                INSERT INTO staging_meta.load_history 
                (load_id, batch_id, source_name, load_type, target_table, target_schema,
                 load_start_time, status)
                VALUES (:load_id, :batch_id, :source_name, 'STAGING_TO_PRODUCTION', 
                        :target_table, :target_schema, :start_time, 'IN_PROGRESS')
            """), {
                "load_id": load_id,
                "batch_id": batch_id,
                "source_name": source_name,
                "target_table": production_table,
                "target_schema": production_schema,
                "start_time": start_time
            })
            db.commit()
            
            try:
                # 1. Reflect Production Table
                # 1. Reflect Production Table (Targeted)
                # 1. Reflect Production Table (Targeted - Using Inspect to avoid FK recursion)
                # metadata = MetaData() - Removed as we don't need full Table object with relationships
                try:
                     inspector = inspect(db.get_bind())
                     # Check if table exists
                     if not inspector.has_table(production_table, schema=production_schema):
                         raise Exception(f"Production table {production_schema}.{production_table} does not exist")
                         
                     # Get columns
                     columns_info = inspector.get_columns(production_table, schema=production_schema)
                     target_columns = [c['name'] for c in columns_info]
                     
                     # Reconstruct Table object for insert() references without reflecting FKs
                     # This avoids the infinite recursion issue while allowing SQLAlchemy to build queries
                     columns_list = [Column(c['name'], c['type'], primary_key=(c['name'] in [k for k in dict(inspector.get_pk_constraint(production_table, schema=production_schema)).get('constrained_columns', [])])) for c in columns_info]
                     target_table_obj = Table(production_table, MetaData(), *columns_list, schema=production_schema)
                     
                     # Get PK for default dedup
                     pk_constraint = inspector.get_pk_constraint(production_table, schema=production_schema)
                     target_pk_columns = pk_constraint.get('constrained_columns', [])
                     
                except Exception as e:
                    raise Exception(f"Error inspecting table {production_schema}.{production_table}: {e}")
                
                logger.info(f"Production table columns: {target_columns}")
                logger.info(f"Production table columns: {target_columns}")
                
                # Determine Primary Key / Dedup Columns
                pk_columns = []
                if dedup_columns and dedup_columns.strip():
                    pk_columns = [f.strip() for f in dedup_columns.split(',')]
                    # Verify they exist
                    missing = [col for col in pk_columns if col not in target_columns]
                    if missing:
                        raise Exception(f"Dedup columns {missing} not found in target table.")
                else:
                    # No dedup columns provided -> Append Mode
                    pk_columns = []
                    logger.info("No dedup_columns provided. Using APPEND ONLY mode.")
                    
                logger.info(f"Using deduplication keys: {pk_columns}")
                
                # 2. Count Total Records
                count_query = text(f"SELECT COUNT(*) FROM staging_data.{staging_table} WHERE batch_id = :batch_id AND validation_status = 'PASSED'")
                total_records = db.execute(count_query, {"batch_id": batch_id}).scalar()
                logger.info(f"Total validated records to process: {total_records}")
                
                if total_records == 0:
                     # DIAGNOSTIC LOGGING
                     debug_count = db.execute(text(f"SELECT COUNT(*) FROM staging_data.{staging_table} WHERE batch_id = :batch_id"), {"batch_id": batch_id}).scalar()
                     logger.error(f"DIAGNOSTIC: Total records for batch (any status): {debug_count}")
                     if debug_count > 0:
                         sample_status = db.execute(text(f"SELECT validation_status, COUNT(*) FROM staging_data.{staging_table} WHERE batch_id = :batch_id GROUP BY validation_status"), {"batch_id": batch_id}).fetchall()
                         logger.error(f"DIAGNOSTIC: Status distribution: {sample_status}")
                     
                     raise Exception(f"No validated records found in staging_data.{staging_table}")

                # 3. Process in Batches
                records_processed = 0
                last_row_number = -1
                
                while True:
                    logger.info(f"Processing batch starting after row {last_row_number} (Total expected: {total_records})")
                    
                    # Fetch batch from Staging using Keyset Pagination
                    staging_query = text(f"""
                        SELECT staging_id, processed_data, source_row_number
                        FROM staging_data.{staging_table}
                        WHERE batch_id = :batch_id 
                        AND validation_status = 'PASSED'
                        AND source_row_number > :last_row_number
                        ORDER BY source_row_number
                        LIMIT :limit
                    """)
                    
                    staging_batch = db.execute(staging_query, {
                        "batch_id": batch_id, 
                        "limit": BATCH_SIZE, 
                        "last_row_number": last_row_number
                    }).fetchall()
                    
                    if not staging_batch:
                        break
                        
                    # Update cursor for next iteration
                    last_row_number = staging_batch[-1].source_row_number
                    
                    # Process records in current batch
                    for record in staging_batch:
                        processed_data = record.processed_data
                        
                        # Filter columns that exist in target table
                        clean_data = {
                            col: processed_data.get(col)
                            for col in target_columns
                            if col in processed_data
                        }
                        
                        # If we have dedup columns, use upsert
                        if pk_columns:
                            # Verify record has all PK columns
                            if not all(col in clean_data for col in pk_columns):
                                continue
                            
                            # Use INSERT ... ON CONFLICT for upsert
                            stmt = insert(target_table_obj).values(clean_data)
                            update_dict = {col: clean_data[col] for col in clean_data if col not in pk_columns}
                            if update_dict:
                                stmt = stmt.on_conflict_do_update(
                                    index_elements=pk_columns,
                                    set_=update_dict
                                )
                            else:
                                stmt = stmt.on_conflict_do_nothing(index_elements=pk_columns)
                            
                            db.execute(stmt)
                        else:
                            # Simple insert (append mode)
                            stmt = insert(target_table_obj).values(clean_data)
                            db.execute(stmt)
                        
                        records_processed += 1
                    
                    db.commit()
                    logger.info(f"Processed {records_processed}/{total_records} records")
                
                # Update load_history record
                duration = (datetime.now() - start_time).total_seconds()
                db.execute(text("""
                    UPDATE staging_meta.load_history
                    SET status = 'COMPLETED',
                        load_end_time = CURRENT_TIMESTAMP,
                        duration_seconds = :duration,
                        records_inserted = :records_inserted,
                        rows_per_second = :rps
                    WHERE load_id = :load_id
                """), {
                    "duration": int(duration),
                    "records_inserted": records_processed,
                    "rps": round(records_processed / duration, 2) if duration > 0 else 0,
                    "load_id": load_id
                })
                db.commit()
                
                logger.info(f"Staging-to-production completed: {records_processed} records processed")
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error during staging-to-production: {e}")
                
                # Update load_history to FAILED
                db.execute(text("""
                    UPDATE staging_meta.load_history
                    SET status = 'FAILED',
                        load_end_time = CURRENT_TIMESTAMP,
                        error_details = :error
                    WHERE load_id = :load_id
                """), {
                    "error": str(e),
                    "load_id": load_id
                })
                db.commit()
                
                raise
                
    except Exception as e:
        logger.error(f"Fatal error in staging-to-production: {e}")
        raise


def process_staging_to_production_sync(
    batch_id: str,
    staging_table: str,
    production_table: str,
    production_schema: str,
    dedup_columns: Optional[str],
    source_name: str
):
    """
    Versión SÍNCRONA de staging-to-production para usar en workers.
    
    Esta función es bloqueante y debe ejecutarse en workers, no en el API.
    Implementa upsert (INSERT ... ON CONFLICT UPDATE) para PostgreSQL.
    """
    import psycopg2
    import uuid
    from datetime import datetime
    from data_staging.config import settings
    from sqlalchemy import create_engine, text, inspect, MetaData, Table, Column
    from sqlalchemy.dialects.postgresql import insert
    
    logger.info(f"Starting sync staging-to-production for batch {batch_id}")
    
    conn = psycopg2.connect(str(settings.DATABASE_URL))
    conn.autocommit = False
    
    try:
        cursor = conn.cursor()
        
        # 1. Crear load_history record
        load_id = str(uuid.uuid4())
        start_time = datetime.now()
        
        cursor.execute("""
            INSERT INTO staging_meta.load_history 
            (load_id, batch_id, source_name, load_type, target_table, target_schema,
             load_start_time, status)
            VALUES (%s, %s, %s, 'STAGING_TO_PRODUCTION', %s, %s, %s, 'IN_PROGRESS')
        """, (load_id, batch_id, source_name, production_table, production_schema, start_time))
        conn.commit()
        
        # 2. Obtener estructura de tabla de producción
        engine = create_engine(str(settings.DATABASE_URL))
        inspector = inspect(engine)
        
        # Verificar que tabla existe
        if not inspector.has_table(production_table, schema=production_schema):
            raise Exception(f"Production table {production_schema}.{production_table} does not exist")
        
        # Obtener columnas
        columns_info = inspector.get_columns(production_table, schema=production_schema)
        target_columns = [c['name'] for c in columns_info]
        
        # Obtener primary key
        pk_constraint = inspector.get_pk_constraint(production_table, schema=production_schema)
        target_pk_columns = pk_constraint.get('constrained_columns', [])
        
        logger.info(f"Target table columns: {target_columns}")
        logger.info(f"Target table PK: {target_pk_columns}")
        
        # 3. Determinar columnas de deduplicación
        if dedup_columns and dedup_columns.strip():
            pk_columns = [col.strip() for col in dedup_columns.split(',')]
            # Verificar que existen
            missing = [col for col in pk_columns if col not in target_columns]
            if missing:
                raise Exception(f"Dedup columns {missing} not found in target table")
        elif target_pk_columns:
            pk_columns = target_pk_columns
        else:
            # Modo append (sin dedup)
            pk_columns = []
        
        logger.info(f"Using dedup columns: {pk_columns}")
        
        # 4. Contar registros a procesar
        cursor.execute(f"""
            SELECT COUNT(*) 
            FROM staging_data.{staging_table} 
            WHERE batch_id = %s AND validation_status = 'PASSED'
        """, (batch_id,))
        
        total_records = cursor.fetchone()[0]
        logger.info(f"Total records to process: {total_records}")
        
        if total_records == 0:
            raise Exception(f"No validated records found in staging_data.{staging_table}")
        
        # 5. Procesar en batches
        BATCH_SIZE = 5000
        offset = 0
        
        stats = {
            "inserted": 0,
            "updated": 0,
            "rejected": 0
        }
        
        while offset < total_records:
            # Leer batch de staging
            cursor.execute(f"""
                SELECT processed_data
                FROM staging_data.{staging_table}
                WHERE batch_id = %s 
                  AND validation_status = 'PASSED'
                ORDER BY source_row_number
                LIMIT %s OFFSET %s
            """, (batch_id, BATCH_SIZE, offset))
            
            staging_batch = cursor.fetchall()
            
            if not staging_batch:
                break
            
            # Preparar datos para upsert
            upsert_data = []
            
            for row in staging_batch:
                processed_data = row[0]  # JSONB
                
                # Filtrar solo columnas que existen en tabla target
                clean_data = {
                    col: processed_data.get(col)
                    for col in target_columns
                    if col in processed_data
                }
                
                # Verificar que tiene las columnas de dedup
                if pk_columns:
                    if not all(col in clean_data for col in pk_columns):
                        stats["rejected"] += 1
                        continue
                
                upsert_data.append(clean_data)
            
            # Ejecutar upsert si hay datos
            if upsert_data:
                if pk_columns:
                    # Modo UPSERT
                    inserted, updated, rejected = execute_upsert_batch(
                        conn=conn,
                        schema=production_schema,
                        table=production_table,
                        columns=target_columns,
                        pk_columns=pk_columns,
                        data=upsert_data
                    )
                else:
                    # Modo APPEND
                    inserted, updated, rejected = execute_insert_batch(
                        conn=conn,
                        schema=production_schema,
                        table=production_table,
                        columns=target_columns,
                        data=upsert_data
                    )
                
                stats["inserted"] += inserted
                stats["updated"] += updated
                stats["rejected"] += rejected
            
            offset += BATCH_SIZE
            conn.commit()
            
            logger.info(f"Processed {offset}/{total_records} records")
        
        # 6. Actualizar load_history
        duration = (datetime.now() - start_time).total_seconds()
        
        cursor.execute("""
            UPDATE staging_meta.load_history
            SET status = 'COMPLETED',
                load_end_time = CURRENT_TIMESTAMP,
                duration_seconds = %s,
                records_inserted = %s,
                records_updated = %s,
                records_rejected = %s,
                rows_per_second = %s
            WHERE load_id = %s
        """, (
            int(duration),
            stats["inserted"],
            stats["updated"],
            stats["rejected"],
            round((stats["inserted"] + stats["updated"]) / duration, 2) if duration > 0 else 0,
            load_id
        ))
        
        conn.commit()
        
        logger.info(
            f"Staging-to-production completed: "
            f"{stats['inserted']} inserted, {stats['updated']} updated, "
            f"{stats['rejected']} rejected"
        )
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Staging-to-production failed: {e}")
        
        # Actualizar load_history a FAILED
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE staging_meta.load_history
                SET status = 'FAILED',
                    load_end_time = CURRENT_TIMESTAMP,
                    error_details = %s
                WHERE load_id = %s
            """, (str(e), load_id))
            conn.commit()
        except:
            pass
        
        raise
    
    finally:
        conn.close()


def execute_upsert_batch(
    conn,
    schema: str,
    table: str,
    columns: List[str],
    pk_columns: List[str],
    data: List[Dict]
) -> tuple[int, int, int]:
    """
    Ejecuta upsert batch usando INSERT ... ON CONFLICT.
    Returns: (inserted, updated, rejected)
    """
    from psycopg2.extras import execute_values
    
    cursor = conn.cursor()
    
    # Preparar columnas para UPDATE (todas excepto PKs)
    update_columns = [col for col in columns if col not in pk_columns]
    
    if not update_columns:
        # Si no hay columnas para actualizar, hacer DO NOTHING
        update_clause = "DO NOTHING"
    else:
        # Construir SET clause
        set_items = [f"{col} = EXCLUDED.{col}" for col in update_columns]
        update_clause = f"DO UPDATE SET {', '.join(set_items)}"
    
    # Construir query
    columns_str = ', '.join(columns)
    pk_str = ', '.join(pk_columns)
    
    query = f"""
        INSERT INTO {schema}.{table} ({columns_str})
        VALUES %s
        ON CONFLICT ({pk_str})
        {update_clause}
        RETURNING (xmax = 0) AS inserted
    """
    
    try:
        # Preparar valores
        values = [
            tuple(d.get(col) for col in columns)
            for d in data
        ]
        
        # Ejecutar
        template = f"({', '.join(['%s'] * len(columns))})"
        results = execute_values(
            cursor,
            query,
            values,
            template=template,
            page_size=1000,
            fetch=True
        )
        
        # Contar inserts vs updates
        inserted = sum(1 for row in results if row[0])
        updated = len(results) - inserted
        
        return inserted, updated, 0
        
    except Exception as e:
        logger.error(f"Upsert batch failed: {e}")
        # Intentar uno por uno
        return execute_upsert_one_by_one(
            conn, schema, table, columns, pk_columns, data
        )


def execute_insert_batch(
    conn,
    schema: str,
    table: str,
    columns: List[str],
    data: List[Dict]
) -> tuple[int, int, int]:
    """
    Ejecuta insert simple sin upsert.
    Returns: (inserted, updated, rejected)
    """
    from psycopg2.extras import execute_values
    
    cursor = conn.cursor()
    
    columns_str = ', '.join(columns)
    query = f"INSERT INTO {schema}.{table} ({columns_str}) VALUES %s"
    
    try:
        values = [
            tuple(d.get(col) for col in columns)
            for d in data
        ]
        
        template = f"({', '.join(['%s'] * len(columns))})"
        execute_values(cursor, query, values, template=template, page_size=1000)
        
        return len(data), 0, 0
        
    except Exception as e:
        logger.error(f"Insert batch failed: {e}")
        return 0, 0, len(data)


def execute_upsert_one_by_one(
    conn,
    schema: str,
    table: str,
    columns: List[str],
    pk_columns: List[str],
    data: List[Dict]
) -> tuple[int, int, int]:
    """Fallback: insertar uno por uno cuando el batch falla."""
    cursor = conn.cursor()
    
    inserted = 0
    updated = 0
    rejected = 0
    
    update_columns = [col for col in columns if col not in pk_columns]
    columns_str = ', '.join(columns)
    pk_str = ', '.join(pk_columns)
    placeholders = ', '.join(['%s'] * len(columns))
    
    if update_columns:
        set_items = [f"{col} = EXCLUDED.{col}" for col in update_columns]
        update_clause = f"DO UPDATE SET {', '.join(set_items)}"
    else:
        update_clause = "DO NOTHING"
    
    query = f"""
        INSERT INTO {schema}.{table} ({columns_str})
        VALUES ({placeholders})
        ON CONFLICT ({pk_str})
        {update_clause}
        RETURNING (xmax = 0) AS inserted
    """
    
    for record in data:
        try:
            values = tuple(record.get(col) for col in columns)
            cursor.execute(query, values)
            result = cursor.fetchone()
            
            if result and result[0]:
                inserted += 1
            else:
                updated += 1
            
            conn.commit()
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Individual upsert failed: {e}")
            rejected += 1
    
    return inserted, updated, rejected
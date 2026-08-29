"""Create batch_control records for wizard uploads and scheduled incremental loads."""

from __future__ import annotations

import json
import logging
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from data_staging.utils.load_storage_paths import load_storage_metadata_fields

logger = logging.getLogger(__name__)


def save_source_file_to_storage(
    source_path: Path,
    batch_id: str,
    storage_dir: Path,
    *,
    target_column_types: Optional[Dict[str, str]] = None,
) -> Tuple[Path, Dict[str, Any]]:
    """Copy a file from disk into storage_dir; CSV → typed .raw.parquet."""
    from data_staging.api.v1.upload import upload_service

    storage_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = storage_dir / f"{batch_id}_{timestamp}_{source_path.name}"
    shutil.copy2(source_path, dest)

    file_analysis: Dict[str, Any]
    if dest.suffix.lower() == ".csv":
        file_analysis = upload_service.analyze_file_structure(dest)
        if file_analysis.get("error"):
            raise ValueError(file_analysis["error"])
        from data_staging.utils.raw_parquet import csv_to_raw_parquet

        raw_parquet = csv_to_raw_parquet(
            dest,
            delimiter=file_analysis.get("delimiter", ","),
            target_column_types=target_column_types,
        )
        dest.unlink(missing_ok=True)
        file_analysis["logical_file_type"] = "csv"
        file_analysis["stored_format"] = "raw_parquet"
        return raw_parquet, file_analysis

    file_analysis = upload_service.analyze_file_structure(dest)
    if file_analysis.get("error"):
        raise ValueError(file_analysis["error"])
    return dest, file_analysis


def build_batch_metadata(
    *,
    file_path: Path,
    file_analysis: Dict[str, Any],
    organization_id: str,
    load_type: str,
    storage_dir: Path,
    load_timestamp: datetime,
    target_schema: Optional[str] = None,
    target_table: Optional[str] = None,
    process_type: Optional[str] = None,
    catalog_name: Optional[str] = None,
    production_table: Optional[str] = None,
    target_column_types: Optional[Dict[str, str]] = None,
    column_mappings: Optional[Dict[str, Any]] = None,
    column_toggles: Optional[Dict[str, Any]] = None,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Assemble metadata JSON for a new batch."""
    file_headers: List[str] = file_analysis.get("columns", [])
    file_path_str = str(file_path)
    metadata: Dict[str, Any] = {
        "file_analysis": file_analysis,
        "file_headers": file_headers,
        "file_path": file_path_str,
        "original_file_path": file_path_str,
        "target_schema": target_schema,
        "target_table": target_table,
        "load_type": load_type,
        "process_type": process_type if load_type == "history" else None,
        "organization_id": organization_id,
        **load_storage_metadata_fields(storage_dir, organization_id, load_timestamp),
    }
    if catalog_name:
        metadata["catalog_name"] = catalog_name
        metadata["production_table"] = production_table
    if load_type == "history":
        from data_staging.services.history.history_config import get_history_table_meta

        table_name = target_table or "sales_history"
        metadata["history_config"] = get_history_table_meta(table_name)
        metadata["unique_keys"] = get_history_table_meta(table_name).get("unique_keys", [])
    if target_column_types:
        metadata["target_column_types"] = target_column_types
    if column_mappings:
        metadata["column_mappings"] = column_mappings
    if column_toggles:
        metadata["column_toggles"] = column_toggles
    if extra_metadata:
        metadata.update(extra_metadata)
    return metadata


def insert_batch_control(
    db: Session,
    *,
    batch_id: str,
    source_name: str,
    file_name: str,
    file_path: str,
    file_size: int,
    organization_id: str,
    metadata: Dict[str, Any],
    status: str = "PENDING_MAPPING",
) -> str:
    """Insert batch_control row; returns batch_id."""
    db.execute(
        text("""
            INSERT INTO staging_meta.batch_control
            (batch_id, source_name, source_type, file_name, file_path, file_size,
             status, metadata, organization_id, retry_count, max_retries,
             created_at, updated_at)
            VALUES (
                :batch_id, :source_name, 'file', :file_name, :file_path, :file_size,
                :status, :metadata, :organization_id, 0, 3,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """),
        {
            "batch_id": batch_id,
            "source_name": source_name,
            "file_name": file_name,
            "file_path": file_path,
            "file_size": file_size,
            "metadata": json.dumps(metadata),
            "organization_id": organization_id,
            "status": status,
        },
    )
    return batch_id


def create_incremental_batch(
    db: Session,
    *,
    organization_id: str,
    source_file: Path,
    storage_dir: Path,
    load_type: str,
    load_timestamp: datetime,
    target_schema: Optional[str],
    target_table: Optional[str],
    source_name: str,
    process_type: Optional[str] = None,
    catalog_name: Optional[str] = None,
    production_table: Optional[str] = None,
    column_mappings: Optional[Dict[str, Any]] = None,
    column_toggles: Optional[Dict[str, Any]] = None,
    incremental_run_id: Optional[str] = None,
    target_column_types: Optional[Dict[str, str]] = None,
) -> str:
    """Create a batch for scheduled incremental processing (mappings pre-applied)."""
    batch_id = str(uuid.uuid4())
    file_path, file_analysis = save_source_file_to_storage(
        source_file,
        batch_id,
        storage_dir,
        target_column_types=target_column_types,
    )
    extra: Dict[str, Any] = {
        "scheduled_load": True,
        "source_file_path": str(source_file),
        "load_storage_dir": str(storage_dir),
    }
    if incremental_run_id:
        extra["incremental_run_id"] = incremental_run_id
    if load_type == "catalog":
        extra["preserve_upload_files"] = True

    metadata = build_batch_metadata(
        file_path=file_path,
        file_analysis=file_analysis,
        organization_id=organization_id,
        load_type=load_type,
        storage_dir=storage_dir,
        load_timestamp=load_timestamp,
        target_schema=target_schema,
        target_table=target_table,
        process_type=process_type,
        catalog_name=catalog_name,
        production_table=production_table,
        target_column_types=target_column_types,
        column_mappings=column_mappings,
        column_toggles=column_toggles,
        extra_metadata=extra,
    )
    if load_type == "history":
        from data_staging.services.history.history_config import source_from_filename

        metadata["source_extension"] = source_from_filename(source_file.name)

    insert_batch_control(
        db,
        batch_id=batch_id,
        source_name=source_name,
        file_name=source_file.name,
        file_path=str(file_path),
        file_size=file_path.stat().st_size,
        organization_id=organization_id,
        metadata=metadata,
        status="PENDING_PREVIEW",
    )
    return batch_id


def update_batch_mappings(
    db: Session,
    *,
    batch_id: str,
    organization_id: str,
    column_mappings: Dict[str, Any],
    column_toggles: Dict[str, Any],
    load_type: str,
) -> None:
    """Apply column mappings and set status for pipeline start."""
    row = db.execute(
        text("SELECT metadata FROM staging_meta.batch_control WHERE batch_id = :batch_id"),
        {"batch_id": batch_id},
    ).fetchone()
    if not row:
        raise ValueError(f"Batch {batch_id} not found")
    metadata = row.metadata if isinstance(row.metadata, dict) else json.loads(row.metadata or "{}")
    metadata["column_mappings"] = column_mappings
    metadata["column_toggles"] = column_toggles
    metadata["organization_id"] = organization_id

    db.execute(
        text("""
            UPDATE staging_meta.batch_control
            SET metadata = :metadata,
                organization_id = :organization_id,
                status = 'PENDING_PREVIEW',
                updated_at = CURRENT_TIMESTAMP
            WHERE batch_id = :batch_id
        """),
        {
            "metadata": json.dumps(metadata),
            "organization_id": organization_id,
            "batch_id": batch_id,
        },
    )

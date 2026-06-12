"""Background preview job (PREVIEW_BATCH) — validation + aggregation for wizard Step 3."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

from sqlalchemy import text

from data_staging.config import settings
from data_staging.database import get_database_session
from data_staging.utils.batch_control import (
    normalize_metadata,
    resolve_original_file_path,
    with_file_path,
)
from data_staging.auth.security import ensure_organization_id_mapping

logger = logging.getLogger(__name__)


def execute_preview_pipeline(batch_id: str, org_id: str) -> None:
    """Runs preview pipeline (same validation rules as sync path)."""
    from data_staging.api.v1.upload import (
        _build_preview_response_payload,
        _resolve_preview_encoding,
    )

    db = get_database_session()
    try:
        db.execute(text("SET LOCAL statement_timeout = '0'"))
        result = db.execute(
            text("""
                SELECT batch_id, metadata, source_name, file_path
                FROM staging_meta.batch_control
                WHERE batch_id = :batch_id
            """),
            {"batch_id": batch_id},
        )
        batch = result.fetchone()
        if not batch:
            return

        metadata = normalize_metadata(batch.metadata)
        file_path = resolve_original_file_path(
            metadata, file_path_column=getattr(batch, "file_path", None)
        )
        if not file_path or not Path(file_path).is_file():
            metadata["preview_in_progress"] = False
            metadata["preview_error"] = (
                "No se encontró el archivo original del batch. "
                "Vuelve al paso 1 y sube el archivo de nuevo."
            )
            db.execute(
                text("""
                    UPDATE staging_meta.batch_control
                    SET metadata = :metadata, updated_at = CURRENT_TIMESTAMP
                    WHERE batch_id = :batch_id
                """),
                {"metadata": json.dumps(metadata), "batch_id": batch_id},
            )
            db.commit()
            return

        column_mappings, column_toggles = ensure_organization_id_mapping(
            metadata.get("column_mappings", {}),
            metadata.get("column_toggles", {}),
            org_id,
        )
        metadata["column_mappings"] = column_mappings
        metadata["column_toggles"] = column_toggles
        metadata["organization_id"] = org_id
        load_type = metadata.get("load_type", "history")
        process_type = metadata.get("process_type")
        file_analysis = metadata.get("file_analysis", {}) or {}
        delimiter = file_analysis.get("delimiter", ",")
        target_table = metadata.get("target_table", "")
        encoding = _resolve_preview_encoding(file_path, file_analysis)
        if encoding != file_analysis.get("encoding"):
            file_analysis = {**file_analysis, "encoding": encoding}
            metadata["file_analysis"] = file_analysis

        agg_stats: Dict[str, Any]
        agg_file_path: Path

        if load_type == "catalog":
            from data_staging.services.catalog_preview_service import (
                process_catalog_preview_light,
                CatalogPreviewError,
            )

            try:
                agg_stats, agg_file_path = process_catalog_preview_light(
                    file_path=file_path,
                    target_table=target_table,
                    column_mappings=column_mappings,
                    column_toggles=column_toggles,
                    encoding=encoding,
                    delimiter=delimiter,
                    organization_id=org_id,
                )
                process_type = "Catalog"
            except CatalogPreviewError as ce:
                metadata["preview_in_progress"] = False
                metadata["preview_error"] = str(ce)
                db.execute(
                    text("""
                        UPDATE staging_meta.batch_control
                        SET metadata = :metadata, updated_at = CURRENT_TIMESTAMP
                        WHERE batch_id = :batch_id
                    """),
                    {"metadata": json.dumps(metadata), "batch_id": batch_id},
                )
                db.commit()
                return
        else:
            from data_staging.services.history.history_preview_pipeline import (
                process_history_preview_with_validation,
            )
            from data_staging.utils.batch_staging_files import rejected_records_path

            try:
                agg_stats, agg_file_path = process_history_preview_with_validation(
                    batch_id=batch_id,
                    file_path=file_path,
                    column_mappings=column_mappings,
                    column_toggles=column_toggles,
                    process_type=process_type,
                    encoding=encoding,
                    delimiter=delimiter,
                    organization_id=org_id,
                    metadata=metadata,
                    file_name=getattr(batch, "source_name", "") or "",
                )
            except Exception as exc:
                logger.exception("History preview pipeline failed for batch %s", batch_id)
                metadata["preview_in_progress"] = False
                metadata["preview_error"] = str(exc)
                db.execute(
                    text("""
                        UPDATE staging_meta.batch_control
                        SET metadata = :metadata, updated_at = CURRENT_TIMESTAMP
                        WHERE batch_id = :batch_id
                    """),
                    {"metadata": json.dumps(metadata), "batch_id": batch_id},
                )
                db.commit()
                return

            rejected_path = str(rejected_records_path(batch_id).resolve())
            metadata["rejected_temp_file"] = rejected_path
            metadata["validated_in_preview"] = True
            ctx_cols = metadata.get("column_mappings") or {}
            source_cols = [
                fc for fc, cfg in ctx_cols.items()
                if isinstance(cfg, dict) and cfg.get("target") and not str(fc).startswith("__")
            ]
            if source_cols:
                metadata["source_file_columns"] = source_cols

            valid_rows = int(agg_stats.get("valid_rows") or 0)
            rejected_rows = int(agg_stats.get("rejected_rows") or 0)
            metadata["processing_stats"] = {
                "total_inserted": valid_rows,
                "total_rejected": rejected_rows,
            }

            if not agg_stats.get("has_error"):
                agg_path = str(agg_file_path)
                metadata["aggregated_file_path"] = agg_path
                metadata["valid_temp_file"] = agg_path
                metadata["valid_file_format"] = "parquet"
                metadata = with_file_path(metadata, agg_path)

        metadata["wizard_step"] = 3
        metadata["preview_generated"] = True
        metadata["preview_in_progress"] = False
        metadata.pop("preview_error", None)

        batch_status = "PENDING_PROCESS"
        records_count = None
        if load_type == "history" and metadata.get("validated_in_preview"):
            if not agg_stats.get("has_error"):
                batch_status = "COMPLETED"
                records_count = int(
                    agg_stats.get("grouped_rows") or agg_stats.get("valid_rows") or 0
                )
            else:
                batch_status = "PENDING_PREVIEW"

        response_payload = _build_preview_response_payload(
            batch_id=batch_id,
            batch_source_name=getattr(batch, "source_name", "") or "",
            metadata=metadata,
            agg_stats=agg_stats,
            org_id=org_id,
            load_type=load_type,
            process_type=process_type,
        )
        metadata["preview_result"] = response_payload

        from data_staging.workers.file_processor import open_progress_connection, report_processing_progress

        progress_conn = open_progress_connection()
        try:
            final_stats = metadata.get("processing_stats", {}) or {}
            valid_rows = int(final_stats.get("total_inserted") or records_count or 0)
            rejected_rows = int(final_stats.get("total_rejected") or 0)
            total_rows = valid_rows + rejected_rows
            report_processing_progress(
                progress_conn,
                batch_id,
                progress_percentage=100,
                current_operation="Vista previa lista",
                phase="preview_done",
                total_rows=total_rows,
                rows_processed=total_rows,
                loaded_rows=valid_rows,
                rejected_rows=rejected_rows,
                force=True,
            )
        finally:
            try:
                progress_conn.close()
            except Exception:
                pass

        update_sql = """
            UPDATE staging_meta.batch_control
            SET metadata = :metadata,
                status = :status,
                updated_at = CURRENT_TIMESTAMP
        """
        update_params = {
            "metadata": json.dumps(metadata),
            "batch_id": batch_id,
            "status": batch_status,
        }
        if records_count is not None:
            update_sql += ", records_count = :records_count"
            update_params["records_count"] = records_count
        if metadata.get("aggregated_file_path"):
            update_sql += ", file_path = :file_path"
            update_params["file_path"] = metadata["aggregated_file_path"]
        update_sql += " WHERE batch_id = :batch_id"

        db.execute(text(update_sql), update_params)
        db.commit()
        logger.info("Preview generated for batch %s (worker)", batch_id)
    except Exception as exc:
        logger.exception("Background preview failed for batch %s", batch_id)
        try:
            db.rollback()
            err_meta = normalize_metadata(
                db.execute(
                    text("SELECT metadata FROM staging_meta.batch_control WHERE batch_id = :batch_id"),
                    {"batch_id": batch_id},
                ).scalar()
            )
            err_meta["preview_in_progress"] = False
            err_meta["preview_error"] = str(exc)
            db.execute(
                text("""
                    UPDATE staging_meta.batch_control
                    SET metadata = :metadata, updated_at = CURRENT_TIMESTAMP
                    WHERE batch_id = :batch_id
                """),
                {"metadata": json.dumps(err_meta), "batch_id": batch_id},
            )
            db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()


def preview_batch_job(payload: Dict[str, Any]) -> None:
    """Job queue handler for PREVIEW_BATCH."""
    batch_id = payload.get("batch_id")
    org_id = payload.get("organization_id")
    if not batch_id or not org_id:
        raise ValueError("PREVIEW_BATCH payload requires batch_id and organization_id")
    execute_preview_pipeline(str(batch_id), str(org_id))

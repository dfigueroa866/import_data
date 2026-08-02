"""Background validation job (VALIDATE_BATCH) — wizard after step 1 auto-mapping."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

from sqlalchemy import text

from data_staging.config import settings
from data_staging.database import get_database_session
from data_staging.utils.batch_control import normalize_metadata, resolve_original_file_path
from data_staging.auth.security import ensure_organization_id_mapping
from data_staging.utils.batch_cancel import BatchCancelledError, raise_if_batch_cancelled

logger = logging.getLogger(__name__)


def execute_validation_pipeline(batch_id: str, org_id: str) -> None:
    """Validate all rows after mapping (Step 2); writes validated + rejected files."""
    from data_staging.api.v1.upload import _resolve_preview_encoding
    from data_staging.services.catalog.catalog_preview_pipeline import run_catalog_validation_only
    from data_staging.services.history.history_preview_pipeline import run_history_validation_only
    from data_staging.services.history.history_preview_pipeline import validated_intermediate_path
    from data_staging.utils.batch_staging_files import rejected_records_path
    from data_staging.workers.file_processor import open_progress_connection, report_processing_progress

    db = get_database_session()
    try:
        db.execute(text("SET LOCAL statement_timeout = '0'"))
        result = db.execute(
            text("""
                SELECT batch_id, metadata, source_name, file_path,
                       COALESCE(organization_id, metadata->>'organization_id') AS organization_id
                FROM staging_meta.batch_control
                WHERE batch_id = :batch_id
            """),
            {"batch_id": batch_id},
        )
        batch = result.fetchone()
        if not batch:
            return

        raise_if_batch_cancelled(batch_id)

        metadata = normalize_metadata(batch.metadata)
        resolved_org = str(org_id or getattr(batch, "organization_id", "") or "").strip()
        if not resolved_org:
            raise ValueError(f"organization_id is required for VALIDATE_BATCH on batch {batch_id}")
        org_id = resolved_org
        load_type = metadata.get("load_type", "history")
        if load_type not in ("history", "catalog"):
            metadata["validation_in_progress"] = False
            metadata["validation_complete"] = True
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

        file_path = resolve_original_file_path(
            metadata, file_path_column=getattr(batch, "file_path", None)
        )
        if not file_path or not Path(file_path).is_file():
            metadata["validation_in_progress"] = False
            metadata["validation_error"] = (
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

        process_type = metadata.get("process_type")
        file_analysis = metadata.get("file_analysis", {}) or {}
        delimiter = file_analysis.get("delimiter", ",")
        encoding = _resolve_preview_encoding(file_path, file_analysis)
        if encoding != file_analysis.get("encoding"):
            file_analysis = {**file_analysis, "encoding": encoding}
            metadata["file_analysis"] = file_analysis

        try:
            if load_type == "catalog":
                validation_stats = run_catalog_validation_only(
                    batch_id=batch_id,
                    file_path=file_path,
                    column_mappings=column_mappings,
                    column_toggles=column_toggles,
                    encoding=encoding,
                    delimiter=delimiter,
                    organization_id=org_id,
                    metadata=metadata,
                    file_name=getattr(batch, "source_name", "") or "",
                )
            else:
                validation_stats = run_history_validation_only(
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
        except BatchCancelledError:
            raise
        except Exception as exc:
            logger.exception("Validation pipeline failed for batch %s", batch_id)
            metadata["validation_in_progress"] = False
            metadata["validation_error"] = str(exc)
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

        validated_path = validated_intermediate_path(batch_id, metadata)
        rejected_path = rejected_records_path(batch_id, metadata)

        metadata["validated_temp_file"] = str(validated_path.resolve())
        metadata["rejected_temp_file"] = str(rejected_path.resolve())
        metadata["validation_complete"] = True
        metadata["validation_in_progress"] = False
        metadata["validated_at_step"] = metadata.get("wizard_step", 1)
        metadata.pop("validation_error", None)
        metadata.pop("preview_result", None)
        metadata["preview_generated"] = False
        metadata["validated_in_preview"] = True

        valid_rows = int(validation_stats.get("valid_rows") or 0)
        rejected_rows = int(validation_stats.get("rejected_rows") or 0)
        metadata["processing_stats"] = {
            "total_inserted": valid_rows,
            "total_rejected": rejected_rows,
        }

        ctx_cols = metadata.get("column_mappings") or {}
        source_cols = [
            fc
            for fc, cfg in ctx_cols.items()
            if isinstance(cfg, dict) and cfg.get("target") and not str(fc).startswith("__")
        ]
        if source_cols:
            metadata["source_file_columns"] = source_cols

        metadata["wizard_step"] = 2

        progress_conn = open_progress_connection()
        try:
            total_rows = valid_rows + rejected_rows
            report_processing_progress(
                progress_conn,
                batch_id,
                progress_percentage=100,
                current_operation="Validación de mapeo completada",
                phase="mapping_validation_done",
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

        db.execute(
            text("""
                UPDATE staging_meta.batch_control
                SET metadata = :metadata,
                    status = 'PENDING_PREVIEW',
                    updated_at = CURRENT_TIMESTAMP
                WHERE batch_id = :batch_id AND status != 'CANCELLED'
            """),
            {"metadata": json.dumps(metadata), "batch_id": batch_id},
        )
        db.commit()
        logger.info("Mapping validation completed for batch %s (worker)", batch_id)
    except BatchCancelledError:
        logger.info("Validation cancelled for batch %s (worker)", batch_id)
        try:
            db.rollback()
            db.execute(
                text("""
                    UPDATE staging_meta.batch_control
                    SET metadata = metadata || jsonb_build_object(
                            'validation_in_progress', false
                        ),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE batch_id = :batch_id AND status = 'CANCELLED'
                """),
                {"batch_id": batch_id},
            )
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
        raise
    except Exception as exc:
        logger.exception("Background validation failed for batch %s", batch_id)
        try:
            db.rollback()
            err_meta = normalize_metadata(
                db.execute(
                    text("SELECT metadata FROM staging_meta.batch_control WHERE batch_id = :batch_id"),
                    {"batch_id": batch_id},
                ).scalar()
            )
            err_meta["validation_in_progress"] = False
            err_meta["validation_error"] = str(exc)
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


def validate_batch_job(payload: Dict[str, Any]) -> None:
    """Job queue handler for VALIDATE_BATCH."""
    batch_id = payload.get("batch_id")
    org_id = payload.get("organization_id")
    if not batch_id or not org_id:
        raise ValueError("VALIDATE_BATCH payload requires batch_id and organization_id")
    execute_validation_pipeline(str(batch_id), str(org_id))

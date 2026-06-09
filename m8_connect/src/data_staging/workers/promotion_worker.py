
import logging
import json
import psycopg2
import psycopg2.extras
import os
import itertools
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Tuple

import pandas as pd

from data_staging.config import settings
from data_staging.utils.batch_staging_files import (
    find_valid_records_file,
    is_parquet_valid_file,
    metadata_merge_expr,
)
from data_staging.utils.pipeline_timing import PipelineTimer, persist_timing_metadata
from data_staging.utils.promotion_bulk import (
    build_upsert_from_staging_sql,
    build_values_upsert_sql,
    copy_arrow_batch_to_staging,
    copy_frame_to_staging,
    ensure_staging_table,
    frame_to_tuples,
)
from data_staging.workers.file_processor import report_processing_progress

logger = logging.getLogger(__name__)

PROMOTION_BATCH_SIZE = int(getattr(settings, "PROMOTION_BATCH_SIZE", 100_000))
PROMOTION_PROGRESS_EVERY_CHUNKS = int(
    getattr(settings, "PROMOTION_PROGRESS_EVERY_CHUNKS", 3)
)
PROMOTION_METADATA_EVERY_CHUNKS = int(
    getattr(settings, "PROMOTION_METADATA_EVERY_CHUNKS", 3)
)


def _promotion_chunks_total(total_rows: int) -> int:
    return max(1, (max(total_rows, 1) + PROMOTION_BATCH_SIZE - 1) // PROMOTION_BATCH_SIZE)


def report_promotion_progress(
    conn,
    batch_id: str,
    *,
    promote_total: int,
    rows_processed: int,
    chunks_processed: int,
    force: bool = False,
) -> None:
    """Persist promotion progress for wizard Step 4 polling."""
    if (
        not force
        and PROMOTION_PROGRESS_EVERY_CHUNKS > 1
        and chunks_processed % PROMOTION_PROGRESS_EVERY_CHUNKS != 0
    ):
        return
    chunks_total = _promotion_chunks_total(promote_total)
    pct = min(99.0, (rows_processed / max(promote_total, 1)) * 100) if promote_total else 0.0
    report_processing_progress(
        conn,
        batch_id,
        progress_percentage=pct,
        current_operation=(
            f"Promoviendo a producción ({rows_processed:,} de {promote_total:,} registros)…"
        ),
        phase="promoting",
        total_rows=promote_total,
        rows_processed=rows_processed,
        loaded_rows=rows_processed,
        rejected_rows=0,
        chunks_processed=chunks_processed,
        chunks_total=chunks_total,
    )

# Fallback si el catálogo no define unique_keys (nombres = columnas físicas en BD)
_CATALOG_UPSERT_KEYS_FALLBACK = {
    "skus": ["organization_id", "code"],
    "location": ["organization_id", "code"],
}

# Claves legacy en configs viejos → nombre real en tabla locations
_CONFLICT_KEY_ALIASES = {
    "location_code": "code",
    "location_name": "name",
}


def _resolve_db_column_name(
    key: str,
    db_columns: Dict[str, str],
    db_columns_lower: Dict[str, str],
) -> Optional[str]:
    if key in db_columns:
        return key
    lower = key.lower()
    if lower in db_columns_lower:
        return db_columns_lower[lower]
    alias = _CONFLICT_KEY_ALIASES.get(key) or _CONFLICT_KEY_ALIASES.get(lower)
    if alias:
        if alias in db_columns:
            return alias
        if alias.lower() in db_columns_lower:
            return db_columns_lower[alias.lower()]
    return None


def _resolve_history_conflict_columns(
    metadata: Dict[str, Any],
    db_columns: Dict[str, str],
    db_columns_lower: Dict[str, str],
    insert_columns: Set[str],
    unique_indexes: List[List[str]],
) -> List[str]:
    from data_staging.services.history.history_schema import (
        history_preferred_unique_keys,
        pick_upsert_conflict_columns,
    )

    preferred = history_preferred_unique_keys(metadata, set(db_columns.keys()))
    picked = pick_upsert_conflict_columns(
        preferred,
        insert_columns,
        unique_indexes,
        lambda key: _resolve_db_column_name(key, db_columns, db_columns_lower),
    )
    if picked:
        logger.info("History UPSERT ON CONFLICT (%s)", ", ".join(picked))
    else:
        logger.warning(
            "No hay índice único en sales_history compatible con columnas insertadas %s; "
            "se hará INSERT sin UPSERT",
            sorted(insert_columns),
        )
    return picked


def _resolve_catalog_conflict_columns(
    catalog_slug: Optional[str],
    metadata: Dict[str, Any],
    db_columns: Dict[str, str],
    db_columns_lower: Dict[str, str],
    insert_columns: Set[str],
    unique_indexes: List[List[str]],
) -> List[str]:
    """UPSERT: claves del catálogo alineadas a un índice único real en la tabla destino."""
    from data_staging.services.history.history_schema import pick_upsert_conflict_columns
    from data_staging.services.catalog.catalog_registry import get_catalog_table

    keys: List[str] = []
    if catalog_slug:
        entry = get_catalog_table(catalog_slug)
        if entry:
            keys = list(entry.get("unique_keys") or [])

    if not keys:
        keys = list(metadata.get("unique_keys") or [])

    if not keys and catalog_slug:
        keys = list(_CATALOG_UPSERT_KEYS_FALLBACK.get(catalog_slug.lower(), []))

    picked = pick_upsert_conflict_columns(
        keys,
        insert_columns,
        unique_indexes,
        lambda key: _resolve_db_column_name(key, db_columns, db_columns_lower),
    )
    if picked:
        logger.info("Catalog UPSERT ON CONFLICT (%s)", ", ".join(picked))
    elif keys:
        logger.warning(
            "No hay índice único compatible para catálogo %s (preferido: %s)",
            catalog_slug,
            keys,
        )
    return picked


def _catalog_upsert_clause(
    load_type: str,
    insert_cols: List[str],
    conflict_cols: Optional[List[str]] = None,
) -> str:
    if load_type not in ("catalog", "history") or not conflict_cols:
        return ""

    normalized = [c.strip('"') for c in insert_cols if c.strip('"') != "imported_at"]
    conflict_set = {c.lower() for c in conflict_cols}
    update_cols = [
        c for c in normalized if c.lower() not in conflict_set and c.lower() != "id"
    ]
    conflict_str = ", ".join(f'"{c}"' for c in conflict_cols)

    if not update_cols:
        return f"ON CONFLICT ({conflict_str}) DO NOTHING"

    set_clause = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in update_cols)
    return f"ON CONFLICT ({conflict_str}) DO UPDATE SET {set_clause}"


def _is_history_promotion(
    metadata: Dict[str, Any],
    target_schema: str,
    target_table: str,
    load_type: str,
) -> bool:
    from data_staging.services.history.history_config import (
        HISTORY_TARGET_TABLE,
        is_sales_history_target,
    )

    if (load_type or "").lower() == "history":
        return True
    if is_sales_history_target(target_schema, target_table):
        return True
    if metadata.get("history_config"):
        return True
    return (metadata.get("target_table") or "").lower() == HISTORY_TARGET_TABLE.lower()


def _ensure_history_valid_db_columns(
    valid_db_target_cols: List[str],
    db_columns: Dict[str, str],
    db_columns_lower: Dict[str, str],
) -> List[str]:
    from data_staging.services.history.history_config import HISTORY_AUTO_PROMOTION_COLUMNS

    seen = set(valid_db_target_cols)
    out = list(valid_db_target_cols)
    for col in HISTORY_AUTO_PROMOTION_COLUMNS:
        resolved = _resolve_db_column_name(col, db_columns, db_columns_lower)
        if resolved and resolved not in seen:
            out.append(resolved)
            seen.add(resolved)
    return out


def _parquet_promotion_columns(
    file_columns: List[str],
    valid_db_target_cols: List[str],
) -> List[str]:
    """Solo columnas presentes en el archivo temporal y válidas para la tabla destino."""
    valid_set = set(valid_db_target_cols)
    return [
        c
        for c in file_columns
        if c in valid_set and not str(c).startswith("_")
    ]


def _build_insert_context(
    cursor,
    metadata: Dict[str, Any],
    target_schema: str,
    target_table: str,
) -> Tuple[List[str], Dict[str, str], Dict[str, str], Dict[str, str], List[List[str]]]:
    wizard_mappings = metadata.get("column_mappings", {})
    target_columns: List[str] = []
    for _file_col, config in wizard_mappings.items():
        if config.get("target") and config.get("target") != "__new__":
            target_columns.append(config.get("target"))

    if not target_columns:
        old_mapping = metadata.get("column_mapping", {})
        if old_mapping:
            target_columns = list(old_mapping.keys())

    target_columns = list(set(target_columns))

    load_type = metadata.get("load_type", "history")
    history_promotion = _is_history_promotion(
        metadata, target_schema, target_table, load_type
    )
    if history_promotion:
        from data_staging.services.history.history_config import HISTORY_AUTO_PROMOTION_COLUMNS

        for auto_col in HISTORY_AUTO_PROMOTION_COLUMNS:
            if auto_col not in target_columns:
                target_columns.append(auto_col)
    system_managed: frozenset = frozenset()
    if load_type == "catalog":
        from data_staging.services.history.history_config import HISTORY_AUTO_PROMOTION_COLUMNS
        from data_staging.services.catalog.catalog_transforms import load_db_system_managed_columns_psycopg2

        system_managed = load_db_system_managed_columns_psycopg2(
            cursor, target_schema, target_table
        )

    cursor.execute(
        """
        SELECT column_name, data_type, udt_name
        FROM information_schema.columns
        WHERE LOWER(table_schema) = LOWER(%s) AND LOWER(table_name) = LOWER(%s)
        """,
        (target_schema, target_table),
    )
    db_columns: Dict[str, str] = {}
    db_udt_names: Dict[str, str] = {}
    for row in cursor.fetchall():
        col_name, data_type, udt_name = row[0], row[1], row[2]
        db_columns[col_name] = data_type
        if udt_name:
            db_udt_names[col_name] = udt_name
    db_columns_lower = {k.lower(): k for k in db_columns.keys()}

    valid_db_target_cols: List[str] = []
    for requested_col in target_columns:
        real_col_name = None
        if requested_col in db_columns:
            real_col_name = requested_col
        elif requested_col.lower() in db_columns_lower:
            real_col_name = db_columns_lower[requested_col.lower()]
        if real_col_name and real_col_name not in system_managed:
            valid_db_target_cols.append(real_col_name)

    if not valid_db_target_cols:
        raise ValueError(
            f"No columns matched between mapping and target table {target_schema}.{target_table}. "
            f"Available columns in DB: {list(db_columns.keys())}. Requested columns: {target_columns}"
        )

    if history_promotion:
        valid_db_target_cols = _ensure_history_valid_db_columns(
            valid_db_target_cols, db_columns, db_columns_lower
        )

    from data_staging.services.history.history_schema import discover_unique_indexes

    unique_indexes = discover_unique_indexes(cursor, target_schema, target_table)
    return valid_db_target_cols, db_columns, db_columns_lower, db_udt_names, unique_indexes


def _prepare_insert_query(
    valid_db_target_cols: List[str],
    db_columns: Dict[str, str],
    file_columns: List[str],
    target_schema: str,
    target_table: str,
    load_type: str,
    catalog_slug: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    db_columns_lower: Optional[Dict[str, str]] = None,
    unique_indexes: Optional[List[List[str]]] = None,
) -> Tuple[str, str, List[int], List[str]]:
    insert_cols: List[str] = []
    file_col_indices: List[int] = []

    for idx, col in enumerate(file_columns):
        if col in valid_db_target_cols:
            insert_cols.append(f'"{col}"')
            file_col_indices.append(idx)

    if "imported_at" in db_columns:
        insert_cols.append('"imported_at"')

    if not insert_cols:
        raise ValueError("No matching columns could be found between the temp file and target table.")

    insert_cols_str = ", ".join(insert_cols)
    template_values = "(" + ", ".join(["%s"] * len(file_col_indices))
    if "imported_at" in db_columns:
        template_values += ", NOW()"
    template_values += ")"

    conflict_cols: Optional[List[str]] = None
    meta = metadata or {}
    db_lower = db_columns_lower or {k.lower(): k for k in db_columns}
    insert_col_names = {c.strip('"') for c in insert_cols}
    indexes = unique_indexes or []
    if load_type == "catalog":
        conflict_cols = _resolve_catalog_conflict_columns(
            catalog_slug,
            meta,
            db_columns,
            db_lower,
            insert_col_names,
            indexes,
        )
    elif load_type == "history":
        conflict_cols = _resolve_history_conflict_columns(
            meta, db_columns, db_lower, insert_col_names, indexes
        )
    conflict_clause = _catalog_upsert_clause(load_type, insert_cols, conflict_cols)
    insert_query = f"""
        INSERT INTO {target_schema}.{target_table} ({insert_cols_str})
        VALUES %s
        {conflict_clause}
    """
    return insert_query, template_values, file_col_indices, insert_cols, conflict_clause


def _uses_upsert_update(conflict_clause: str) -> bool:
    return "DO UPDATE" in (conflict_clause or "").upper()


def _fetch_upsert_counts(cursor) -> Tuple[int, int, int]:
    row = cursor.fetchone()
    if not row:
        return 0, 0, 0
    affected, inserted, updated = int(row[0]), int(row[1]), int(row[2])
    return affected, inserted, updated


def _execute_promotion_batch(
    cursor,
    insert_query: str,
    template_values: str,
    chunk_data: List[tuple],
    conflict_clause: str,
) -> Tuple[int, int, int]:
    """
    Ejecuta un lote de INSERT/UPSERT y devuelve (filas_afectadas, insertadas, actualizadas).
    Usa CTE agregado para contadores exactos sin transferir una fila por registro a Python.
    """
    if not chunk_data:
        return 0, 0, 0

    sql = build_values_upsert_sql(insert_query, conflict_clause)
    psycopg2.extras.execute_values(
        cursor,
        sql,
        chunk_data,
        template=template_values,
        page_size=10000,
    )
    return _fetch_upsert_counts(cursor)


def _execute_staging_promotion_batch(
    cursor,
    target_schema: str,
    target_table: str,
    insert_cols: List[str],
    staging_cols: List[str],
    conflict_clause: str,
    data_cols: List[str],
    *,
    include_imported_at: bool,
    db_columns: Optional[Dict[str, str]] = None,
    db_udt_names: Optional[Dict[str, str]] = None,
    frame: Optional[pd.DataFrame] = None,
    arrow_batch=None,
) -> Tuple[int, int, int]:
    """COPY chunk to temp table, then UPSERT with aggregated RETURNING counts."""
    ensure_staging_table(cursor, staging_cols)
    arrow_min_rows = int(getattr(settings, "ARROW_COPY_MIN_ROWS", 10_000))
    if arrow_batch is not None and arrow_batch.num_rows >= arrow_min_rows:
        copied = copy_arrow_batch_to_staging(cursor, arrow_batch, data_cols, staging_cols)
    elif frame is not None and not frame.empty:
        copied = copy_frame_to_staging(cursor, frame, data_cols, staging_cols)
    elif arrow_batch is not None and arrow_batch.num_rows > 0:
        import pyarrow as pa

        frame = arrow_batch.to_pandas()
        copied = copy_frame_to_staging(cursor, frame, data_cols, staging_cols)
    else:
        return 0, 0, 0
    if copied == 0:
        return 0, 0, 0
    sql = build_upsert_from_staging_sql(
        target_schema,
        target_table,
        insert_cols,
        staging_cols,
        conflict_clause,
        include_imported_at=include_imported_at,
        db_columns=db_columns,
        db_udt_names=db_udt_names,
    )
    cursor.execute(sql)
    return _fetch_upsert_counts(cursor)


def _persist_promotion_chunk_metadata(
    conn,
    cursor,
    batch_id: str,
    metadata: Dict[str, Any],
    *,
    chunks_processed: int,
    force: bool = False,
) -> None:
    if (
        not force
        and PROMOTION_METADATA_EVERY_CHUNKS > 1
        and chunks_processed % PROMOTION_METADATA_EVERY_CHUNKS != 0
    ):
        return
    cursor.execute(
        f"""
        UPDATE staging_meta.batch_control
        SET metadata = {metadata_merge_expr("%s::jsonb")},
            updated_at = CURRENT_TIMESTAMP
        WHERE batch_id = %s
        """,
        (json.dumps(metadata), batch_id),
    )
    conn.commit()


def _apply_promotion_session_tuning(cursor) -> None:
    cursor.execute("SET statement_timeout = 0;")
    work_mem = getattr(settings, "PROMOTION_WORK_MEM", "256MB")
    if work_mem:
        cursor.execute(f"SET work_mem = '{work_mem}';")
    if not getattr(settings, "PROMOTION_SYNCHRONOUS_COMMIT", False):
        cursor.execute("SET synchronous_commit = off;")


def _merge_promotion_metadata(
    metadata: Dict[str, Any],
    *,
    promoted_rows: int,
    promoted_inserted: int,
    promoted_updated: int,
) -> Dict[str, Any]:
    return {
        **metadata,
        "promoted_rows": promoted_rows,
        "promoted_inserted": promoted_inserted,
        "promoted_updated": promoted_updated,
        "promoted_count": promoted_rows,
    }


def _row_tuple_from_values(raw_vals: List[str], file_col_indices: List[int]) -> tuple:
    return tuple(None if raw_vals[i] in ("\\N", "", None) else raw_vals[i] for i in file_col_indices)


def _promote_from_tsv(
    conn,
    cursor,
    valid_path: Path,
    valid_db_target_cols: List[str],
    db_columns: Dict[str, str],
    db_columns_lower: Dict[str, str],
    target_schema: str,
    target_table: str,
    load_type: str,
    batch_id: str,
    metadata: Dict[str, Any],
    total_inserted: int,
    promote_total: int,
    catalog_slug: Optional[str] = None,
    unique_indexes: Optional[List[List[str]]] = None,
) -> Tuple[int, int, int]:
    """Returns (rows_processed, inserted, updated)."""
    promoted_inserted = int(metadata.get("promoted_inserted") or 0)
    promoted_updated = int(metadata.get("promoted_updated") or 0)
    chunks_processed = total_inserted // PROMOTION_BATCH_SIZE if total_inserted else 0

    is_history = _is_history_promotion(metadata, target_schema, target_table, load_type)
    effective_load_type = "history" if is_history else load_type

    with open(valid_path, "r", encoding="utf-8") as f:
        header_line = f.readline().strip()
        file_columns = header_line.split("\t")
        data_cols = _parquet_promotion_columns(file_columns, valid_db_target_cols)
        if not data_cols:
            raise ValueError("No promotable columns found in TSV valid file.")

        insert_query, template_values, file_col_indices, _insert_cols, conflict_clause = (
            _prepare_insert_query(
                valid_db_target_cols,
                db_columns,
                data_cols,
                target_schema,
                target_table,
                effective_load_type,
                catalog_slug=catalog_slug,
                metadata=metadata,
                db_columns_lower=db_columns_lower,
                unique_indexes=unique_indexes,
            )
        )

        if total_inserted > 0:
            logger.info(f"Skipping first {total_inserted} previously promoted rows...")
            for _ in itertools.islice(f, total_inserted):
                pass

        chunk_data: List[tuple] = []
        for line in f:
            raw_vals = line.rstrip("\n").split("\t")
            chunk_data.append(_row_tuple_from_values(raw_vals, file_col_indices))

            if len(chunk_data) >= PROMOTION_BATCH_SIZE:
                _aff, ins, upd = _execute_promotion_batch(
                    cursor, insert_query, template_values, chunk_data, conflict_clause
                )
                total_inserted += len(chunk_data)
                promoted_inserted += ins
                promoted_updated += upd
                conn.commit()
                metadata = _merge_promotion_metadata(
                    metadata,
                    promoted_rows=total_inserted,
                    promoted_inserted=promoted_inserted,
                    promoted_updated=promoted_updated,
                )
                chunks_processed += 1
                _persist_promotion_chunk_metadata(
                    conn,
                    cursor,
                    batch_id,
                    metadata,
                    chunks_processed=chunks_processed,
                )
                report_promotion_progress(
                    conn,
                    batch_id,
                    promote_total=promote_total,
                    rows_processed=total_inserted,
                    chunks_processed=chunks_processed,
                )
                chunk_data = []

        if chunk_data:
            _aff, ins, upd = _execute_promotion_batch(
                cursor, insert_query, template_values, chunk_data, conflict_clause
            )
            total_inserted += len(chunk_data)
            promoted_inserted += ins
            promoted_updated += upd
            conn.commit()
            metadata = _merge_promotion_metadata(
                metadata,
                promoted_rows=total_inserted,
                promoted_inserted=promoted_inserted,
                promoted_updated=promoted_updated,
            )
            chunks_processed += 1
            _persist_promotion_chunk_metadata(
                conn,
                cursor,
                batch_id,
                metadata,
                chunks_processed=chunks_processed,
                force=True,
            )
            report_promotion_progress(
                conn,
                batch_id,
                promote_total=promote_total,
                rows_processed=total_inserted,
                chunks_processed=chunks_processed,
            )

    return total_inserted, promoted_inserted, promoted_updated


def _promote_from_parquet(
    conn,
    cursor,
    valid_path: Path,
    valid_db_target_cols: List[str],
    db_columns: Dict[str, str],
    db_columns_lower: Dict[str, str],
    target_schema: str,
    target_table: str,
    load_type: str,
    batch_id: str,
    metadata: Dict[str, Any],
    total_inserted: int,
    promote_total: int,
    catalog_slug: Optional[str] = None,
    unique_indexes: Optional[List[List[str]]] = None,
    db_udt_names: Optional[Dict[str, str]] = None,
    timer: Optional[PipelineTimer] = None,
) -> Tuple[int, int, int]:
    """Returns (rows_processed, inserted, updated)."""
    promoted_inserted = int(metadata.get("promoted_inserted") or 0)
    promoted_updated = int(metadata.get("promoted_updated") or 0)
    chunks_processed = total_inserted // PROMOTION_BATCH_SIZE if total_inserted else 0

    import pyarrow.parquet as pq

    pf = pq.ParquetFile(valid_path)
    total_frame_rows = pf.metadata.num_rows
    if promote_total <= 0:
        promote_total = total_frame_rows
    if total_inserted >= total_frame_rows:
        return total_inserted, promoted_inserted, promoted_updated

    skip = total_inserted
    is_history = _is_history_promotion(metadata, target_schema, target_table, load_type)
    effective_load_type = "history" if is_history else load_type
    insert_cols: List[str] = []
    staging_cols: List[str] = []
    conflict_clause = ""
    include_imported_at = False

    use_arrow_copy = not (load_type == "catalog" and catalog_slug)

    for batch in pf.iter_batches(batch_size=PROMOTION_BATCH_SIZE):
        with (timer.phase("parquet_read_ms") if timer else _noop_phase()):
            arrow_batch = batch
        batch_rows = arrow_batch.num_rows
        if skip >= batch_rows:
            skip -= batch_rows
            continue
        if skip > 0:
            arrow_batch = arrow_batch.slice(skip, batch_rows - skip)
            batch_rows = arrow_batch.num_rows
            skip = 0
        if batch_rows == 0:
            continue

        frame: Optional[pd.DataFrame] = None
        if load_type == "catalog" and catalog_slug:
            from data_staging.services.catalog.catalog_transforms import normalize_catalog_enum_columns

            frame = arrow_batch.to_pandas()
            frame = normalize_catalog_enum_columns(frame, catalog_slug)
            batch_columns = list(frame.columns)
            use_arrow_copy = False
        else:
            batch_columns = list(arrow_batch.schema.names)

        data_cols = _parquet_promotion_columns(batch_columns, valid_db_target_cols)
        if not data_cols:
            raise ValueError("No promotable columns found in Parquet file.")

        if not insert_cols:
            logger.info("Promotion columns from file: %s", ", ".join(data_cols))
            _insert_query, _template_values, _file_col_indices, insert_cols, conflict_clause = (
                _prepare_insert_query(
                    valid_db_target_cols,
                    db_columns,
                    data_cols,
                    target_schema,
                    target_table,
                    effective_load_type,
                    catalog_slug=catalog_slug,
                    metadata=metadata,
                    db_columns_lower=db_columns_lower,
                    unique_indexes=unique_indexes,
                )
            )
            staging_cols = [c.strip('"') for c in insert_cols if c.strip('"') != "imported_at"]
            include_imported_at = "imported_at" in db_columns

        with (timer.phase("upsert_ms") if timer else _noop_phase()):
            _aff, ins, upd = _execute_staging_promotion_batch(
                cursor,
                target_schema,
                target_table,
                insert_cols,
                staging_cols,
                conflict_clause,
                data_cols,
                include_imported_at=include_imported_at,
                db_columns=db_columns,
                db_udt_names=db_udt_names,
                frame=frame,
                arrow_batch=arrow_batch if use_arrow_copy else None,
            )
        chunk_len = batch_rows if use_arrow_copy else len(frame or [])
        total_inserted += chunk_len
        promoted_inserted += ins
        promoted_updated += upd
        conn.commit()
        metadata = _merge_promotion_metadata(
            metadata,
            promoted_rows=total_inserted,
            promoted_inserted=promoted_inserted,
            promoted_updated=promoted_updated,
        )
        chunks_processed += 1
        with (timer.phase("metadata_commit_ms") if timer else _noop_phase()):
            _persist_promotion_chunk_metadata(
                conn,
                cursor,
                batch_id,
                metadata,
                chunks_processed=chunks_processed,
            )
        report_promotion_progress(
            conn,
            batch_id,
            promote_total=promote_total,
            rows_processed=total_inserted,
            chunks_processed=chunks_processed,
        )

    return total_inserted, promoted_inserted, promoted_updated


class _noop_phase:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def promote_batch_job(payload: Dict[str, Any]):
    batch_id = payload.get("batch_id")
    target_schema = payload.get("target_schema")
    target_table = payload.get("target_table")

    if not batch_id or not target_schema or not target_table:
        raise ValueError("Missing required fields: batch_id, target_schema, target_table")

    database_url = str(settings.DATABASE_URL)
    conn = psycopg2.connect(
        database_url,
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
    )
    conn.autocommit = False
    valid_path: Optional[Path] = None
    promo_timer = PipelineTimer("promotion")

    try:
        cursor = conn.cursor()
        _apply_promotion_session_tuning(cursor)

        cursor.execute(
            "SELECT metadata, source_name, records_count FROM staging_meta.batch_control WHERE batch_id = %s",
            (batch_id,),
        )
        batch_row = cursor.fetchone()
        if not batch_row:
            raise ValueError(f"Batch {batch_id} not found")

        metadata = batch_row[0] or {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        source_name = batch_row[1]
        records_count = int(batch_row[2] or 0)
        final_stats = metadata.get("processing_stats", {}) or {}
        promote_total = int(final_stats.get("total_inserted") or records_count or 0)

        safe_source_name = source_name.lower().replace(" ", "_").replace("-", "_")
        staging_table = f"stage_{safe_source_name}"
        load_type = metadata.get("load_type", "history")
        catalog_slug = None
        if load_type == "catalog":
            catalog_slug = metadata.get("catalog_name") or metadata.get("target_table") or target_table
            production_table = metadata.get("production_table")
            if production_table:
                target_table = production_table
            elif catalog_slug:
                from data_staging.services.catalog.catalog_registry import resolve_catalog_db_target

                target_schema, target_table = resolve_catalog_db_target(catalog_slug, target_schema)
        elif load_type == "history" or metadata.get("history_config"):
            from data_staging.services.history.history_config import (
                HISTORY_TARGET_SCHEMA,
                HISTORY_TARGET_TABLE,
            )

            load_type = "history"
            target_schema = HISTORY_TARGET_SCHEMA
            target_table = HISTORY_TARGET_TABLE
        else:
            from data_staging.services.history.history_config import (
                HISTORY_TARGET_SCHEMA,
                HISTORY_TARGET_TABLE,
                is_sales_history_target,
            )

            if is_sales_history_target(target_schema, target_table):
                load_type = "history"
                target_schema = HISTORY_TARGET_SCHEMA
                target_table = HISTORY_TARGET_TABLE

        valid_path = find_valid_records_file(batch_id, metadata.get("valid_temp_file"))

        logger.info(f"Starting promotion for batch {batch_id} to {target_schema}.{target_table}")

        if not valid_path:
            logger.warning(
                f"No valid records file for batch {batch_id} (metadata path: {metadata.get('valid_temp_file')})"
            )
        elif not valid_path.is_file():
            logger.warning(f"Valid records file missing on disk: {valid_path}")

        valid_db_target_cols, db_columns, db_columns_lower, db_udt_names, unique_indexes = (
            _build_insert_context(cursor, metadata, target_schema, target_table)
        )

        total_inserted = int(metadata.get("promoted_rows") or 0)
        promoted_inserted = int(metadata.get("promoted_inserted") or 0)
        promoted_updated = int(metadata.get("promoted_updated") or 0)

        if valid_path and valid_path.is_file() and is_parquet_valid_file(valid_path):
            import pyarrow.parquet as pq

            promote_total = max(promote_total, pq.ParquetFile(valid_path).metadata.num_rows)

        report_promotion_progress(
            conn,
            batch_id,
            promote_total=max(promote_total, total_inserted, 1),
            rows_processed=total_inserted,
            chunks_processed=total_inserted // PROMOTION_BATCH_SIZE if total_inserted else 0,
            force=True,
        )

        if valid_path and valid_path.is_file():
            logger.info(f"Promoting from {valid_path} (format: {valid_path.suffix})")
            logger.info(f"Resuming from row: {total_inserted}")

            try:
                upsert_catalog = catalog_slug if load_type == "catalog" else None
                if is_parquet_valid_file(valid_path):
                    total_inserted, promoted_inserted, promoted_updated = _promote_from_parquet(
                        conn,
                        cursor,
                        valid_path,
                        valid_db_target_cols,
                        db_columns,
                        db_columns_lower,
                        target_schema,
                        target_table,
                        load_type,
                        batch_id,
                        metadata,
                        total_inserted,
                        promote_total,
                        catalog_slug=upsert_catalog,
                        unique_indexes=unique_indexes,
                        db_udt_names=db_udt_names,
                        timer=promo_timer,
                    )
                else:
                    total_inserted, promoted_inserted, promoted_updated = _promote_from_tsv(
                        conn,
                        cursor,
                        valid_path,
                        valid_db_target_cols,
                        db_columns,
                        db_columns_lower,
                        target_schema,
                        target_table,
                        load_type,
                        batch_id,
                        metadata,
                        total_inserted,
                        promote_total,
                        catalog_slug=upsert_catalog,
                        unique_indexes=unique_indexes,
                    )
                logger.info(
                    "Promoted batch %s: %s rows (%s inserted, %s updated)",
                    batch_id,
                    total_inserted,
                    promoted_inserted,
                    promoted_updated,
                )
            except (psycopg2.OperationalError, psycopg2.DatabaseError, psycopg2.InterfaceError) as db_err:
                conn.rollback()
                error_msg = f"Truncado en registro {total_inserted}. Error: {str(db_err)}"
                logger.error(f"Batch crashed mid-flight. {error_msg}")
                try:
                    rescue_conn = psycopg2.connect(database_url)
                    rescue_cursor = rescue_conn.cursor()
                    rescue_cursor.execute(
                        """
                        UPDATE staging_meta.batch_control
                        SET status = 'PARTIALLY_PROMOTED',
                            error_message = %s,
                            completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE batch_id = %s
                        """,
                        (error_msg, batch_id),
                    )
                    rescue_conn.commit()
                    rescue_conn.close()
                except Exception as rescue_err:
                    logger.error(f"Failed to save PARTIALLY_PROMOTED state for {batch_id}: {rescue_err}")
                raise Exception(error_msg) from db_err
        else:
            raise ValueError(
                f"Archivo de registros válidos no encontrado para el batch {batch_id}. "
                f"Ruta esperada: {metadata.get('valid_temp_file')}. "
                "Vuelve a procesar el batch antes de promover."
            )

        if total_inserted == 0:
            cursor.execute(
                f"""
                UPDATE staging_meta.batch_control
                SET status = 'PROMOTED',
                    metadata = {metadata_merge_expr("%s::jsonb")},
                    error_message = 'No records to promote: all records were rejected or duplicated',
                    completed_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE batch_id = %s
                """,
                (json.dumps({"promoted_at": "NOW()", "promoted_count": 0}), batch_id),
            )
            conn.commit()
            return

        promotion_payload = _merge_promotion_metadata(
            {},
            promoted_rows=total_inserted,
            promoted_inserted=promoted_inserted,
            promoted_updated=promoted_updated,
        )
        promotion_payload["promoted_at"] = "NOW()"
        promotion_payload.update(promo_timer.snapshot())

        cursor.execute(
            f"""
            UPDATE staging_meta.batch_control
            SET status = 'PROMOTED',
                metadata = {metadata_merge_expr("%s::jsonb")},
                error_message = NULL,
                completed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE batch_id = %s
            """,
            (json.dumps(promotion_payload), batch_id),
        )
        conn.commit()
        persist_timing_metadata(conn, batch_id, promo_timer.snapshot())

        try:
            os.remove(valid_path)
            logger.info(f"Deleted temp valid file: {valid_path}")
        except OSError as e:
            logger.warning(f"Failed to delete temp file {valid_path}: {e}")

    except Exception as e:
        conn.rollback()
        logger.error(f"Promotion failed for batch {batch_id}: {e}")
        try:
            err_conn = psycopg2.connect(database_url)
            err_cursor = err_conn.cursor()
            err_cursor.execute("SELECT status FROM staging_meta.batch_control WHERE batch_id = %s", (batch_id,))
            current_st = err_cursor.fetchone()
            if current_st and current_st[0] != "PARTIALLY_PROMOTED":
                err_cursor.execute(
                    """
                    UPDATE staging_meta.batch_control
                    SET error_message = %s,
                        status = 'FAILED',
                        completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE batch_id = %s
                    """,
                    (f"Promotion Error: {str(e)}", batch_id),
                )
                err_conn.commit()
            err_conn.close()
        except Exception:
            pass
        raise
    finally:
        conn.close()

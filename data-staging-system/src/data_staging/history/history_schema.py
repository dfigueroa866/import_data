"""Introspección de esquema para carga de historia (skus / sales_history)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

_SKUS_PK_CANDIDATES = ("id", "sku_id")
_SKUS_CODE_CANDIDATES = ("code", "sku_code", "sku")


def table_columns(cursor, schema: str, table: str) -> Set[str]:
    cursor.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        """,
        (schema, table),
    )
    return {row[0] for row in cursor.fetchall()}


def detect_skus_pk_column(cursor, schema: str = "public", table: str = "skus") -> Optional[str]:
    """PK real de public.skus (id, sku_id, etc.)."""
    cursor.execute(
        """
        SELECT a.attname
        FROM pg_index i
        JOIN pg_class c ON c.oid = i.indrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
        WHERE i.indisprimary
          AND n.nspname = %s
          AND c.relname = %s
        ORDER BY a.attnum
        LIMIT 1
        """,
        (schema, table),
    )
    row = cursor.fetchone()
    if row and row[0]:
        return str(row[0])

    cols = table_columns(cursor, schema, table)
    for candidate in _SKUS_PK_CANDIDATES:
        if candidate in cols:
            return candidate
    return None


def detect_skus_code_column(cursor, schema: str = "public", table: str = "skus") -> str:
    cols = table_columns(cursor, schema, table)
    for candidate in _SKUS_CODE_CANDIDATES:
        if candidate in cols:
            return candidate
    return "code"


def _mapping_target_names(column_mapping: Optional[Dict]) -> Set[str]:
    """Nombres destino desde wizard {file_col: {target}} o worker {target: {source}}."""
    targets: Set[str] = set()
    if not column_mapping:
        return targets
    for key, cfg in column_mapping.items():
        if isinstance(cfg, dict):
            if cfg.get("target"):
                targets.add(str(cfg["target"]))
            elif cfg.get("source") is not None or cfg.get("default") is not None:
                targets.add(str(key))
        else:
            targets.add(str(key))
    return targets


def history_preferred_unique_keys(
    metadata: Dict[str, Any],
    table_columns: Set[str],
) -> List[str]:
    """Claves preferidas para ON CONFLICT (filtradas a columnas presentes en la tabla)."""
    from data_staging.history.history_config import HISTORY_UNIQUE_KEYS

    keys = list(metadata.get("unique_keys") or HISTORY_UNIQUE_KEYS)
    col_lower = {c.lower(): c for c in table_columns}
    resolved: List[str] = []
    for key in keys:
        if key in table_columns:
            resolved.append(key)
        elif key.lower() in col_lower:
            resolved.append(col_lower[key.lower()])
    return resolved


def sales_history_needs_sku_id_resolution(
    target_column_types: Optional[Dict[str, str]],
    column_mapping: Optional[Dict] = None,
) -> bool:
    """Deprecated: sales_history ya no usa columna sku_id."""
    return False


def discover_unique_indexes(cursor, schema: str, table: str) -> List[List[str]]:
    """Índices únicos y PK de la tabla (columnas en orden)."""
    cursor.execute(
        """
        SELECT i.indisprimary,
               array_agg(a.attname ORDER BY k.ord) AS cols
        FROM pg_class t
        JOIN pg_namespace n ON n.oid = t.relnamespace
        JOIN pg_index i ON i.indrelid = t.oid
        JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS k(attnum, ord) ON TRUE
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum
        WHERE n.nspname = %s
          AND t.relname = %s
          AND i.indisunique
        GROUP BY i.indexrelid, i.indisprimary
        ORDER BY i.indisprimary DESC, cardinality(array_agg(a.attname))
        """,
        (schema, table),
    )
    indexes: List[List[str]] = []
    for row in cursor.fetchall():
        cols = list(row[1] or [])
        if cols:
            indexes.append(cols)
    return indexes


def pick_upsert_conflict_columns(
    preferred_keys: List[str],
    insert_columns: Set[str],
    unique_indexes: List[List[str]],
    resolve_name,
) -> List[str]:
    """
    Elige columnas ON CONFLICT que existan como índice único en BD y estén en el INSERT.
    resolve_name(key) -> nombre físico de columna o None.
    """
    insert_lower = {c.lower(): c for c in insert_columns}
    resolved_preferred = []
    for key in preferred_keys:
        col = resolve_name(key)
        if col and col.lower() in insert_lower:
            resolved_preferred.append(insert_lower[col.lower()])

    best_cols: Optional[List[str]] = None
    best_score = -1

    for index_cols in unique_indexes:
        if not all(c.lower() in insert_lower for c in index_cols):
            continue
        physical = [insert_lower[c.lower()] for c in index_cols]
        pref_lower = {c.lower() for c in resolved_preferred}
        overlap = sum(1 for c in physical if c.lower() in pref_lower)
        score = overlap * 100 + len(physical)
        if score > best_score:
            best_score = score
            best_cols = physical

    if best_cols:
        return best_cols

    for index_cols in unique_indexes:
        if len(index_cols) == 1 and index_cols[0].lower() == "id":
            if index_cols[0].lower() in insert_lower:
                return [insert_lower[index_cols[0].lower()]]

    return []


def create_sku_resolver(
    cursor,
    organization_id: str,
    target_column_types: Optional[Dict[str, str]] = None,
    column_mapping: Optional[Dict] = None,
):
    """
    Resolver código → UUID solo si el mapeo apunta a sku_id / sku_code.
    Retorna None si solo se usa columna sku (texto).
    """
    if not sales_history_needs_sku_id_resolution(target_column_types, column_mapping):
        return None

    pk_col = detect_skus_pk_column(cursor)
    if not pk_col:
        return None

    from data_staging.history.history_transforms import SkuCodeResolver

    code_col = detect_skus_code_column(cursor)
    return SkuCodeResolver(
        cursor,
        organization_id,
        pk_column=pk_col,
        code_column=code_col,
    )

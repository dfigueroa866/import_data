"""Apply catalog defaults and transformation rules (preview + worker)."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import polars as pl
from sqlalchemy import text
from sqlalchemy.orm import Session

from data_staging.services.catalog.catalog_registry import get_catalog_table, load_full_config

_EMPTY_TOKENS = {"", "nan", "none", "null", "n/a", "na"}
AUDIT_COLUMNS = frozenset({"created_at", "updated_at", "imported_at"})
# Columns with DB default that remain user-mappable and enum-validated when present in the file.
MAPPABLE_DEFAULT_COLUMNS = frozenset({"status"})
# File headers that must never appear in the mapping UI (audit + PK name collisions).
IGNORED_FILE_HEADERS = frozenset({
    "created_at",
    "updated_at",
    "imported_at",
    "sku_id",
    "location_id",
    "organization_id",
})

_CATALOG_IGNORED_FILE_BY_TABLE: Dict[str, frozenset[str]] = {
    "skus": frozenset({"sku_id", "organization_id"}),
    "location": frozenset({"location_id", "organization_id"}),
}

_DB_DEFAULT_COLUMNS_SQL = """
    SELECT column_name
    FROM information_schema.columns
    WHERE table_schema = :schema
      AND table_name = :table
      AND column_default IS NOT NULL
"""

_DB_DEFAULT_COLUMNS_SQL_PSYCOPG2 = """
    SELECT column_name
    FROM information_schema.columns
    WHERE table_schema = %s
      AND table_name = %s
      AND column_default IS NOT NULL
"""

_PK_COLUMNS_SQL = """
    SELECT kcu.column_name
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON tc.constraint_name = kcu.constraint_name
     AND tc.table_schema = kcu.table_schema
     AND tc.table_name = kcu.table_name
    WHERE tc.constraint_type = 'PRIMARY KEY'
      AND tc.table_schema = :schema
      AND tc.table_name = :table
"""

_PK_COLUMNS_SQL_PSYCOPG2 = """
    SELECT kcu.column_name
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON tc.constraint_name = kcu.constraint_name
     AND tc.table_schema = kcu.table_schema
     AND tc.table_name = kcu.table_name
    WHERE tc.constraint_type = 'PRIMARY KEY'
      AND tc.table_schema = %s
      AND tc.table_name = %s
"""


def is_empty_value(value: Any) -> bool:
    """True for None, NaN, blank strings, and literal tokens like 'none' / 'null'."""
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    if isinstance(value, float) and np.isnan(value):
        return True
    return str(value).strip().lower() in _EMPTY_TOKENS


# Backward-compatible alias used inside this module
_is_empty_scalar = is_empty_value


def coalesce_empty_to_none(value: Any) -> Any:
    """Normalize empty/null sentinels to Python None (never the string 'None')."""
    if is_empty_value(value):
        return None
    return value


_FRACTIONAL_SECONDS_SUFFIX = re.compile(r"\.\d+$")

_DATE_PARSE_FORMATS = (
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%Y/%m/%d",
    "%d-%m-%Y",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%d/%m/%Y %H:%M:%S",
)


def _clean_date_text(value: Any) -> str:
    text = str(value).strip()
    if not text:
        return ""
    if "T" in text and " " not in text[:11]:
        text = text.replace("T", " ", 1)
    text = _FRACTIONAL_SECONDS_SUFFIX.sub("", text)
    return text.strip()


def parse_flexible_datetime(value: Any) -> Optional[datetime]:
    """Parsea fechas ISO, datetime con fracciones (.000000000) y formatos comunes."""
    if is_empty_value(value):
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    text = _clean_date_text(value)
    if not text:
        return None
    for fmt in _DATE_PARSE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        from dateutil import parser as date_parser

        parsed = date_parser.parse(text)
        return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
    except Exception:
        return None


def format_date_for_storage(value: Any, *, date_only: bool = True) -> Optional[str]:
    """Normaliza a YYYY-MM-DD (columnas date) o datetime sin fracciones."""
    parsed = parse_flexible_datetime(value)
    if not parsed:
        return None
    if date_only:
        return parsed.date().isoformat()
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def sanitize_row_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    return {k: coalesce_empty_to_none(v) for k, v in row.items()}


def sanitize_empty_values_in_dataframe(
    df: pd.DataFrame,
    columns: Optional[List[str]] = None,
) -> pd.DataFrame:
    cols = columns or list(df.columns)
    out = df.copy()
    for col in cols:
        if col not in out.columns:
            continue
        out[col] = out[col].apply(coalesce_empty_to_none)
    return out


def _normalize_empty_to_na(df: pd.DataFrame, columns: Optional[List[str]] = None) -> pd.DataFrame:
    cols = columns or list(df.columns)
    out = df.copy()
    for col in cols:
        if col not in out.columns:
            continue
        out[col] = out[col].apply(lambda v: np.nan if _is_empty_scalar(v) else v)
    return out


def get_active_mapped_targets(
    column_mappings: Dict[str, Dict[str, Any]],
    column_toggles: Dict[str, bool],
) -> frozenset[str]:
    """Target column names the user explicitly enabled in the mapping step."""
    targets: set[str] = set()
    for file_col, config in (column_mappings or {}).items():
        if not column_toggles.get(file_col, True):
            continue
        target = config.get("target")
        if target:
            targets.add(str(target))
    return frozenset(targets)


def _column_in_scope(col: str, out: pd.DataFrame, mapped_columns: Optional[frozenset[str]]) -> bool:
    if col not in out.columns:
        return False
    if mapped_columns is not None and col not in mapped_columns:
        return False
    return True


def _normalize_enum_columns_in_frame(
    out: pd.DataFrame,
    catalog: Dict[str, Any],
    mapped_columns: Optional[frozenset[str]] = None,
) -> pd.DataFrame:
    """
    Map enum column values to canonical lowercase labels (e.g. Active -> active)
    so PostgreSQL enum types (sku_status) accept them on INSERT.
    """
    enums = catalog.get("enums") or {}
    if not enums:
        return out

    for col, allowed in enums.items():
        if not _column_in_scope(col, out, mapped_columns) or not allowed:
            continue
        canonical = {str(v).strip().lower(): str(v).strip().lower() for v in allowed}

        def _norm_cell(value: Any, _canon: Dict[str, str] = canonical) -> Any:
            if is_empty_value(value):
                return np.nan
            key = str(value).strip().lower()
            return _canon.get(key, value)

        out[col] = out[col].apply(_norm_cell)
    return out


def normalize_catalog_enum_columns(
    pdf: pd.DataFrame,
    table_name: str,
    mapped_columns: Optional[frozenset[str]] = None,
) -> pd.DataFrame:
    """Public helper for promotion worker (Parquet may predate enum normalization)."""
    catalog = get_catalog_table(table_name)
    if not catalog or pdf.empty:
        return pdf
    return _normalize_enum_columns_in_frame(pdf.copy(), catalog, mapped_columns)


def apply_catalog_transforms(
    pdf: pd.DataFrame,
    table_name: str,
    mapped_columns: Optional[frozenset[str]] = None,
) -> pd.DataFrame:
    """Apply registry defaults and config transformation_rules to mapped catalog data."""
    catalog = get_catalog_table(table_name)
    if not catalog:
        return pdf

    config = load_full_config(table_name)
    out = pdf.copy()

    defaults = catalog.get("defaults") or {}
    for col, default_val in defaults.items():
        if not _column_in_scope(col, out, mapped_columns):
            continue
        mask = out[col].apply(_is_empty_scalar)
        if mask.any():
            out.loc[mask, col] = default_val

    for rule in config.get("transformation_rules") or []:
        name = rule.get("name")
        if name == "clean_whitespace":
            for col in rule.get("columns") or []:
                if _column_in_scope(col, out, mapped_columns):
                    out[col] = out[col].apply(
                        lambda v: np.nan if is_empty_value(v) else str(v).strip()
                    )
        elif name == "handle_nulls" and rule.get("strategy") == "fill":
            fill_values = rule.get("fill_values") or {}
            applicable = [
                c for c in fill_values.keys() if _column_in_scope(c, out, mapped_columns)
            ]
            out = _normalize_empty_to_na(out, applicable)
            for col in applicable:
                out[col] = out[col].fillna(fill_values[col])

    out = _normalize_enum_columns_in_frame(out, catalog, mapped_columns)
    scope_cols = (
        [c for c in out.columns if c in mapped_columns]
        if mapped_columns is not None
        else list(out.columns)
    )
    return sanitize_empty_values_in_dataframe(out, scope_cols)


def apply_catalog_transforms_polars(
    df: pl.DataFrame,
    table_name: str,
    mapped_columns: Optional[frozenset[str]] = None,
) -> pl.DataFrame:
    if df.is_empty():
        return df
    pdf = df.to_pandas()
    pdf = apply_catalog_transforms(pdf, table_name, mapped_columns=mapped_columns)
    return pl.from_pandas(pdf)


def load_db_primary_key_columns(
    db_session: Optional[Session],
    schema: str,
    table: str,
) -> List[str]:
    if not db_session or not schema or not table:
        return []
    try:
        rows = db_session.execute(
            text(_PK_COLUMNS_SQL),
            {"schema": schema, "table": table},
        ).fetchall()
        return [str(r[0]) for r in rows]
    except Exception:
        return []


def load_primary_key_columns_psycopg2(cursor, schema: str, table: str) -> List[str]:
    if not cursor or not schema or not table:
        return []
    try:
        cursor.execute(_PK_COLUMNS_SQL_PSYCOPG2, (schema, table))
        return [str(r[0]) for r in cursor.fetchall()]
    except Exception:
        return []


def load_db_default_columns(
    db_session: Optional[Session],
    schema: str,
    table: str,
) -> List[str]:
    """Columns with a database default (uuid, timestamps, status, etc.)."""
    if not db_session or not schema or not table:
        return []
    try:
        rows = db_session.execute(
            text(_DB_DEFAULT_COLUMNS_SQL),
            {"schema": schema, "table": table},
        ).fetchall()
        return [str(r[0]) for r in rows]
    except Exception:
        return []


def load_db_default_columns_psycopg2(cursor, schema: str, table: str) -> List[str]:
    if not cursor or not schema or not table:
        return []
    try:
        cursor.execute(_DB_DEFAULT_COLUMNS_SQL_PSYCOPG2, (schema, table))
        return [str(r[0]) for r in cursor.fetchall()]
    except Exception:
        return []


def load_db_system_managed_columns(
    db_session: Optional[Session],
    schema: str,
    table: str,
) -> frozenset[str]:
    """PK and audit columns — never mappable or promotable from user mapping."""
    managed: set[str] = set(AUDIT_COLUMNS)
    managed.update(load_db_primary_key_columns(db_session, schema, table))
    return frozenset(managed)


def load_db_system_managed_columns_psycopg2(cursor, schema: str, table: str) -> frozenset[str]:
    managed: set[str] = set(AUDIT_COLUMNS)
    managed.update(load_primary_key_columns_psycopg2(cursor, schema, table))
    return frozenset(managed)


def load_db_validation_excluded_columns(
    db_session: Optional[Session],
    schema: str,
    table: str,
) -> frozenset[str]:
    """PK, audit, and DB-default columns — skip NOT NULL validation (except mappable defaults like status)."""
    skip: set[str] = set(load_db_system_managed_columns(db_session, schema, table))
    skip.update(
        c for c in load_db_default_columns(db_session, schema, table)
        if c not in MAPPABLE_DEFAULT_COLUMNS
    )
    return frozenset(skip)


def load_db_validation_excluded_columns_psycopg2(cursor, schema: str, table: str) -> frozenset[str]:
    skip: set[str] = set(load_db_system_managed_columns_psycopg2(cursor, schema, table))
    skip.update(
        c for c in load_db_default_columns_psycopg2(cursor, schema, table)
        if c not in MAPPABLE_DEFAULT_COLUMNS
    )
    return frozenset(skip)


def filter_catalog_validation_rules(
    rules: Dict[str, Any],
    system_managed: frozenset[str],
) -> Dict[str, Any]:
    """Remove system-managed / PK columns from catalog JSON validation rules."""
    if not rules or not system_managed:
        return rules

    out = dict(rules)
    not_null = dict(out.get("not_null") or {})
    cols = not_null.get("columns")
    if cols:
        not_null["columns"] = [c for c in cols if c not in system_managed]
        out["not_null"] = not_null

    unique = dict(out.get("unique") or {})
    ucols = unique.get("columns")
    if ucols:
        unique["columns"] = [c for c in ucols if c not in system_managed]
        out["unique"] = unique

    lookup = dict(out.get("lookup_validation") or {})
    lookups = lookup.get("lookups")
    if isinstance(lookups, dict):
        lookup["lookups"] = {
            k: v
            for k, v in lookups.items()
            if k not in system_managed or k in MAPPABLE_DEFAULT_COLUMNS
        }
        out["lookup_validation"] = lookup

    return out


def validate_catalog_row_enums(row: Dict[str, Any], table_name: str) -> List[str]:
    """Return error messages for enum violations on mapped catalog columns."""
    catalog = get_catalog_table(table_name)
    if not catalog:
        return []
    enums = catalog.get("enums") or {}
    errors: List[str] = []
    for col, allowed in enums.items():
        if col not in row:
            continue
        value = row[col]
        if _is_empty_scalar(value):
            continue
        allowed_lower = {str(v).lower() for v in allowed}
        if str(value).strip().lower() not in allowed_lower:
            errors.append(
                f"Invalid value for '{col}': '{value}'. "
                f"Allowed: {', '.join(str(v) for v in allowed)}"
            )
    return errors


def check_catalog_enum_issues(pdf: pd.DataFrame, table_name: str) -> List[Dict[str, Any]]:
    """Dataframe-level enum validation for preview (status, etc.)."""
    catalog = get_catalog_table(table_name)
    if not catalog or pdf.empty:
        return []
    enums = catalog.get("enums") or {}
    issues: List[Dict[str, Any]] = []
    for col, allowed in enums.items():
        if col not in pdf.columns:
            continue
        allowed_lower = {str(v).lower() for v in allowed}
        invalid_mask = pdf[col].apply(
            lambda v: not _is_empty_scalar(v) and str(v).strip().lower() not in allowed_lower
        )
        count = int(invalid_mask.sum())
        if count > 0:
            sample = pdf.loc[invalid_mask, col].iloc[0]
            issues.append({
                "rule": "lookup_validation",
                "severity": "error",
                "message": (
                    f"Valor inválido en '{col}': '{sample}'. "
                    f"Permitidos: {', '.join(str(v) for v in allowed)}"
                ),
                "column": col,
                "count": count,
            })
    return issues


def is_ignored_file_header(file_col: str, catalog_table: Optional[str] = None) -> bool:
    lower = file_col.lower()
    normalized = "".join(ch for ch in lower if ch.isalnum())

    if catalog_table:
        from data_staging.services.catalog.catalog_registry import get_catalog_table

        catalog = get_catalog_table(catalog_table)
        if catalog:
            for ignored in catalog.get("ignored_file_headers") or []:
                ignored_norm = "".join(ch for ch in ignored.lower() if ch.isalnum())
                if lower == ignored.lower() or normalized == ignored_norm:
                    return True

    if lower in IGNORED_FILE_HEADERS or normalized in {
        "createdat",
        "updatedat",
        "importedat",
        "skuid",
        "locationid",
        "organizationid",
    }:
        return True
    table = (catalog_table or "").lower()
    for ignored in _CATALOG_IGNORED_FILE_BY_TABLE.get(table, frozenset()):
        ignored_norm = "".join(ch for ch in ignored.lower() if ch.isalnum())
        if lower == ignored.lower() or normalized == ignored_norm:
            return True
    if table == "skus" and normalized == "skuid":
        return True
    if table == "location" and normalized == "locationid":
        return True
    return False


def load_db_not_null_columns(
    db_session: Optional[Session],
    schema: str,
    table: str,
    *,
    exclude_primary_keys: bool = True,
) -> List[str]:
    """NOT NULL columns from DB, excluding PK, audit, and DB-default columns."""
    if not db_session or not schema or not table:
        return []
    try:
        rows = db_session.execute(
            text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = :schema
                  AND table_name = :table
                  AND is_nullable = 'NO'
            """),
            {"schema": schema, "table": table},
        ).fetchall()
        skip = load_db_validation_excluded_columns(db_session, schema, table)
        if not exclude_primary_keys:
            pk = set(load_db_primary_key_columns(db_session, schema, table))
            skip = frozenset(c for c in skip if c not in pk)
        return [str(r[0]) for r in rows if str(r[0]) not in skip]
    except Exception:
        return []


def check_not_null_row_issues(
    pdf: pd.DataFrame,
    not_null_columns: List[str],
) -> List[Dict[str, Any]]:
    """Return validation issues for rows that still violate NOT NULL after transforms."""
    issues: List[Dict[str, Any]] = []
    for col in not_null_columns:
        if col not in pdf.columns:
            issues.append({
                "rule": "not_null",
                "severity": "critical",
                "message": f"Columna obligatoria en destino no presente: {col}",
                "column": col,
                "count": len(pdf),
            })
            continue

        empty_mask = pdf[col].apply(_is_empty_scalar)
        count = int(empty_mask.sum())
        if count > 0:
            issues.append({
                "rule": "not_null",
                "severity": "critical",
                "message": f"Valor vacío no permitido en '{col}' ({count} filas)",
                "column": col,
                "count": count,
            })
    return issues

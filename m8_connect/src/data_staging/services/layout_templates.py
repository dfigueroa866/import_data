"""Generate CSV upload layouts from live database table schemas."""

from __future__ import annotations

import csv
import io
import logging
import zipfile
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from data_staging.services.catalog.catalog_registry import list_catalog_tables
from data_staging.services.catalog.catalog_transforms import AUDIT_COLUMNS
from data_staging.services.history.history_config import (
    HISTORY_TARGET_SCHEMA,
    HISTORY_TARGET_TABLE,
)
from data_staging.utils.pg_schema import fetch_table_columns

logger = logging.getLogger(__name__)

# Surrogate / identity columns that users never provide in upload files.
_SURROGATE_COLUMNS = frozenset({"id", "sku_id", "location_id"})

_LAYOUT_SPECS: Tuple[Dict[str, str], ...] = (
    {"group": "catalogos", "filename": "skus.csv", "catalog_name": "skus"},
    {"group": "catalogos", "filename": "locations.csv", "catalog_name": "location"},
    {
        "group": "historia",
        "filename": "sales_history.csv",
        "schema": HISTORY_TARGET_SCHEMA,
        "table": HISTORY_TARGET_TABLE,
    },
)


def _quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _example_from_type(col: Dict[str, Any]) -> str:
    dtype = str(col.get("type") or "").lower()
    name = str(col.get("name") or "").lower()

    if name in {"status"}:
        return "active"
    if name in {"loc_type", "location_type"}:
        return "warehouse"
    if name in {"granularity"}:
        return "weekly"
    if name in {"source"}:
        return "csv"
    if name in {"sales_channel"}:
        return "SELL_IN"
    if name in {"period_start"}:
        return date.today().isoformat()
    if name in {"quantity", "pieces"}:
        return "1"
    if name in {"sku", "code", "location_code"}:
        return "EJEMPLO-001"
    if "name" in name:
        return "Ejemplo"

    if dtype in {"integer", "bigint", "smallint"}:
        return "1"
    if dtype in {"numeric", "decimal", "double precision", "real"}:
        return "1.0"
    if dtype == "boolean":
        return "true"
    if dtype == "date":
        return date.today().isoformat()
    if "timestamp" in dtype:
        return datetime.now().replace(microsecond=0).isoformat(sep=" ")
    if dtype == "uuid":
        return ""
    if dtype in {"json", "jsonb"}:
        return "{}"
    return "ejemplo"


def _stringify_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (datetime, date)):
        return value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (dict, list)):
        import json

        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _is_layout_excluded(col: Dict[str, Any]) -> bool:
    name = str(col.get("name") or "")
    if name in AUDIT_COLUMNS or name in _SURROGATE_COLUMNS:
        return True
    # UUID PKs with DB default (e.g. uuid_generate_v4) are system-managed.
    default = str(col.get("default") or "").lower()
    if col.get("is_primary_key") and "uuid" in default:
        return True
    return False


def _layout_columns(db: Session, schema: str, table: str) -> List[Dict[str, Any]]:
    columns = fetch_table_columns(db, schema, table)
    if not columns:
        return []
    return [col for col in columns if not _is_layout_excluded(col)]


def _sample_row_values(
    db: Session,
    schema: str,
    table: str,
    column_names: Sequence[str],
) -> Optional[Dict[str, str]]:
    if not column_names:
        return None
    cols_sql = ", ".join(_quote_ident(c) for c in column_names)
    sql = text(
        f"SELECT {cols_sql} FROM {_quote_ident(schema)}.{_quote_ident(table)} LIMIT 1"
    )
    try:
        row = db.execute(sql).mappings().first()
    except Exception as exc:
        logger.warning("Could not sample row from %s.%s: %s", schema, table, exc)
        db.rollback()
        return None
    if not row:
        return None
    return {name: _stringify_cell(row.get(name)) for name in column_names}


def _build_csv(columns: List[Dict[str, Any]], example: Dict[str, str]) -> bytes:
    buffer = io.StringIO()
    names = [c["name"] for c in columns]
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(names)
    writer.writerow([example.get(name, "") for name in names])
    return buffer.getvalue().encode("utf-8-sig")


def _resolve_catalog_target(catalog_name: str) -> Tuple[str, str]:
    catalogs = {c["name"]: c for c in list_catalog_tables()}
    entry = catalogs.get(catalog_name)
    if not entry:
        raise ValueError(f"Catálogo '{catalog_name}' no encontrado o inactivo")
    schema = entry.get("target_schema") or "public"
    table = entry.get("target_table") or catalog_name
    return schema, table


def build_layout_zip(db: Session) -> bytes:
    """
    Build a ZIP with CSV layouts for catalogs (skus, locations) and history.

    Each CSV has a header row from the live DB columns (excluding system-managed
    surrogate/audit columns) plus one example row (sample from DB when available).
    """
    files: List[Tuple[str, bytes]] = []

    for spec in _LAYOUT_SPECS:
        if spec.get("catalog_name"):
            schema, table = _resolve_catalog_target(spec["catalog_name"])
        else:
            schema, table = spec["schema"], spec["table"]

        columns = _layout_columns(db, schema, table)
        if not columns:
            raise ValueError(f"Tabla {schema}.{table} no encontrada o sin columnas")

        names = [c["name"] for c in columns]
        sample = _sample_row_values(db, schema, table, names)
        example = sample or {c["name"]: _example_from_type(c) for c in columns}

        zip_path = f"{spec['group']}/{spec['filename']}"
        files.append((zip_path, _build_csv(columns, example)))

    out = io.BytesIO()
    with zipfile.ZipFile(out, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path, content in files:
            zf.writestr(path, content)
    return out.getvalue()

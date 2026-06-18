"""Organization-scoped SKU/location reference sets for history validation."""

from __future__ import annotations

import logging
from typing import Dict, Optional, Set, Tuple

from data_staging.services.history.history_schema import (
    detect_skus_code_column,
    table_columns,
)

logger = logging.getLogger(__name__)

_LOCATION_CANDIDATES: Tuple[Tuple[str, str, str], ...] = (
    ("public", "locations", "code"),
    ("public", "locations", "location_code"),
    ("public", "location", "location_code"),
    ("public", "location", "code"),
)


def _normalize_org_id(organization_id: Optional[str]) -> str:
    return str(organization_id or "").strip()


def _normalize_code(value) -> str:
    return str(value).strip().lower()


def _resolve_location_reference(cursor) -> Optional[Tuple[str, str, str]]:
    for schema, table, code_col in _LOCATION_CANDIDATES:
        cols = table_columns(cursor, schema, table)
        if "organization_id" in cols and code_col in cols:
            return schema, table, code_col
    return None


def load_org_scoped_fk_sets(cursor, organization_id: Optional[str]) -> Dict[str, Set[str]]:
    """
    Load SKU and location business codes for FK validation, scoped to one organization.

    Returns keys __valid_skus__, __valid_locations__ (and *_list companions).
    """
    org_id = _normalize_org_id(organization_id)
    result: Dict[str, Set[str]] = {
        "__valid_skus__": set(),
        "__valid_locations__": set(),
    }
    if not org_id:
        logger.warning("organization_id missing; SKU/location FK validation disabled")
        return result

    sku_code_col = detect_skus_code_column(cursor, "public", "skus")
    try:
        cursor.execute(
            f'SELECT DISTINCT LOWER(TRIM("{sku_code_col}"::text)) '
            f'FROM public.skus '
            f'WHERE organization_id::text = %s AND "{sku_code_col}" IS NOT NULL',
            (org_id,),
        )
        sku_codes = {_normalize_code(row[0]) for row in cursor.fetchall() if row and row[0]}
        result["__valid_skus__"] = sku_codes
        logger.info("Loaded %s SKU codes for organization %s", len(sku_codes), org_id)
    except Exception as exc:
        logger.error("Failed to load valid SKUs for org %s: %s", org_id, exc)

    location_ref = _resolve_location_reference(cursor)
    if not location_ref:
        logger.warning("No location reference table found for FK validation")
    else:
        schema, table, code_col = location_ref
        try:
            cursor.execute(
                f'SELECT DISTINCT LOWER(TRIM("{code_col}"::text)) '
                f'FROM "{schema}"."{table}" '
                f'WHERE organization_id::text = %s AND "{code_col}" IS NOT NULL',
                (org_id,),
            )
            loc_codes = {_normalize_code(row[0]) for row in cursor.fetchall() if row and row[0]}
            result["__valid_locations__"] = loc_codes
            logger.info(
                "Loaded %s location codes from %s.%s for organization %s",
                len(loc_codes),
                schema,
                table,
                org_id,
            )
        except Exception as exc:
            logger.error(
                "Failed to load valid locations from %s.%s for org %s: %s",
                schema,
                table,
                org_id,
                exc,
            )

    result["__valid_skus_list__"] = list(result["__valid_skus__"])
    result["__valid_locations_list__"] = list(result["__valid_locations__"])
    if org_id:
        result["__fk_org_scoped__"] = True
    return result


def load_generic_fk_values(
    cursor,
    *,
    schema: str,
    table: str,
    column: str,
    organization_id: Optional[str] = None,
    normalize_lower: bool = False,
) -> Set[str]:
    """Load distinct FK reference values, scoped by organization when the table supports it."""
    cols = table_columns(cursor, schema, table)
    if column not in cols:
        return set()

    conditions = [f'"{column}" IS NOT NULL']
    params = []
    org_id = _normalize_org_id(organization_id)
    if org_id and "organization_id" in cols:
        conditions.append("organization_id::text = %s")
        params.append(org_id)

    where_clause = " AND ".join(conditions)
    cursor.execute(
        f'SELECT DISTINCT "{column}" FROM "{schema}"."{table}" WHERE {where_clause}',
        tuple(params),
    )
    values: Set[str] = set()
    for row in cursor.fetchall():
        if not row or row[0] is None:
            continue
        raw = str(row[0]).strip()
        values.add(_normalize_code(raw) if normalize_lower else raw)
    return values

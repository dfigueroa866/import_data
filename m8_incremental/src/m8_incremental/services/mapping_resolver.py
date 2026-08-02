"""Auto-resolve column mappings for incremental loads.

Mappings use the same wizard shape as m8_connect:
  {file_header: {"target": dest_col}, "__fixed_*": {"target": ..., "default_value": ...}}
so catalog/history preview and process pipelines work without changes to the pipelines.

File headers may match the target name or a catalog alias (e.g. CSV ``code`` → DB ``sku``).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

ORG_MAPPING_KEY = "__fixed_organization_id__"
GRANULARITY_MAPPING_KEY = "__fixed_granularity__"
SOURCE_MAPPING_KEY = "__fixed_source__"
SALES_CHANNEL_MAPPING_KEY = "__fixed_sales_channel__"


def _normalize_header(value: str) -> str:
    return re.sub(r"\s+", "_", str(value or "").strip().lower())


def _match_header_exact(file_headers: List[str], candidate: str) -> Optional[str]:
    want = _normalize_header(candidate)
    for header in file_headers:
        if _normalize_header(header) == want:
            return header
    return None


def _match_header_for_target(
    file_headers: List[str],
    target: str,
    column_aliases: Optional[Dict[str, Sequence[str]]] = None,
) -> Optional[str]:
    """Match a file header to a DB target via exact name or catalog aliases."""
    header = _match_header_exact(file_headers, target)
    if header:
        return header
    for alias in (column_aliases or {}).get(target) or []:
        header = _match_header_exact(file_headers, str(alias))
        if header:
            return header
    return None


def _process_type_from_granularity(granularity: str) -> str:
    g = (granularity or "weekly").lower()
    if g in ("monthly", "month"):
        return "Monthly"
    return "Weekly"


def _granularity_value(process_type: str) -> str:
    pt = (process_type or "Weekly").lower()
    if "month" in pt:
        return "monthly"
    return "weekly"


def _map_file_column(
    column_mappings: Dict[str, Any],
    column_toggles: Dict[str, Any],
    used_headers: set[str],
    file_headers: List[str],
    target: str,
    missing: List[str],
    *,
    column_aliases: Optional[Dict[str, Sequence[str]]] = None,
    required: bool = True,
) -> None:
    """Map a file header -> target using wizard key = real file column name."""
    available = [h for h in file_headers if h not in used_headers]
    header = _match_header_for_target(available, target, column_aliases)
    if header:
        column_mappings[header] = {"target": target}
        column_toggles[header] = {"selected": True}
        used_headers.add(header)
    elif required:
        missing.append(target)


def build_incremental_mappings(
    *,
    file_headers: List[str],
    load_type: str,
    organization_id: str,
    granularity: Optional[str] = None,
    catalog_targets: Optional[List[str]] = None,
    catalog_optional_targets: Optional[List[str]] = None,
    history_targets: Optional[List[str]] = None,
    column_aliases: Optional[Dict[str, Sequence[str]]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any], str, List[str]]:
    """
    Build column_mappings and column_toggles for incremental batch.

    File columns use wizard convention (dict key = CSV header, value.target = DB column).
    Fixed fields use ``__fixed_*`` keys expected by m8_connect.
    Headers may match the target or an alias (normalized).

    Returns (column_mappings, column_toggles, process_type, missing_targets).
    """
    process_type = _process_type_from_granularity(granularity or "weekly")
    missing: List[str] = []
    aliases = column_aliases or {}

    column_mappings: Dict[str, Any] = {
        ORG_MAPPING_KEY: {
            "target": "organization_id",
            "source": None,
            "default_value": organization_id,
        },
    }
    column_toggles: Dict[str, Any] = {
        ORG_MAPPING_KEY: {"selected": True},
    }

    if load_type == "history":
        org_header = _match_header_exact(file_headers, "organization_id")
        if org_header:
            column_mappings[ORG_MAPPING_KEY]["source"] = org_header
        else:
            missing.append("organization_id")

        gran_header = _match_header_exact(file_headers, "granularity")
        column_mappings[GRANULARITY_MAPPING_KEY] = {
            "target": "granularity",
            "source": gran_header,
            "default_value": _granularity_value(process_type),
        }
        column_toggles[GRANULARITY_MAPPING_KEY] = {"selected": True}
        if not gran_header:
            missing.append("granularity")

        column_mappings[SOURCE_MAPPING_KEY] = {
            "target": "source",
            "source": None,
            "default_value": "incremental",
        }
        column_toggles[SOURCE_MAPPING_KEY] = {"selected": True}
        column_mappings[SALES_CHANNEL_MAPPING_KEY] = {
            "target": "sales_channel",
            "source": None,
            "default_value": "SELL_IN",
        }
        column_toggles[SALES_CHANNEL_MAPPING_KEY] = {"selected": True}

        targets = history_targets or [
            "sku",
            "location_code",
            "period_start",
            "quantity",
            "pieces",
        ]
        used_headers: set[str] = set()
        if org_header:
            used_headers.add(org_header)
        if gran_header:
            used_headers.add(gran_header)

        for target in targets:
            _map_file_column(
                column_mappings,
                column_toggles,
                used_headers,
                file_headers,
                target,
                missing,
                column_aliases=aliases,
                required=True,
            )
    else:
        targets = catalog_targets or ["sku", "name"]
        used_headers = set()

        for target in targets:
            _map_file_column(
                column_mappings,
                column_toggles,
                used_headers,
                file_headers,
                target,
                missing,
                column_aliases=aliases,
                required=True,
            )

        for target in catalog_optional_targets or []:
            if target in targets:
                continue
            _map_file_column(
                column_mappings,
                column_toggles,
                used_headers,
                file_headers,
                target,
                missing,
                column_aliases=aliases,
                required=False,
            )

    return column_mappings, column_toggles, process_type, missing

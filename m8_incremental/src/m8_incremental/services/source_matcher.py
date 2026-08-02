"""Match incremental source files to catalog slugs (strict, no aliases)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from data_staging.services.history.history_catalog_prerequisites import normalize_catalog_slug

_SYSTEM_COLUMNS = frozenset(
    {"organization_id", "created_at", "updated_at", "imported_at", "sku_id", "location_id"}
)


def catalog_slug_for_filename(slug: str) -> str:
    """Canonical catalog slug used to match source file names."""
    return (normalize_catalog_slug(slug) or str(slug or "")).strip().lower()


def match_catalog_source_file(
    files: List[Path],
    slug: str,
    catalog_entry: Optional[Dict[str, Any]] = None,
) -> Optional[Path]:
    """
    Return a source file whose name contains the catalog slug (case-insensitive).
    No plural/singular aliases or fallback to unrelated files.
    """
    del catalog_entry  # kept for call-site compatibility
    key = catalog_slug_for_filename(slug)
    if not key or not files:
        return None

    matches = [path for path in files if key in path.stem.lower()]
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    return sorted(matches, key=lambda path: path.name.lower())[0]


def catalog_mapping_targets(catalog_entry: Dict[str, Any]) -> List[str]:
    """Columns that must exist in the source file (exact header names)."""
    targets: List[str] = []
    seen: Set[str] = set()

    for col in catalog_entry.get("required_mapping_columns") or []:
        if col not in seen:
            targets.append(col)
            seen.add(col)

    for col in catalog_entry.get("required_columns") or []:
        if col in seen or col in _SYSTEM_COLUMNS:
            continue
        if col.endswith("_id"):
            continue
        targets.append(col)
        seen.add(col)

    return targets or ["code", "name"]

"""History upload prerequisites: promoted catalog batches per organization."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from sqlalchemy import text
from sqlalchemy.orm import Session

REQUIRED_CATALOG_SLUGS: tuple[str, ...] = ("skus", "location")

_CATALOG_ALIASES: Dict[str, str] = {
    "skus": "skus",
    "sku": "skus",
    "products": "skus",
    "productos": "skus",
    "location": "location",
    "locations": "location",
    "ubicaciones": "location",
    "ubicacion": "location",
}

_CATALOG_LABELS: Dict[str, str] = {
    "skus": "Productos (SKUs)",
    "location": "Ubicaciones",
}


def normalize_catalog_slug(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    key = str(raw).strip().lower()
    if not key:
        return None
    return _CATALOG_ALIASES.get(key, key if key in REQUIRED_CATALOG_SLUGS else None)


def _load_promoted_catalog_slugs(db: Session, organization_id: str) -> Set[str]:
    org_id = str(organization_id or "").strip()
    if not org_id:
        return set()

    rows = db.execute(
        text("""
            SELECT DISTINCT LOWER(TRIM(COALESCE(
                metadata->>'catalog_name',
                metadata->>'target_table',
                metadata->>'production_table',
                source_name
            )))
            FROM staging_meta.batch_control
            WHERE status = 'PROMOTED'
              AND metadata->>'load_type' = 'catalog'
              AND COALESCE(organization_id::text, metadata->>'organization_id') = :org_id
        """),
        {"org_id": org_id},
    ).fetchall()

    promoted: Set[str] = set()
    for row in rows:
        slug = normalize_catalog_slug(row[0] if row else None)
        if slug:
            promoted.add(slug)
    return promoted


def _build_readiness_message(missing: List[str]) -> str:
    if not missing:
        return "Catálogos promovidos listos para cargar historia."
    labels = [_CATALOG_LABELS.get(slug, slug) for slug in missing]
    if len(labels) == 1:
        missing_text = labels[0]
    elif len(labels) == 2:
        missing_text = f"{labels[0]} y {labels[1]}"
    else:
        missing_text = ", ".join(labels[:-1]) + f" y {labels[-1]}"
    return (
        f"No puedes cargar historia todavía. Falta promover a producción: {missing_text}. "
        "Ve a Catálogos, completa la carga y pulsa «Cargar a producción» en cada uno."
    )


def check_history_catalog_readiness(
    db: Session,
    organization_id: Optional[str],
) -> Dict[str, Any]:
    """
    Return readiness based on PROMOTED catalog batches for the organization.

    Requires at least one PROMOTED batch for skus and one for location.
    """
    org_id = str(organization_id or "").strip()
    if not org_id:
        missing = list(REQUIRED_CATALOG_SLUGS)
        return {
            "ready": False,
            "missing": missing,
            "promoted_catalogs": [],
            "message": _build_readiness_message(missing),
        }

    promoted = _load_promoted_catalog_slugs(db, org_id)
    missing = [slug for slug in REQUIRED_CATALOG_SLUGS if slug not in promoted]
    return {
        "ready": len(missing) == 0,
        "missing": missing,
        "promoted_catalogs": sorted(promoted),
        "message": _build_readiness_message(missing),
    }

"""Hierarchical load storage paths per organization (slug) and load type."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Literal, Optional

from sqlalchemy.orm import Session
from sqlalchemy import text

from data_staging.config import settings
from data_staging.utils.batch_control import normalize_metadata

LoadType = Literal["history", "catalog"]

HISTORIA_DIR = "historia"
CATALOGOS_DIR = "catalogos"
LOAD_TIMESTAMP_FMT = "%Y-%m-%d_%H%M%S"


def fetch_organization_slug(db: Session, organization_id: str) -> str:
    """Return organization slug from public.organizations."""
    if not organization_id:
        raise ValueError("organization_id is required")
    row = db.execute(
        text("""
            SELECT slug
            FROM public.organizations
            WHERE id = :organization_id
            LIMIT 1
        """),
        {"organization_id": organization_id},
    ).fetchone()
    if not row or not row.slug:
        raise ValueError(f"Organization slug not found for id={organization_id}")
    return str(row.slug).strip()


def format_load_timestamp(ts: Optional[datetime] = None) -> str:
    """Folder name for a load: YYYY-MM-DD_HHMMSS."""
    when = ts or datetime.now()
    return when.strftime(LOAD_TIMESTAMP_FMT)


def build_load_storage_dir(
    org_slug: str,
    load_type: LoadType,
    *,
    catalog_name: Optional[str] = None,
    load_timestamp: Optional[datetime] = None,
    upload_root: Optional[Path] = None,
) -> Path:
    """
    Build path under UPLOAD_PATH:
      {slug}/historia/{timestamp}/
      {slug}/catalogos/{catalog}/{timestamp}/
    """
    root = (upload_root or Path(settings.UPLOAD_PATH)).resolve()
    slug = org_slug.strip()
    if not slug:
        raise ValueError("org_slug is required")

    normalized_type = (load_type or "history").lower()
    if normalized_type not in ("history", "catalog"):
        normalized_type = "history"

    ts_folder = format_load_timestamp(load_timestamp)

    if normalized_type == "catalog":
        if not catalog_name:
            raise ValueError("catalog_name is required for catalog loads")
        catalog_segment = catalog_name.strip().lower().replace(" ", "_")
        return root / slug / CATALOGOS_DIR / catalog_segment / ts_folder

    return root / slug / HISTORIA_DIR / ts_folder


def ensure_load_storage_dir(
    org_slug: str,
    load_type: LoadType,
    *,
    catalog_name: Optional[str] = None,
    load_timestamp: Optional[datetime] = None,
    upload_root: Optional[Path] = None,
) -> Path:
    """Create org/load-type/[catalog]/timestamp directories if missing."""
    path = build_load_storage_dir(
        org_slug,
        load_type,
        catalog_name=catalog_name,
        load_timestamp=load_timestamp,
        upload_root=upload_root,
    )
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def resolve_batch_work_dir(metadata: Any) -> Path:
    """
    Return batch work directory.
    New batches: metadata.load_storage_dir under UPLOAD_PATH.
    Legacy batches: flat TEMP_PATH.
    """
    meta = normalize_metadata(metadata)
    stored = meta.get("load_storage_dir")
    if stored:
        path = Path(str(stored))
        if path.is_dir():
            return path.resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path.resolve()

    from data_staging.utils.batch_staging_files import get_temp_dir

    return get_temp_dir()


def batch_artifact_path(
    batch_id: str,
    suffix: str,
    metadata: Any = None,
) -> Path:
    """Path for a batch artifact file inside the work directory."""
    work_dir = resolve_batch_work_dir(metadata)
    name = suffix if suffix.startswith(batch_id) else f"{batch_id}{suffix}"
    return work_dir / name


def load_storage_metadata_fields(
    storage_dir: Path,
    org_slug: str,
    load_timestamp: datetime,
) -> Dict[str, str]:
    """Metadata fragment to persist on batch creation."""
    return {
        "load_storage_dir": str(storage_dir.resolve()),
        "organization_slug": org_slug,
        "load_timestamp": load_timestamp.isoformat(timespec="seconds"),
    }

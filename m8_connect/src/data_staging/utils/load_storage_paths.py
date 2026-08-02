"""Hierarchical load storage paths per organization and load type."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Literal, Optional

from data_staging.config import settings
from data_staging.utils.batch_control import normalize_metadata

LoadType = Literal["history", "catalog"]

HISTORIA_DIR = "historia"
CATALOGOS_DIR = "catalogos"
LOAD_TIMESTAMP_FMT = "%Y-%m-%d_%H%M%S"

_INVALID_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
)


def format_load_timestamp(ts: Optional[datetime] = None) -> str:
    """Folder name for a load: YYYY-MM-DD_HHMMSS."""
    when = ts or datetime.now()
    return when.strftime(LOAD_TIMESTAMP_FMT)


def sanitize_organization_folder_name(name: str) -> str:
    """Make organization display name safe as a single path segment."""
    cleaned = _INVALID_PATH_CHARS.sub("_", str(name or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip().rstrip(". ")
    if not cleaned:
        return ""
    upper = cleaned.upper()
    if upper in _WINDOWS_RESERVED_NAMES:
        cleaned = f"_{cleaned}"
    return cleaned[:120]


def resolve_organization_folder_segment(
    organization_id: str,
    organization_name: Optional[str] = None,
) -> str:
    """Folder segment: organization name when available, else organization_id."""
    org_id = organization_id.strip()
    if not org_id:
        raise ValueError("organization_id is required")
    if organization_name:
        segment = sanitize_organization_folder_name(organization_name)
        if segment:
            return segment
    return org_id


def build_load_storage_dir(
    organization_id: str,
    load_type: LoadType,
    *,
    organization_name: Optional[str] = None,
    catalog_name: Optional[str] = None,
    load_timestamp: Optional[datetime] = None,
    upload_root: Optional[Path] = None,
) -> Path:
    """
    Build path under UPLOAD_PATH:
      {organization_name}/historia/{timestamp}/
      {organization_name}/catalogos/{catalog}/{timestamp}/
    """
    root = (upload_root or Path(settings.UPLOAD_PATH)).resolve()
    org_key = resolve_organization_folder_segment(organization_id, organization_name)

    normalized_type = (load_type or "history").lower()
    if normalized_type not in ("history", "catalog"):
        normalized_type = "history"

    ts_folder = format_load_timestamp(load_timestamp)

    if normalized_type == "catalog":
        if not catalog_name:
            raise ValueError("catalog_name is required for catalog loads")
        catalog_segment = catalog_name.strip().lower().replace(" ", "_")
        return root / org_key / CATALOGOS_DIR / catalog_segment / ts_folder

    return root / org_key / HISTORIA_DIR / ts_folder


def ensure_load_storage_dir(
    organization_id: str,
    load_type: LoadType,
    *,
    organization_name: Optional[str] = None,
    catalog_name: Optional[str] = None,
    load_timestamp: Optional[datetime] = None,
    upload_root: Optional[Path] = None,
) -> Path:
    """Create org/load-type/[catalog]/timestamp directories if missing."""
    path = build_load_storage_dir(
        organization_id,
        load_type,
        organization_name=organization_name,
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
    organization_id: str,
    load_timestamp: datetime,
) -> Dict[str, str]:
    """Metadata fragment to persist on batch creation."""
    return {
        "load_storage_dir": str(storage_dir.resolve()),
        "organization_id": organization_id.strip(),
        "load_timestamp": load_timestamp.isoformat(timespec="seconds"),
    }

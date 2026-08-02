"""Incremental load storage paths: {org}/{YYYY-MM-DD}/catalogos|historia/."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Literal, Optional

from data_staging.utils.batch_staging_files import batch_artifact_path
from data_staging.utils.load_storage_paths import (
    CATALOGOS_DIR,
    HISTORIA_DIR,
    resolve_organization_folder_segment,
    sanitize_organization_folder_name,
)

LoadKind = Literal["catalog", "history"]

LOAD_DATE_FMT = "%Y-%m-%d"


def format_load_date(d: Optional[date] = None) -> str:
    when = d or date.today()
    return when.strftime(LOAD_DATE_FMT)


def build_incremental_storage_dir(
    organization_id: str,
    load_kind: LoadKind,
    *,
    organization_name: Optional[str] = None,
    load_date: Optional[date] = None,
    upload_root: Optional[Path] = None,
) -> Path:
    """{upload_root}/{org}/{YYYY-MM-DD}/catalogos|historia/"""
    from m8_incremental.config import upload_root as default_upload_root

    root = (upload_root or default_upload_root()).resolve()
    org_key = resolve_organization_folder_segment(organization_id, organization_name)
    date_seg = format_load_date(load_date)
    sub = CATALOGOS_DIR if load_kind == "catalog" else HISTORIA_DIR
    return root / org_key / date_seg / sub


def ensure_incremental_storage_dir(*args, **kwargs) -> Path:
    path = build_incremental_storage_dir(*args, **kwargs)
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_source_dir(
    profile_source_path: str,
    *,
    fallback_root: Optional[Path] = None,
) -> Path:
    """Resolve organization source directory."""
    path = Path(profile_source_path)
    if path.is_absolute() and path.is_dir():
        return path
    if fallback_root:
        candidate = fallback_root / profile_source_path
        if candidate.is_dir():
            return candidate
        candidate = fallback_root / sanitize_organization_folder_name(profile_source_path)
        if candidate.is_dir():
            return candidate
    if path.is_dir():
        return path.resolve()
    raise FileNotFoundError(f"Source path not found: {profile_source_path}")


def source_catalog_dir(source_root: Path) -> Path:
    return source_root / CATALOGOS_DIR


def source_history_dir(source_root: Path) -> Path:
    return source_root / HISTORIA_DIR


def suggest_org_source_path(
    *,
    organization_id: str,
    organization_name: Optional[str] = None,
    source_root: Optional[Path] = None,
) -> str:
    """Suggested absolute (or relative) path under INCREMENTAL_SOURCE_ROOT/{org}."""
    from m8_incremental.config import default_source_root

    root = source_root if source_root is not None else default_source_root()
    segment = resolve_organization_folder_segment(organization_id, organization_name)
    if root is None:
        return segment
    return str((root / segment).resolve())


def ensure_org_source_layout(source_path: str) -> Path:
    """
    Ensure organization source folder exists with catalogos/ and historia/.
    Relative paths are resolved under INCREMENTAL_SOURCE_ROOT when configured.
    """
    from m8_incremental.config import default_source_root

    path = Path(str(source_path or "").strip())
    if not str(path):
        raise ValueError("source_path is required")
    if not path.is_absolute():
        root = default_source_root()
        path = (root / path) if root is not None else path
    path = path.resolve()
    path.mkdir(parents=True, exist_ok=True)
    (path / CATALOGOS_DIR).mkdir(parents=True, exist_ok=True)
    (path / HISTORIA_DIR).mkdir(parents=True, exist_ok=True)
    return path


def incremental_artifact_path(
    batch_id: str,
    suffix: str,
    *,
    storage_dir: Path,
) -> Path:
    return batch_artifact_path(batch_id, suffix, work_dir=storage_dir)

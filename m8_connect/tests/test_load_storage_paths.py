"""Tests for hierarchical load storage paths."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from data_staging.utils.load_storage_paths import (
    CATALOGOS_DIR,
    HISTORIA_DIR,
    build_load_storage_dir,
    ensure_load_storage_dir,
    format_load_timestamp,
    load_storage_metadata_fields,
    resolve_batch_work_dir,
    sanitize_organization_folder_name,
)

ORG_ID = "34b43c21-7aac-4f1c-b6b4-df8d29f7b091"
ORG_NAME = "M8 Solutions"


def test_format_load_timestamp():
    ts = datetime(2026, 6, 12, 14, 30, 52)
    assert format_load_timestamp(ts) == "2026-06-12_143052"


def test_build_history_storage_dir(tmp_path: Path):
    ts = datetime(2026, 6, 12, 14, 30, 52)
    path = build_load_storage_dir(
        ORG_ID,
        "history",
        organization_name=ORG_NAME,
        load_timestamp=ts,
        upload_root=tmp_path,
    )
    assert path == tmp_path / ORG_NAME / HISTORIA_DIR / "2026-06-12_143052"


def test_build_history_storage_dir_falls_back_to_org_id(tmp_path: Path):
    ts = datetime(2026, 6, 12, 14, 30, 52)
    path = build_load_storage_dir(
        ORG_ID,
        "history",
        load_timestamp=ts,
        upload_root=tmp_path,
    )
    assert path == tmp_path / ORG_ID / HISTORIA_DIR / "2026-06-12_143052"


def test_build_catalog_storage_dir(tmp_path: Path):
    ts = datetime(2026, 6, 12, 14, 30, 52)
    path = build_load_storage_dir(
        ORG_ID,
        "catalog",
        organization_name=ORG_NAME,
        catalog_name="skus",
        load_timestamp=ts,
        upload_root=tmp_path,
    )
    assert path == tmp_path / ORG_NAME / CATALOGOS_DIR / "skus" / "2026-06-12_143052"


def test_sanitize_organization_folder_name():
    assert sanitize_organization_folder_name("  M8 Solutions  ") == "M8 Solutions"
    assert sanitize_organization_folder_name("Org/Name:Test") == "Org_Name_Test"


def test_ensure_load_storage_dir_creates_directories(tmp_path: Path):
    ts = datetime(2026, 6, 12, 14, 30, 52)
    path = ensure_load_storage_dir(
        ORG_ID,
        "catalog",
        organization_name=ORG_NAME,
        catalog_name="location",
        load_timestamp=ts,
        upload_root=tmp_path,
    )
    assert path.is_dir()
    assert (tmp_path / ORG_NAME / CATALOGOS_DIR / "location").is_dir()


def test_resolve_batch_work_dir_uses_metadata(tmp_path: Path, monkeypatch):
    work = tmp_path / ORG_ID / HISTORIA_DIR / "2026-06-12_120000"
    work.mkdir(parents=True)
    resolved = resolve_batch_work_dir({"load_storage_dir": str(work)})
    assert resolved == work.resolve()


def test_resolve_batch_work_dir_legacy_fallback(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "data_staging.config.settings.TEMP_PATH",
        str(tmp_path / "temp"),
    )
    legacy = resolve_batch_work_dir({})
    assert legacy == (tmp_path / "temp").resolve()


def test_build_catalog_requires_catalog_name(tmp_path: Path):
    with pytest.raises(ValueError, match="catalog_name"):
        build_load_storage_dir(ORG_ID, "catalog", upload_root=tmp_path)


def test_load_storage_metadata_fields(tmp_path: Path):
    ts = datetime(2026, 6, 12, 14, 30, 52)
    storage = tmp_path / ORG_ID / HISTORIA_DIR / "2026-06-12_143052"
    storage.mkdir(parents=True)
    fields = load_storage_metadata_fields(storage, ORG_ID, ts)
    assert fields["organization_id"] == ORG_ID
    assert fields["load_storage_dir"] == str(storage.resolve())
    assert fields["load_timestamp"] == "2026-06-12T14:30:52"


def test_build_load_storage_dir_requires_organization_id(tmp_path: Path):
    with pytest.raises(ValueError, match="organization_id"):
        build_load_storage_dir("", "history", upload_root=tmp_path)

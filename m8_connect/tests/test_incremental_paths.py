"""Tests for incremental storage path layout."""

from datetime import date
from pathlib import Path

from m8_incremental.paths import (
    build_incremental_storage_dir,
    ensure_org_source_layout,
    format_load_date,
    source_catalog_dir,
    source_history_dir,
    suggest_org_source_path,
)


def test_format_load_date():
    assert format_load_date(date(2026, 6, 22)) == "2026-06-22"


def test_build_incremental_storage_dir_layout(tmp_path):
    catalog = build_incremental_storage_dir(
        "uuid-org",
        "catalog",
        organization_name="Acme Corp",
        load_date=date(2026, 6, 22),
        upload_root=tmp_path,
    )
    history = build_incremental_storage_dir(
        "uuid-org",
        "history",
        organization_name="Acme Corp",
        load_date=date(2026, 6, 22),
        upload_root=tmp_path,
    )
    assert catalog == tmp_path / "Acme Corp" / "2026-06-22" / "catalogos"
    assert history == tmp_path / "Acme Corp" / "2026-06-22" / "historia"


def test_source_subdirs(tmp_path):
    root = tmp_path / "Acme"
    root.mkdir()
    assert source_catalog_dir(root) == root / "catalogos"
    assert source_history_dir(root) == root / "historia"


def test_suggest_org_source_path(tmp_path):
    path = suggest_org_source_path(
        organization_id="uuid-1",
        organization_name="Patito",
        source_root=tmp_path,
    )
    assert Path(path) == (tmp_path / "Patito").resolve()


def test_ensure_org_source_layout_creates_subdirs(tmp_path):
    org_dir = tmp_path / "NuevaOrg"
    ensured = ensure_org_source_layout(str(org_dir))
    assert ensured == org_dir.resolve()
    assert (ensured / "catalogos").is_dir()
    assert (ensured / "historia").is_dir()

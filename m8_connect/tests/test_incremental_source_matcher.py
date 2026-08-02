"""Tests for incremental catalog source file matching."""

from pathlib import Path

from data_staging.services.catalog.catalog_store import get_catalog_by_name
from m8_incremental.services.source_matcher import (
    catalog_mapping_targets,
    match_catalog_source_file,
)


def _files(*names: str, tmp_path: Path) -> list[Path]:
    paths = []
    for name in names:
        path = tmp_path / name
        path.write_text("h\n1", encoding="utf-8")
        paths.append(path)
    return paths


def test_match_skus_requires_slug_in_filename(tmp_path):
    files = _files("Locations.csv", "skus.csv", tmp_path=tmp_path)
    entry = get_catalog_by_name("skus")
    matched = match_catalog_source_file(files, "skus", entry)
    assert matched is not None
    assert matched.name == "skus.csv"


def test_sku_csv_does_not_match_skus_slug(tmp_path):
    files = _files("Locations.csv", "sku.csv", tmp_path=tmp_path)
    entry = get_catalog_by_name("skus")
    assert match_catalog_source_file(files, "skus", entry) is None


def test_match_location_to_locations_csv(tmp_path):
    files = _files("Locations.csv", "skus.csv", tmp_path=tmp_path)
    entry = get_catalog_by_name("location")
    matched = match_catalog_source_file(files, "location", entry)
    assert matched is not None
    assert matched.name == "Locations.csv"


def test_no_fallback_to_unrelated_file(tmp_path):
    files = _files("Locations.csv", tmp_path=tmp_path)
    entry = get_catalog_by_name("skus")
    assert match_catalog_source_file(files, "skus", entry) is None


def test_catalog_mapping_targets_include_required_columns():
    skus = get_catalog_by_name("skus")
    targets = catalog_mapping_targets(skus)
    assert "status" in targets
    assert "sku" in targets
    assert "name" in targets

    location = get_catalog_by_name("location")
    loc_targets = catalog_mapping_targets(location)
    assert "code" in loc_targets
    assert "name" in loc_targets

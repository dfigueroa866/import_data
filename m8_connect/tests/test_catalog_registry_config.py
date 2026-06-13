"""Tests for catalog config path resolution."""

from __future__ import annotations

from pathlib import Path

from data_staging.services.catalog import catalog_registry


def test_config_root_points_to_project_config_catalog():
    root = catalog_registry.resolve_catalog_config_root()
    assert root.is_dir(), f"Expected config dir at {root}"
    assert "src" not in root.parts[-3:], f"Config root must not be under src/: {root}"
    assert (root / "location_config.json").is_file()
    assert (root / "skus_config.json").is_file()


def test_load_validation_rules_location():
    rules = catalog_registry.load_validation_rules("location")
    assert isinstance(rules, dict)

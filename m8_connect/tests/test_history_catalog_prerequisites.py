"""Tests for history catalog prerequisite gate."""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from data_staging.services.history.history_catalog_prerequisites import (
    check_history_catalog_readiness,
    normalize_catalog_slug,
)


def test_normalize_catalog_slug_aliases():
    assert normalize_catalog_slug("locations") == "location"
    assert normalize_catalog_slug("SKUS") == "skus"
    assert normalize_catalog_slug("unknown") is None


def test_readiness_missing_org():
    db = MagicMock()
    result = check_history_catalog_readiness(db, "")
    assert result["ready"] is False
    assert result["missing"] == ["skus", "location"]
    db.execute.assert_not_called()


def test_readiness_no_promoted_batches():
    db = MagicMock()
    db.execute.return_value.fetchall.return_value = []
    result = check_history_catalog_readiness(db, "org-1")
    assert result["ready"] is False
    assert set(result["missing"]) == {"skus", "location"}
    assert "Productos (SKUs)" in result["message"]


def test_readiness_only_skus():
    db = MagicMock()
    db.execute.return_value.fetchall.return_value = [("skus",)]
    result = check_history_catalog_readiness(db, "org-1")
    assert result["ready"] is False
    assert result["missing"] == ["location"]
    assert result["promoted_catalogs"] == ["skus"]


def test_readiness_both_catalogs():
    db = MagicMock()
    db.execute.return_value.fetchall.return_value = [("skus",), ("locations",)]
    result = check_history_catalog_readiness(db, "org-1")
    assert result["ready"] is True
    assert result["missing"] == []
    assert set(result["promoted_catalogs"]) == {"skus", "location"}


def test_assert_history_catalog_ready_respects_flag(monkeypatch):
    from data_staging.api.v1 import upload as upload_module

    monkeypatch.setattr(upload_module.settings, "HISTORY_REQUIRE_PROMOTED_CATALOGS", False)
    db = MagicMock()
    upload_module._assert_history_catalog_ready(db, "org-1")
    db.execute.assert_not_called()


def test_assert_history_catalog_ready_blocks(monkeypatch):
    from data_staging.api.v1 import upload as upload_module

    monkeypatch.setattr(upload_module.settings, "HISTORY_REQUIRE_PROMOTED_CATALOGS", True)
    db = MagicMock()
    db.execute.return_value.fetchall.return_value = []
    with pytest.raises(HTTPException) as exc:
        upload_module._assert_history_catalog_ready(db, "org-1")
    assert exc.value.status_code == 409
    assert "historia" in str(exc.value.detail).lower()

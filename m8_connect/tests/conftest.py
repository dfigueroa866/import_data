"""Pytest fixtures for batch golden regression tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

import polars as pl
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_INCREMENTAL_SRC = _REPO_ROOT / "m8_incremental" / "src"
if _INCREMENTAL_SRC.is_dir() and str(_INCREMENTAL_SRC) not in sys.path:
    sys.path.insert(0, str(_INCREMENTAL_SRC))

GOLDEN_BATCH_ID = "7cd1ffb6-71a7-48e2-80c1-f38d25667342"
GOLDEN_SHORT_ID = "7cd1ffb6"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "batches" / GOLDEN_SHORT_ID


@pytest.fixture(scope="session")
def golden_expected() -> Dict[str, Any]:
    path = FIXTURES_DIR / "expected.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def golden_raw_csv() -> Path:
    return FIXTURES_DIR / "transactions_dummy.csv"


@pytest.fixture(scope="session")
def golden_aggregated_parquet() -> Path:
    return FIXTURES_DIR / "aggregated.parquet"


@pytest.fixture(scope="session")
def golden_column_mappings_wizard() -> Dict[str, Dict[str, Any]]:
    return {
        "location": {"target": "location_code"},
        "sku": {"target": "sku"},
        "quantity": {"target": "quantity"},
        "start_date": {"target": "period_start"},
        "pieces": {"target": "pieces"},
    }


@pytest.fixture(scope="session")
def golden_column_mappings() -> Dict[str, Dict[str, Any]]:
    """Target-column mapping for pre-mapped aggregated Parquet."""
    return {
        "location_code": {"source": "location"},
        "sku": {"source": "sku"},
        "quantity": {"source": "quantity"},
        "period_start": {"source": "start_date"},
        "pieces": {"source": "pieces"},
        "organization_id": {"default": None},
        "granularity": {"default": None},
        "source": {"default": None},
        "sales_channel": {"default": None},
    }


@pytest.fixture(scope="session")
def golden_column_toggles() -> Dict[str, bool]:
    return {
        "location": True,
        "sku": True,
        "quantity": True,
        "start_date": True,
        "pieces": True,
    }


@pytest.fixture
def golden_fk_sets(golden_aggregated_parquet: Path) -> Dict[str, set]:
    """FK sets derived from aggregated fixture (offline tests)."""
    df = pl.read_parquet(golden_aggregated_parquet)
    skus = {str(v).strip().lower() for v in df["sku"].to_list() if v is not None}
    locs = {str(v).strip().lower() for v in df["location_code"].to_list() if v is not None}
    return {
        "__valid_skus__": skus,
        "__valid_locations__": locs,
        "__fk_org_scoped__": True,
    }

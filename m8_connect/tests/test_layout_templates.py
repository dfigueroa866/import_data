"""Tests for upload layout CSV generation helpers."""

from data_staging.services.layout_templates import _build_csv, _example_from_type, _stringify_cell


def test_build_csv_includes_header_and_example():
    columns = [
        {"name": "sku", "type": "character varying"},
        {"name": "name", "type": "character varying"},
        {"name": "status", "type": "USER-DEFINED"},
    ]
    example = {"sku": "SKU-1", "name": "Producto", "status": "active"}
    raw = _build_csv(columns, example).decode("utf-8-sig")
    lines = raw.strip().splitlines()
    assert lines[0] == "sku,name,status"
    assert lines[1] == "SKU-1,Producto,active"


def test_example_from_type_uses_sensible_defaults():
    assert _example_from_type({"name": "status", "type": "USER-DEFINED"}) == "active"
    assert _example_from_type({"name": "quantity", "type": "numeric"}) == "1"
    assert len(_example_from_type({"name": "period_start", "type": "date"})) == 10


def test_stringify_cell_handles_none_and_bool():
    assert _stringify_cell(None) == ""
    assert _stringify_cell(True) == "true"
    assert _stringify_cell(False) == "false"

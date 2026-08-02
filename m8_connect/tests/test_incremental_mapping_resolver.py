"""Tests for incremental column mapping resolver."""

from m8_incremental.services.mapping_resolver import build_incremental_mappings


def test_history_mappings_require_exact_headers():
    headers = [
        "organization_id",
        "granularity",
        "sku",
        "location_code",
        "period_start",
        "quantity",
        "pieces",
    ]
    mappings, toggles, process_type, missing = build_incremental_mappings(
        file_headers=headers,
        load_type="history",
        organization_id="org-uuid-123",
        granularity="weekly",
    )
    assert process_type == "Weekly"
    assert missing == []
    assert mappings["__fixed_organization_id__"]["default_value"] == "org-uuid-123"
    assert mappings["__fixed_granularity__"]["default_value"] == "weekly"
    assert toggles["__fixed_organization_id__"]["selected"] is True
    assert mappings["sku"]["target"] == "sku"
    assert mappings["location_code"]["target"] == "location_code"
    assert "__file__sku" not in mappings


def test_history_reports_missing_exact_headers():
    _, _, _, missing = build_incremental_mappings(
        file_headers=["org", "gran", "sku", "loc", "date", "qty", "pcs"],
        load_type="history",
        organization_id="x",
        granularity="monthly",
    )
    assert "organization_id" in missing
    assert "granularity" in missing


def test_monthly_granularity_maps_to_monthly_process_type():
    _, _, process_type, missing = build_incremental_mappings(
        file_headers=[
            "organization_id",
            "granularity",
            "sku",
            "location_code",
            "period_start",
            "quantity",
            "pieces",
        ],
        load_type="history",
        organization_id="x",
        granularity="monthly",
    )
    assert process_type == "Monthly"
    assert missing == []


def test_catalog_mappings_use_wizard_file_column_keys():
    headers = ["sku", "name", "category", "brand", "status"]
    mappings, toggles, _, missing = build_incremental_mappings(
        file_headers=headers,
        load_type="catalog",
        organization_id="org-1",
        catalog_targets=["sku", "name", "status"],
        catalog_optional_targets=["category", "brand"],
    )
    assert missing == []
    assert mappings["__fixed_organization_id__"]["source"] is None
    assert mappings["sku"]["target"] == "sku"
    assert mappings["name"]["target"] == "name"
    assert mappings["category"]["target"] == "category"
    assert mappings["brand"]["target"] == "brand"
    assert toggles["sku"]["selected"] is True
    assert "__file__sku" not in mappings


def test_catalog_maps_code_header_to_sku_via_alias():
    """CSV may use 'code' while public.skus column is 'sku'."""
    headers = ["code", "name", "category", "family", "brand", "status"]
    aliases = {
        "sku": ["sku", "code", "sku_code", "product_code"],
        "name": ["name"],
        "status": ["status"],
        "category": ["category"],
        "brand": ["brand"],
    }
    mappings, _, _, missing = build_incremental_mappings(
        file_headers=headers,
        load_type="catalog",
        organization_id="org-1",
        catalog_targets=["sku", "name", "status"],
        catalog_optional_targets=["category", "brand"],
        column_aliases=aliases,
    )
    assert missing == []
    assert mappings["code"]["target"] == "sku"
    assert mappings["name"]["target"] == "name"
    assert mappings["status"]["target"] == "status"
    assert mappings["category"]["target"] == "category"
    assert mappings["brand"]["target"] == "brand"
    assert "family" not in mappings


def test_catalog_reports_missing_columns():
    _, _, _, missing = build_incremental_mappings(
        file_headers=["status"],
        load_type="catalog",
        organization_id="org-1",
        catalog_targets=["sku", "name", "status"],
    )
    assert "sku" in missing
    assert "name" in missing
    assert "status" not in missing

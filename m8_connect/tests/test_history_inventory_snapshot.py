"""Tests for multi-table history configuration."""

from data_staging.services.history.history_config import (
    get_history_table_meta,
    is_history_target,
    is_valid_process_type,
    resolve_history_rules,
    resolve_history_table_name,
    valid_process_type_keys,
)
from data_staging.services.history.history_registry import (
    get_history_table,
    list_history_tables,
)


def test_list_history_tables_includes_inventory_snapshot():
    tables = list_history_tables(active_only=True)
    names = {t["name"] for t in tables}
    assert "sales_history" in names
    assert "inventory_snapshot" in names


def test_inventory_snapshot_meta():
    meta = get_history_table_meta("inventory_snapshot")
    assert meta["target_table"] == "inventory_snapshot"
    assert meta["supports_aggregation"] is False
    assert "snapshot_date" in meta["required_mapping_columns"]
    assert "on_hand_qty" in meta["required_mapping_columns"]
    assert meta["features"]["auto_sales_channel"] is False
    assert meta["process_types"][0]["key"] == "Snapshot"


def test_resolve_inventory_rules_from_entry():
    entry = get_history_table("inventory_snapshot")
    assert entry is not None
    rules = resolve_history_rules({"history_config": entry})
    assert rules["name"] == "inventory_snapshot"
    assert rules["supports_aggregation"] is False
    assert "snapshot_date" in rules["required_mapping_columns"]
    assert "granularity" not in rules["non_mappable_targets"]


def test_is_history_target_inventory():
    assert is_history_target("public", "inventory_snapshot")
    assert is_history_target("public", "sales_history")


def test_snapshot_process_type_valid_for_inventory_table():
    metadata = {
        "target_table": "inventory_snapshot",
        "history_config": get_history_table_meta("inventory_snapshot"),
    }
    history_name = resolve_history_table_name(metadata)
    assert history_name == "inventory_snapshot"
    assert is_valid_process_type("Snapshot", history_name)
    assert not is_valid_process_type("Weekly", history_name)
    assert valid_process_type_keys(history_name) == ("Snapshot",)


def test_sales_history_process_types_unchanged():
    metadata = {
        "target_table": "sales_history",
        "history_config": get_history_table_meta("sales_history"),
    }
    history_name = resolve_history_table_name(metadata)
    assert is_valid_process_type("Weekly", history_name)
    assert is_valid_process_type("Monthly", history_name)
    assert not is_valid_process_type("Snapshot", history_name)

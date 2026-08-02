"""Tests for upload file preservation after catalog promotion."""

from data_staging.utils.batch_control import should_preserve_upload_files


def test_preserve_catalog_promoted_by_status():
    meta = {"load_type": "catalog"}
    assert should_preserve_upload_files(meta, batch_status="PROMOTED") is True
    assert should_preserve_upload_files(meta, batch_status="PARTIALLY_PROMOTED") is True


def test_preserve_catalog_not_promoted():
    meta = {"load_type": "catalog"}
    assert should_preserve_upload_files(meta, batch_status="COMPLETED") is False


def test_preserve_flag_in_metadata():
    meta = {"preserve_upload_files": True, "load_type": "history"}
    assert should_preserve_upload_files(meta, batch_status="COMPLETED") is True


def test_history_promoted_not_preserved_by_default():
    meta = {"load_type": "history"}
    assert should_preserve_upload_files(meta, batch_status="PROMOTED") is False

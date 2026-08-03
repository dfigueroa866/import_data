"""Tests for upload file preservation after catalog promotion."""

from pathlib import Path

from data_staging.api.v1.upload import _delete_batch_files
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


def test_force_delete_removes_catalog_storage_dir(tmp_path):
    """Explicit batch delete must remove load folder even for promoted catalogs."""
    storage = tmp_path / "skus_load"
    storage.mkdir()
    artifact = storage / "batch_validated.parquet"
    artifact.write_text("x", encoding="utf-8")

    meta = {
        "load_type": "catalog",
        "preserve_upload_files": True,
        "load_storage_dir": str(storage),
    }
    _delete_batch_files(
        "batch-1",
        meta,
        None,
        batch_status="PROMOTED",
        force=False,
    )
    assert storage.is_dir()
    assert artifact.is_file()

    _delete_batch_files(
        "batch-1",
        meta,
        None,
        batch_status="PROMOTED",
        force=True,
    )
    assert not storage.exists()

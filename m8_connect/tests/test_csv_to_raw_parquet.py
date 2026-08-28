"""CSV → raw Parquet must not infer mixed identifier columns as integers."""

from __future__ import annotations

from pathlib import Path

import polars as pl

from data_staging.utils.raw_parquet import csv_to_raw_parquet


def test_csv_to_raw_parquet_keeps_alphanumeric_sku_after_numeric_rows(tmp_path: Path):
    csv_path = tmp_path / "skus.csv"
    rows = ["sku,name"]
    rows.extend(f"{i},Product {i}" for i in range(1, 121))
    rows.append("BACC1/2,Special")
    csv_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    parquet_path = csv_to_raw_parquet(
        csv_path,
        target_column_types={"sku": "character varying(50)", "name": "text"},
    )

    df = pl.read_parquet(parquet_path)
    skus = df["sku"].to_list()
    assert "BACC1/2" in skus
    assert df["sku"].dtype == pl.Utf8

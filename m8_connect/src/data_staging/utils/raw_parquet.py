"""Convert uploaded CSV to columnar Parquet for downstream streaming."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import polars as pl

from data_staging.config import settings
from data_staging.utils.encoding_utils import detect_file_encoding, encoding_for_polars


def csv_to_raw_parquet(
    csv_path: Path,
    parquet_path: Optional[Path] = None,
    delimiter: str = ",",
) -> Path:
    """Convert CSV upload to Utf8 Parquet (all columns as string).

    Caller is responsible for removing the source CSV after a successful conversion.
    """
    parquet_path = parquet_path or csv_path.with_suffix(".raw.parquet")
    pl_encoding = encoding_for_polars(detect_file_encoding(csv_path))
    df = pl.read_csv(
        csv_path,
        separator=delimiter,
        encoding=pl_encoding,
        ignore_errors=True,
        truncate_ragged_lines=True,
        infer_schema_length=0,
        try_parse_dates=False,
    )
    compression = getattr(settings, "PARQUET_COMPRESSION", "snappy")
    df.write_parquet(parquet_path, compression=compression)
    return parquet_path

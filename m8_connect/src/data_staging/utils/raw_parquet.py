"""Convert uploaded CSV to columnar Parquet for downstream streaming."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import polars as pl
import pyarrow.parquet as pq

from data_staging.config import settings
from data_staging.utils.chunk_iterators import iter_csv_chunks
from data_staging.utils.encoding_utils import detect_file_encoding, encoding_for_polars


def csv_to_raw_parquet(
    csv_path: Path,
    parquet_path: Optional[Path] = None,
    delimiter: str = ",",
) -> Path:
    """Convert CSV upload to Utf8 Parquet via streaming chunks (no full-file load)."""
    parquet_path = parquet_path or csv_path.with_suffix(".raw.parquet")
    pl_encoding = encoding_for_polars(detect_file_encoding(csv_path))
    compression = getattr(settings, "PARQUET_COMPRESSION", "snappy")
    chunk_size = int(getattr(settings, "PROCESS_CHUNK_SIZE", 250_000))

    writer: Optional[pq.ParquetWriter] = None
    try:
        for chunk in iter_csv_chunks(
            csv_path,
            chunk_size,
            delimiter=delimiter,
            encoding=pl_encoding,
        ):
            if chunk.is_empty():
                continue
            chunk = chunk.with_columns(
                [pl.col(c).cast(pl.Utf8) for c in chunk.columns]
            )
            table = chunk.to_arrow()
            if writer is None:
                parquet_path.parent.mkdir(parents=True, exist_ok=True)
                writer = pq.ParquetWriter(parquet_path, table.schema, compression=compression)
            writer.write_table(table)
    finally:
        if writer is not None:
            writer.close()

    if writer is None:
        empty = pl.DataFrame({})
        empty.write_parquet(parquet_path, compression=compression)

    return parquet_path

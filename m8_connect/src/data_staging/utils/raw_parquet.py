"""Convert uploaded CSV to typed columnar Parquet for downstream streaming."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Mapping, Optional

import polars as pl
import pyarrow.parquet as pq

from data_staging.config import settings
from data_staging.utils.chunk_iterators import iter_csv_chunks
from data_staging.utils.encoding_utils import detect_file_encoding, encoding_for_polars
from data_staging.utils.parquet_typing import (
    cast_dataframe_to_target_types,
    map_file_headers_to_target_types,
)


def csv_to_raw_parquet(
    csv_path: Path,
    parquet_path: Optional[Path] = None,
    delimiter: str = ",",
    target_column_types: Optional[Mapping[str, str]] = None,
) -> Path:
    """
    Convert CSV upload to Parquet via streaming chunks.

    When ``target_column_types`` is provided, each file column is cast to the
    matching PostgreSQL type (by column name). Unmatched headers remain Utf8.
    """
    parquet_path = parquet_path or csv_path.with_suffix(".raw.parquet")
    pl_encoding = encoding_for_polars(detect_file_encoding(csv_path))
    compression = getattr(settings, "PARQUET_COMPRESSION", "snappy")
    chunk_size = int(getattr(settings, "PROCESS_CHUNK_SIZE", 250_000))

    file_column_types: Optional[Dict[str, str]] = None
    if target_column_types:
        header_df = pl.read_csv(
            csv_path,
            n_rows=0,
            separator=delimiter,
            encoding=pl_encoding,
        )
        file_column_types = map_file_headers_to_target_types(
            list(header_df.columns),
            target_column_types,
        )

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
            if file_column_types:
                chunk = cast_dataframe_to_target_types(chunk, file_column_types)
            else:
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

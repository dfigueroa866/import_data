"""Streaming chunk iterators for large file processing."""

from __future__ import annotations

from pathlib import Path
from typing import Generator, Iterator, Tuple

import polars as pl
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

from data_staging.utils.encoding_utils import encoding_for_polars, repair_mojibake_text

_MOJIBAKE_SAMPLE_ROWS = 1000


def _columns_needing_mojibake_repair(part: pl.DataFrame) -> list[str]:
    """Sample Utf8 columns and repair only those with suspicious bytes."""
    utf8_cols = [c for c in part.columns if part.schema[c] == pl.Utf8]
    if not utf8_cols:
        return []
    sample = part.select(utf8_cols).head(_MOJIBAKE_SAMPLE_ROWS)
    needs_repair: list[str] = []
    for col in utf8_cols:
        series = sample[col]
        if series.is_null().all():
            continue
        joined = "\n".join(str(v) for v in series.to_list() if v is not None)
        if repair_mojibake_text(joined) != joined:
            needs_repair.append(col)
    return needs_repair


def _apply_mojibake_repair(part: pl.DataFrame) -> pl.DataFrame:
    cols = _columns_needing_mojibake_repair(part)
    if not cols:
        return part
    return part.with_columns(
        [
            pl.col(col).map_elements(repair_mojibake_text, return_dtype=pl.Utf8)
            for col in cols
        ]
    )


def count_csv_rows(file_path: Path, delimiter: str = ",", encoding: str = "utf-8") -> int:
    pl_encoding = encoding_for_polars(encoding)
    try:
        result = pl.scan_csv(
            file_path,
            separator=delimiter,
            encoding=pl_encoding,
            infer_schema_length=0,
        ).select(pl.len()).collect()
        return int(result.item())
    except Exception:
        return sum(1 for _ in open(file_path, encoding=encoding_for_polars(encoding), errors="replace")) - 1


def count_parquet_rows(file_path: Path) -> int:
    pf = pq.ParquetFile(file_path)
    return pf.metadata.num_rows


def parquet_column_names(file_path: Path) -> list[str]:
    """Column names from Parquet metadata (Polars 0.x / 1.x compatible)."""
    return list(pl.read_parquet(file_path, n_rows=0).columns)


def iter_parquet_chunks(file_path: Path, chunk_size: int) -> Iterator[pl.DataFrame]:
    pf = pq.ParquetFile(file_path)
    for batch in pf.iter_batches(batch_size=chunk_size):
        yield pl.from_arrow(batch)


def iter_csv_chunks(
    file_path: Path,
    chunk_size: int,
    delimiter: str = ",",
    encoding: str = "utf-8",
) -> Iterator[pl.DataFrame]:
    """Yield Polars DataFrames of up to chunk_size rows via PyArrow CSV blocks."""
    parse_options = pacsv.ParseOptions(delimiter=delimiter)
    read_options = pacsv.ReadOptions(block_size=max(1 << 20, chunk_size * 512))
    convert_options = pacsv.ConvertOptions(strings_can_be_null=True)
    reader = pacsv.open_csv(
        file_path,
        read_options=read_options,
        parse_options=parse_options,
        convert_options=convert_options,
    )

    buffer: list = []
    buffer_rows = 0

    for record_batch in reader:
        part = pl.from_arrow(record_batch)
        part = _apply_mojibake_repair(part)
        offset = 0
        while offset < part.height:
            take = min(chunk_size - buffer_rows, part.height - offset)
            slice_df = part.slice(offset, take)
            if buffer_rows == 0:
                buffer = [slice_df]
                buffer_rows = take
            else:
                buffer.append(slice_df)
                buffer_rows += take
            offset += take
            if buffer_rows >= chunk_size:
                yield pl.concat(buffer) if len(buffer) > 1 else buffer[0]
                buffer = []
                buffer_rows = 0

    if buffer_rows > 0:
        yield pl.concat(buffer) if len(buffer) > 1 else buffer[0]


def iter_file_chunks(
    file_path: Path,
    chunk_size: int,
    delimiter: str = ",",
    encoding: str = "utf-8",
) -> Tuple[int, Generator[pl.DataFrame, None, None]]:
    ext = file_path.suffix.lower()
    if ext == ".parquet":
        total = count_parquet_rows(file_path)
        return total, iter_parquet_chunks(file_path, chunk_size)
    if ext == ".csv":
        total = count_csv_rows(file_path, delimiter, encoding)
        return total, iter_csv_chunks(file_path, chunk_size, delimiter, encoding)
    raise ValueError(f"Unsupported file type for streaming: {ext}")

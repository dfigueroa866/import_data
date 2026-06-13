"""Paths and I/O for batch valid/rejected staging files on disk."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from data_staging.services.catalog.catalog_transforms import coalesce_empty_to_none, is_empty_value
from data_staging.config import settings
from data_staging.utils.batch_control import normalize_metadata
from data_staging.utils.load_storage_paths import batch_artifact_path, resolve_batch_work_dir

VALID_SUFFIX = "_valid_records.parquet"
REJECTED_SUFFIX = "_rejected_records.tsv"
LEGACY_VALID_CSV_SUFFIX = "_valid_records.csv"

REJECTED_EXPORT_ERROR_COL = "linea_y_errores"
REJECTED_LEGACY_HEADER = (
    "source_row_number",
    "validation_status",
    "error_details",
    "raw_data",
)


def get_temp_dir() -> Path:
    base = Path(getattr(settings, "TEMP_PATH", None) or "temp_uploads")
    base.mkdir(parents=True, exist_ok=True)
    return base.resolve()


def valid_records_path(batch_id: str, metadata: Any = None) -> Path:
    return batch_artifact_path(batch_id, VALID_SUFFIX, metadata)


def rejected_records_path(batch_id: str, metadata: Any = None) -> Path:
    return batch_artifact_path(batch_id, REJECTED_SUFFIX, metadata)


def resolve_staging_path(stored: Optional[str]) -> Optional[Path]:
    if not stored:
        return None
    text = str(stored).strip()
    if not text:
        return None

    candidates: List[Path] = [Path(text)]
    if "\\" in text:
        candidates.append(Path(text.replace("\\", "/")))
    if "/" in text:
        candidates.append(Path(text.replace("/", "\\")))

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()

    by_name = get_temp_dir() / Path(text).name
    if by_name.is_file():
        return by_name.resolve()

    return None


def find_rejected_records_file(
    batch_id: str,
    metadata_path: Optional[str] = None,
    metadata: Any = None,
) -> Optional[Path]:
    candidates = [
        resolve_staging_path(metadata_path),
        rejected_records_path(batch_id, metadata),
    ]
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate
    return None


def find_valid_records_file(
    batch_id: str,
    metadata_path: Optional[str] = None,
    metadata: Any = None,
) -> Optional[Path]:
    work_dir = resolve_batch_work_dir(metadata) if metadata else get_temp_dir()
    candidates = [
        resolve_staging_path(metadata_path),
        valid_records_path(batch_id, metadata),
        work_dir / f"{batch_id}{LEGACY_VALID_CSV_SUFFIX}",
    ]
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate
    return None


def is_parquet_valid_file(path: Path) -> bool:
    return path.suffix.lower() == ".parquet"


class ValidRecordsParquetWriter:
    """Incremental O(n) Parquet writer for valid records (PyArrow)."""

    def __init__(
        self,
        path: Path,
        target_cols: Sequence[str],
        compression: Optional[str] = None,
    ) -> None:
        self.path = path
        self.target_cols = list(target_cols)
        self.compression = compression or getattr(settings, "PARQUET_COMPRESSION", "snappy")
        self._writer: Optional[pq.ParquetWriter] = None
        self.rows_written = 0

    def _ensure_writer(self, table: pa.Table) -> None:
        if self._writer is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._writer = pq.ParquetWriter(
                self.path,
                table.schema,
                compression=self.compression,
            )

    def write_dataframe(self, frame: pd.DataFrame) -> int:
        if frame.empty:
            return 0
        table = pa.Table.from_pandas(frame, preserve_index=False)
        self._ensure_writer(table)
        assert self._writer is not None
        self._writer.write_table(table)
        count = len(frame)
        self.rows_written += count
        return count

    def write_polars(self, df) -> int:
        if df.is_empty():
            return 0
        table = df.to_arrow()
        self._ensure_writer(table)
        assert self._writer is not None
        self._writer.write_table(table)
        count = table.num_rows
        self.rows_written += count
        return count

    def write_polars_chunk(
        self,
        df: pl.DataFrame,
        *,
        batch_id: str,
        start_row_number: int,
        target_cols: Optional[List[str]] = None,
    ) -> int:
        """Write validated Polars rows directly (no JSON roundtrip)."""
        import polars as pl

        if df.is_empty():
            return 0
        cols = target_cols or self.target_cols
        if not cols:
            cols = [c for c in df.columns if not str(c).startswith("_")]
        export = df.select([c for c in cols if c in df.columns])
        export = export.with_columns(
            pl.lit(batch_id).alias("_batch_id_"),
            pl.arange(start_row_number, start_row_number + export.height).alias(
                "_source_row_number_"
            ),
        )
        return self.write_polars(export)

    def write_passed_records(
        self,
        passed_records: List[Dict[str, Any]],
        target_cols: Optional[List[str]] = None,
    ) -> int:
        if not passed_records:
            return 0
        cols = target_cols or self.target_cols
        rows: List[Dict[str, Any]] = []
        for record in passed_records:
            processed = json.loads(record["processed_data"])
            row = {col: coalesce_empty_to_none(processed.get(col)) for col in cols}
            row["_batch_id_"] = record["batch_id"]
            row["_source_row_number_"] = record["source_row_number"]
            rows.append(row)
        return self.write_dataframe(pd.DataFrame(rows))

    def close(self) -> None:
        if self._writer is not None:
            self._writer.close()
            self._writer = None

    def __enter__(self) -> "ValidRecordsParquetWriter":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def append_valid_records_parquet(
    path: Path,
    passed_records: List[Dict[str, Any]],
    target_cols: List[str],
    writer: Optional[ValidRecordsParquetWriter] = None,
) -> int:
    """Append PASSED rows to Parquet. Uses incremental writer when provided."""
    if not passed_records:
        return 0
    if writer is not None:
        return writer.write_passed_records(passed_records, target_cols)

    with ValidRecordsParquetWriter(path, target_cols) as incremental:
        return incremental.write_passed_records(passed_records, target_cols)


def metadata_merge_expr(fragment_sql: str) -> str:
    """Merge fragment into batch_control.metadata (jsonb column)."""
    return f"COALESCE(metadata, '{{}}'::jsonb) || {fragment_sql}"


def parse_rejected_error_messages(error_details: Optional[str]) -> List[str]:
    if not error_details:
        return []
    try:
        parsed = json.loads(error_details)
        if isinstance(parsed, dict):
            errors = parsed.get("errors")
            if isinstance(errors, list):
                return [str(e) for e in errors if e]
        if isinstance(parsed, list):
            return [str(e) for e in parsed if e]
    except (json.JSONDecodeError, TypeError):
        pass
    return [str(error_details)]


def format_rejected_error_column(
    source_row_number: Any,
    error_details: Optional[str],
) -> str:
    """Single column A: line number + human-readable validation errors."""
    errors = parse_rejected_error_messages(error_details)
    line = source_row_number if source_row_number is not None else ""
    if errors:
        return f"Línea {line}: " + "; ".join(errors)
    return f"Línea {line}"


def _load_source_file_row(record: Dict[str, Any]) -> Dict[str, Any]:
    raw = record.get("source_file_data")
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        loaded = json.loads(raw)
        return loaded if isinstance(loaded, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def cell_value_for_rejected_export(val: Any) -> str:
    if is_empty_value(val):
        return ""
    return str(val).strip()


def build_rejected_export_row(
    record: Dict[str, Any],
    source_file_columns: List[str],
) -> List[str]:
    """Column A = line + errors; remaining columns = original file values."""
    source_row = _load_source_file_row(record)
    row_out = [
        format_rejected_error_column(
            record.get("source_row_number"),
            record.get("error_details"),
        )
    ]
    for col in source_file_columns:
        row_out.append(cell_value_for_rejected_export(source_row.get(col)))
    return row_out


def rejected_export_header(source_file_columns: List[str]) -> List[str]:
    return [REJECTED_EXPORT_ERROR_COL, *source_file_columns]


def append_rejected_records_csv(
    path: Path,
    failed_records: List[Dict[str, Any]],
    source_file_columns: List[str],
) -> int:
    """Append rejected rows. Column A = errors; rest = original file columns."""
    if not failed_records:
        return 0

    write_header = not path.exists() or path.stat().st_size == 0
    with open(path, "a", encoding="utf-8", newline="") as rf:
        writer = csv.writer(rf, delimiter=",", lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
        if write_header:
            writer.writerow(rejected_export_header(source_file_columns))
        for record in failed_records:
            writer.writerow(build_rejected_export_row(record, source_file_columns))
    return len(failed_records)


def _detect_storage_delimiter(header_line: str) -> str:
    if header_line.count("\t") >= header_line.count(","):
        return "\t"
    return ","


def _emit_csv_row(cells: List[str]) -> str:
    buf = io.StringIO()
    csv.writer(buf, delimiter=",", lineterminator="\n", quoting=csv.QUOTE_MINIMAL).writerow(cells)
    return buf.getvalue()


def iter_rejected_download_lines(
    path: Path,
    source_file_columns: Optional[List[str]] = None,
) -> Iterable[str]:
    """
    Stream rejected file for download (UTF-8 BOM + comma CSV for Excel).
    Converts legacy 4-column format when source_file_columns are known.
    """
    file_columns = list(source_file_columns or [])

    with open(path, "r", encoding="utf-8", newline="") as f:
        first_line = f.readline()
        if not first_line:
            return

        delimiter = _detect_storage_delimiter(first_line)
        f.seek(0)
        reader = csv.reader(f, delimiter=delimiter)
        header = next(reader, None)
        if not header:
            return

        is_legacy = tuple(header) == REJECTED_LEGACY_HEADER
        yield "\ufeff"

        if is_legacy:
            legacy_rows = list(reader)
            if not file_columns and legacy_rows:
                keys: List[str] = []
                seen: set[str] = set()
                for row in legacy_rows:
                    if len(row) < 4:
                        continue
                    try:
                        data = json.loads(row[3])
                        if isinstance(data, dict):
                            for k in data.keys():
                                if k not in seen:
                                    seen.add(k)
                                    keys.append(k)
                    except (json.JSONDecodeError, TypeError):
                        pass
                file_columns = keys

            yield _emit_csv_row(rejected_export_header(file_columns) if file_columns else [REJECTED_EXPORT_ERROR_COL, "datos"])
            for row in legacy_rows:
                if len(row) < 4:
                    continue
                record = {
                    "source_row_number": row[0],
                    "error_details": row[2] if len(row) > 2 else "",
                    "source_file_data": row[3] if len(row) > 3 else "{}",
                }
                if file_columns:
                    yield _emit_csv_row(build_rejected_export_row(record, file_columns))
                else:
                    col_a = format_rejected_error_column(row[0], row[2] if len(row) > 2 else "")
                    yield _emit_csv_row([col_a, row[3] if len(row) > 3 else ""])
            return

        if header and header[0] == REJECTED_EXPORT_ERROR_COL:
            yield _emit_csv_row(header)
            for row in reader:
                yield _emit_csv_row(row)
            return

        yield _emit_csv_row(header)
        for row in reader:
            yield _emit_csv_row(row)


def _export_columns_from_parquet_batch(columns: Sequence[str]) -> List[str]:
    export_cols = [c for c in columns if not str(c).startswith("_")]
    return list(export_cols) if export_cols else list(columns)


def iter_valid_download_lines(path: Path) -> Iterable[str]:
    """
    Stream valid records for download (UTF-8 BOM + comma CSV for Excel).
    Reads Parquet in batches or converts legacy delimited text files.
    """
    if is_parquet_valid_file(path):
        yield "\ufeff"
        pf = pq.ParquetFile(path)
        export_cols: Optional[List[str]] = None
        for batch in pf.iter_batches(batch_size=8192):
            df = batch.to_pandas()
            if export_cols is None:
                export_cols = _export_columns_from_parquet_batch(df.columns)
                yield _emit_csv_row(export_cols)
            for row in df[export_cols].itertuples(index=False, name=None):
                yield _emit_csv_row([cell_value_for_rejected_export(v) for v in row])
        if export_cols is None:
            yield _emit_csv_row([])
        return

    with open(path, "r", encoding="utf-8", newline="") as f:
        first_line = f.readline()
        if not first_line:
            return

        delimiter = _detect_storage_delimiter(first_line)
        f.seek(0)
        reader = csv.reader(f, delimiter=delimiter)
        header = next(reader, None)
        if not header:
            return

        yield "\ufeff"
        yield _emit_csv_row(header)
        for row in reader:
            yield _emit_csv_row(row)

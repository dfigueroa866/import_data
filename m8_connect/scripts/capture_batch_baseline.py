#!/usr/bin/env python3
"""Capture golden baseline snapshot for regression tests from a batch on disk / DB."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import polars as pl

from data_staging.config import settings
from data_staging.services.history.history_config import HISTORY_UNIQUE_KEYS

DEFAULT_BATCH_ID = "7cd1ffb6-71a7-48e2-80c1-f38d25667342"
FIXTURES_ROOT = ROOT / "tests" / "fixtures" / "batches"


def _short_id(batch_id: str) -> str:
    return batch_id.split("-")[0]


def _find_upload(batch_id: str, suffix: str) -> Optional[Path]:
    upload_dir = Path(settings.UPLOAD_PATH)
    matches = sorted(upload_dir.glob(f"{batch_id}*{suffix}"))
    return matches[0] if matches else None


def _group_checksum(df: pl.DataFrame) -> str:
    keys = [c for c in ["organization_id", "location_code", "sku", "period_start"] if c in df.columns]
    if not keys:
        return ""
    chk = df.group_by(keys).agg(pl.col("quantity").sum().alias("qty")).sort(keys)
    return hashlib.sha256(chk.write_csv().encode()).hexdigest()[:16]


def _load_batch_metadata(batch_id: str) -> Dict[str, Any]:
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor

        conn = psycopg2.connect(settings.DATABASE_URL)
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT batch_id, status, records_count, metadata
                    FROM staging_meta.batch_control
                    WHERE batch_id = %s
                    """,
                    (batch_id,),
                )
                row = cur.fetchone()
                if not row:
                    return {}
                meta = row.get("metadata") or {}
                if isinstance(meta, str):
                    meta = json.loads(meta)
                return {
                    "batch_id": str(row["batch_id"]),
                    "status": row.get("status"),
                    "records_count": row.get("records_count"),
                    "metadata": meta,
                }
        finally:
            conn.close()
    except Exception as exc:
        print(f"Warning: could not read batch_control ({exc})")
        return {}


def capture(batch_id: str, out_dir: Optional[Path] = None) -> Path:
    out_dir = out_dir or (FIXTURES_ROOT / _short_id(batch_id))
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = _find_upload(batch_id, "_transactions_dummy.csv")
    if not csv_path:
        csv_path = _find_upload(batch_id, ".csv")
    agg_path = _find_upload(batch_id, "_agglomerated.parquet")

    if not csv_path or not csv_path.is_file():
        raise FileNotFoundError(f"No CSV upload found for batch {batch_id}")

    raw_df = pl.read_csv(csv_path, infer_schema_length=0)
    agg_df = pl.read_parquet(agg_path) if agg_path and agg_path.is_file() else None

    shutil.copy2(csv_path, out_dir / "transactions_dummy.csv")
    if agg_path and agg_path.is_file():
        shutil.copy2(agg_path, out_dir / "aggregated.parquet")

    temp_dir = Path(settings.TEMP_PATH)
    valid_path = temp_dir / f"{batch_id}_valid_records.parquet"
    rejected_path = temp_dir / f"{batch_id}_rejected_records.tsv"
    if valid_path.is_file():
        shutil.copy2(valid_path, out_dir / "valid_records.parquet")
    if rejected_path.is_file():
        shutil.copy2(rejected_path, out_dir / "rejected_records.tsv")

    db_info = _load_batch_metadata(batch_id)
    meta = db_info.get("metadata") or {}
    processing_stats = meta.get("processing_stats") or {}
    promotion = {
        "promoted_inserted": meta.get("promoted_inserted"),
        "promoted_updated": meta.get("promoted_updated"),
        "promoted_rows": meta.get("promoted_rows"),
    }

    expected: Dict[str, Any] = {
        "batch_id": batch_id,
        "raw_rows": raw_df.height,
        "aggregated_rows": agg_df.height if agg_df is not None else None,
        "process_type": meta.get("process_type") or "Weekly",
        "unique_keys": list(HISTORY_UNIQUE_KEYS),
        "aggregation": {
            "orig_qty": float(raw_df["quantity"].cast(pl.Float64, strict=False).sum())
            if "quantity" in raw_df.columns
            else None,
            "agg_qty": float(agg_df["quantity"].sum()) if agg_df is not None else None,
            "group_checksum": _group_checksum(agg_df) if agg_df is not None else None,
        },
        "processing_stats": {
            "total_inserted": processing_stats.get("total_inserted"),
            "total_rejected": processing_stats.get("total_rejected"),
        },
        "promotion_stats": promotion,
        "process_timing_ms": meta.get("process_timing_ms"),
        "process_timing_total_ms": meta.get("process_timing_total_ms"),
        "promotion_timing_ms": meta.get("promotion_timing_ms"),
        "promotion_timing_total_ms": meta.get("promotion_timing_total_ms"),
        "valid_parquet_schema": list(agg_df.columns) if agg_df is not None else [],
        "column_mappings": meta.get("column_mappings"),
    }

    expected_path = out_dir / "expected.json"
    expected_path.write_text(json.dumps(expected, indent=2, default=str), encoding="utf-8")
    print(f"Baseline written to {expected_path}")
    return expected_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture batch golden baseline")
    parser.add_argument("--batch-id", default=DEFAULT_BATCH_ID)
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args()
    capture(args.batch_id, args.out_dir)


if __name__ == "__main__":
    main()

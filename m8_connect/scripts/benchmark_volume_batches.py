#!/usr/bin/env python3
"""Optional volume benchmarks (run after parity tests pass)."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from data_staging.config import settings


def _bench_batch(batch_prefix: str) -> dict:
    upload_dir = Path(settings.UPLOAD_PATH)
    csv_files = list(upload_dir.glob(f"{batch_prefix}*.csv"))
    if not csv_files:
        return {"batch": batch_prefix, "error": "CSV not found"}
    csv_path = csv_files[0]
    size_mb = csv_path.stat().st_size / (1024 * 1024)
    t0 = time.perf_counter()
    rows = sum(1 for _ in open(csv_path, encoding="utf-8", errors="replace")) - 1
    elapsed = time.perf_counter() - t0
    return {
        "batch": batch_prefix,
        "file_mb": round(size_mb, 2),
        "rows": rows,
        "line_count_sec": round(rows / elapsed, 0) if elapsed else 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--batches",
        nargs="*",
        default=["ac9ada25", "4439b0a3"],
        help="Batch ID prefixes for volume benchmarks",
    )
    args = parser.parse_args()
    for prefix in args.batches:
        print(_bench_batch(prefix))


if __name__ == "__main__":
    main()

"""Optional multiprocessing for chunk validation (Phase 6)."""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from typing import Callable, Iterator, List, Optional, TypeVar

import polars as pl

from data_staging.config import settings

T = TypeVar("T")


def configure_polars_threads() -> None:
    """Ensure Polars uses available CPU threads when not configured externally."""
    if "POLARS_MAX_THREADS" not in os.environ:
        cpu = os.cpu_count() or 4
        os.environ["POLARS_MAX_THREADS"] = str(cpu)


def should_use_parallel_validation(composite_unique_keys: Optional[List[str]]) -> bool:
    if not getattr(settings, "USE_VALIDATION_MULTIPROCESSING", False):
        return False
    if composite_unique_keys:
        return False
    return int(getattr(settings, "VALIDATION_WORKER_PROCESSES", 2) or 0) > 1


def parallel_map_chunks(
    chunks: Iterator[pl.DataFrame],
    worker_fn: Callable[[pl.DataFrame, int], T],
    *,
    max_workers: Optional[int] = None,
) -> Iterator[T]:
    """
    Process chunks in a process pool. worker_fn must be picklable (top-level).
    Falls back to sequential when parallel validation is disabled.
    """
    workers = max_workers or int(getattr(settings, "VALIDATION_WORKER_PROCESSES", 2))
    chunk_list = list(chunks)
    if len(chunk_list) <= 1 or workers <= 1:
        for idx, chunk in enumerate(chunk_list):
            yield worker_fn(chunk, idx)
        return

    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(worker_fn, chunk, idx) for idx, chunk in enumerate(chunk_list)
        ]
        for future in futures:
            yield future.result()

"""Sincroniza columnas de staging_meta.batch_control con metadata del wizard."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Optional, Union

PathLike = Union[str, Path]

_PROMOTED_STATUSES = frozenset({"PROMOTED", "PARTIALLY_PROMOTED"})


def normalize_metadata(metadata: Any) -> Dict[str, Any]:
    if metadata is None:
        return {}
    if isinstance(metadata, str):
        try:
            return json.loads(metadata) if metadata else {}
        except json.JSONDecodeError:
            return {}
    if isinstance(metadata, dict):
        return dict(metadata)
    return {}


def with_file_path(metadata: Dict[str, Any], file_path: Optional[PathLike]) -> Dict[str, Any]:
    """Asegura file_path en metadata JSON (además de la columna dedicada)."""
    out = dict(metadata)
    if file_path:
        out["file_path"] = str(file_path)
    return out


def resolve_effective_file_path(
    metadata: Dict[str, Any],
    *,
    file_path_column: Optional[str] = None,
) -> Optional[str]:
    """Ruta del archivo a procesar: agregado > metadata > columna file_path."""
    meta = normalize_metadata(metadata)
    for key in ("aggregated_file_path", "file_path"):
        val = meta.get(key)
        if val:
            return str(val)
    if file_path_column:
        return str(file_path_column)
    return None


def resolve_original_file_path(
    metadata: Dict[str, Any],
    *,
    file_path_column: Optional[str] = None,
) -> Optional[str]:
    """Ruta del archivo original subido (antes de cualquier agregación)."""
    meta = normalize_metadata(metadata)

    def _resolve_candidate(path_val: Path) -> Optional[str]:
        if path_val.is_file():
            return str(path_val)
        stem = re.sub(r"(_agglomerated)+$", "", path_val.stem)
        parent = path_val.parent
        for suffix in (".raw.parquet", ".parquet", ".csv"):
            candidate = parent / f"{stem}{suffix}"
            if candidate.is_file():
                return str(candidate)
        return None

    if meta.get("original_file_path"):
        resolved = _resolve_candidate(Path(str(meta["original_file_path"])))
        if resolved:
            return resolved

    for key in ("file_path", "aggregated_file_path"):
        val = meta.get(key)
        if val:
            resolved = _resolve_candidate(Path(str(val)))
            if resolved:
                return resolved

    if file_path_column:
        resolved = _resolve_candidate(Path(str(file_path_column)))
        if resolved:
            return resolved
        return str(file_path_column)

    return None


def should_preserve_upload_files(
    metadata: Any,
    *,
    batch_status: Optional[str] = None,
) -> bool:
    """True when upload artifacts must stay on disk (catalog promoted to production)."""
    meta = normalize_metadata(metadata)
    if meta.get("preserve_upload_files"):
        return True
    if meta.get("load_type") == "catalog" and batch_status in _PROMOTED_STATUSES:
        return True
    return False


def collect_batch_file_paths(
    metadata: Any,
    file_path_column: Optional[str] = None,
) -> list[str]:
    """Rutas de disco asociadas al batch (original, agregado, temporales)."""
    paths: list[str] = []
    seen: set[str] = set()

    def add(path: Optional[str]) -> None:
        if not path:
            return
        p = str(path).strip()
        if p and p not in seen:
            seen.add(p)
            paths.append(p)

    meta = normalize_metadata(metadata)
    add(file_path_column)
    add(meta.get("file_path"))
    add(meta.get("original_file_path"))
    add(meta.get("aggregated_file_path"))
    add(meta.get("valid_temp_file"))
    add(meta.get("rejected_temp_file"))
    add(meta.get("load_storage_dir"))
    return paths



def staging_table_for_source(source_name: str) -> str:
    """Nombre de tabla en staging_data (misma convención que file_processor)."""
    safe = (source_name or "unknown").lower().replace(" ", "_").replace("-", "_")
    return f"stage_{safe}"


def is_safe_sql_identifier(name: str) -> bool:
    return bool(name) and name.replace("_", "").isalnum()

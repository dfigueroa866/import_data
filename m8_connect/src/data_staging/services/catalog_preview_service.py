"""
Preview and validation for catalog uploads (skus, location).
Applies column mappings without weekly/monthly aggregation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import polars as pl

from data_staging.services.catalog.catalog_registry import get_catalog_table, load_validation_rules
from data_staging.services.catalog.catalog_transforms import (
    apply_catalog_transforms,
    check_catalog_enum_issues,
    check_not_null_row_issues,
    filter_catalog_validation_rules,
    get_active_mapped_targets,
    load_db_not_null_columns,
    load_db_system_managed_columns,
)
from data_staging.core.validators.data_validator import DataValidator
from data_staging.utils.chunk_iterators import count_csv_rows, count_parquet_rows, parquet_column_names
from data_staging.utils.json_helpers import to_json_safe
from data_staging.utils.mapping_helpers import is_wizard_virtual_mapping


class CatalogPreviewError(Exception):
    pass


def _apply_mappings(
    df: pl.DataFrame,
    column_mappings: Dict[str, Dict[str, Any]],
    column_toggles: Dict[str, bool],
) -> pl.DataFrame:
    rename_mapping = {}
    cols_to_keep: List[str] = []
    static_mappings: Dict[str, str] = {}

    for file_col, config in column_mappings.items():
        if not column_toggles.get(file_col, True):
            continue
        target = config.get("target")
        if not target:
            continue
        if is_wizard_virtual_mapping(file_col, config):
            static_mappings[target] = config.get("default_value", "")
        else:
            if file_col in df.columns:
                cols_to_keep.append(file_col)
                rename_mapping[file_col] = target

    if cols_to_keep:
        df = df.select([c for c in cols_to_keep if c in df.columns])
        df = df.rename(rename_mapping)

    for target_col, default_val in static_mappings.items():
        df = df.with_columns(pl.lit(default_val).alias(target_col))

    return df


def _df_has_column(df: pd.DataFrame, col_name: str) -> bool:
    if col_name in df.columns:
        return True
    target = str(col_name or "").lower()
    return any(str(c).lower() == target for c in df.columns)


def _check_composite_unique(
    df: pd.DataFrame,
    unique_keys: List[str],
) -> List[Dict[str, Any]]:
    """Detect duplicate composite keys within the file."""
    issues: List[Dict[str, Any]] = []
    if not unique_keys:
        return issues
    missing = [k for k in unique_keys if not _df_has_column(df, k)]
    if missing:
        issues.append({
            "rule": "composite_unique",
            "severity": "critical",
            "message": f"Columnas de clave única no mapeadas: {', '.join(missing)}",
            "column": None,
            "count": len(missing),
        })
        return issues

    resolved_keys = []
    lower_map = {str(c).lower(): c for c in df.columns}
    for key in unique_keys:
        if key in df.columns:
            resolved_keys.append(key)
        elif key.lower() in lower_map:
            resolved_keys.append(lower_map[key.lower()])

    if len(resolved_keys) != len(unique_keys):
        return issues

    subset = df[resolved_keys].copy()
    for col in resolved_keys:
        subset[col] = subset[col].astype(str).str.strip()

    dup_mask = subset.duplicated(keep=False)
    dup_count = int(dup_mask.sum())
    if dup_count > 0:
        issues.append({
            "rule": "composite_unique",
            "severity": "critical",
            "message": (
                f"Duplicados en archivo para clave ({', '.join(unique_keys)}): "
                f"{dup_count} filas afectadas"
            ),
            "column": ", ".join(unique_keys),
            "count": dup_count,
        })
    return issues


def _check_required_mapped(
    df: pd.DataFrame,
    required_columns: List[str],
) -> List[Dict[str, Any]]:
    """Ensure required catalog columns exist after mapping (case-insensitive)."""
    issues: List[Dict[str, Any]] = []
    skip = {"organization_id"}
    for col in required_columns:
        if not col or col in skip:
            continue
        if not _df_has_column(df, col):
            issues.append({
                "rule": "required_column",
                "severity": "critical",
                "message": f"Columna requerida no mapeada: {col}",
                "column": col,
                "count": 1,
            })
    return issues


def _selected_parquet_columns(path: Path, cols_to_read: List[str]) -> Optional[List[str]]:
    if not cols_to_read:
        return None
    available = set(parquet_column_names(path))
    selected = [c for c in cols_to_read if c in available]
    return selected or None


def _read_and_transform_catalog(
    file_path: str,
    target_table: str,
    column_mappings: Dict[str, Dict[str, Any]],
    column_toggles: Dict[str, bool],
    encoding: str = "utf-8",
    delimiter: str = ",",
    organization_id: Optional[str] = None,
    preview_row_limit: Optional[int] = None,
) -> Tuple[pd.DataFrame, int, Path, Dict[str, Any]]:
    """Read file, apply mappings and catalog transforms. No validation."""
    path = Path(file_path)
    if not path.exists():
        raise CatalogPreviewError(f"File not found: {file_path}")

    catalog = get_catalog_table(target_table)
    if not catalog:
        raise CatalogPreviewError(f"Unknown catalog table: {target_table}")

    from data_staging.utils.encoding_utils import detect_file_encoding, encoding_for_polars

    is_parquet = path.suffix.lower() == ".parquet" or path.name.lower().endswith(".raw.parquet")
    effective_encoding = encoding if is_parquet else detect_file_encoding(path)
    pl_encoding = encoding_for_polars(effective_encoding)

    cols_to_read = [
        fc
        for fc, cfg in column_mappings.items()
        if column_toggles.get(fc, True)
        and cfg.get("target")
        and not is_wizard_virtual_mapping(fc, cfg)
    ]

    selected_parquet = _selected_parquet_columns(path, cols_to_read) if is_parquet else None

    try:
        if is_parquet:
            read_kwargs: Dict[str, Any] = {}
            if selected_parquet:
                read_kwargs["columns"] = selected_parquet
            if preview_row_limit is not None:
                read_kwargs["n_rows"] = preview_row_limit
                total_rows = count_parquet_rows(path)
            df = pl.read_parquet(path, **read_kwargs)
            if preview_row_limit is None:
                total_rows = df.height
        elif cols_to_read:
            csv_kwargs: Dict[str, Any] = {
                "columns": cols_to_read,
                "separator": delimiter,
                "encoding": pl_encoding,
                "ignore_errors": True,
                "truncate_ragged_lines": True,
            }
            if preview_row_limit is not None:
                csv_kwargs["n_rows"] = preview_row_limit
                total_rows = count_csv_rows(path, delimiter, effective_encoding)
            df = pl.read_csv(path, **csv_kwargs)
            if preview_row_limit is None:
                total_rows = df.height
        else:
            csv_kwargs = {
                "separator": delimiter,
                "encoding": pl_encoding,
                "ignore_errors": True,
                "truncate_ragged_lines": True,
            }
            if preview_row_limit is not None:
                csv_kwargs["n_rows"] = preview_row_limit
                total_rows = count_csv_rows(path, delimiter, effective_encoding)
            df = pl.read_csv(path, **csv_kwargs)
            if preview_row_limit is None:
                total_rows = df.height
    except Exception as e:
        raise CatalogPreviewError(
            f"Failed to read {'Parquet' if is_parquet else 'CSV'}: {e}"
        ) from e

    df = _apply_mappings(df, column_mappings, column_toggles)

    pdf = _repair_string_columns(df.to_pandas())
    if organization_id:
        pdf["organization_id"] = organization_id

    mapped_targets = get_active_mapped_targets(column_mappings, column_toggles)
    pdf = apply_catalog_transforms(pdf, target_table, mapped_columns=mapped_targets)
    return pdf, total_rows, path, catalog


def _repair_string_columns(pdf: pd.DataFrame) -> pd.DataFrame:
    from data_staging.utils.encoding_utils import repair_mojibake_text

    for col in pdf.columns:
        if pdf[col].dtype == object:
            pdf[col] = pdf[col].apply(
                lambda v: repair_mojibake_text(v) if isinstance(v, str) else v
            )
    return pdf


def _build_preview_records(pdf: pd.DataFrame, preview_limit: int = 20) -> List[Dict[str, Any]]:
    if pdf.empty:
        return []
    preview_df = _repair_string_columns(pdf.head(preview_limit).copy())
    for col in preview_df.columns:
        if pd.api.types.is_datetime64_any_dtype(preview_df[col]):
            preview_df[col] = preview_df[col].astype(str)
    return preview_df.where(pd.notnull(preview_df), None).to_dict(orient="records")


def resolve_catalog_preview_target(metadata: Dict[str, Any]) -> str:
    """Catalog registry key (catalog_name) for preview / validation."""
    return str(metadata.get("catalog_name") or metadata.get("target_table") or "").strip()


def run_catalog_wizard_preview(
    file_path: str,
    metadata: Dict[str, Any],
    *,
    organization_id: Optional[str] = None,
    encoding: str = "utf-8",
    delimiter: str = ",",
    preview_limit: int = 20,
) -> Tuple[Dict[str, Any], Path]:
    """Wizard step 3: lightweight catalog preview (row sample + total count)."""
    target_table = resolve_catalog_preview_target(metadata)
    if not target_table:
        raise CatalogPreviewError("Catálogo no definido en el batch (catalog_name / target_table)")
    return process_catalog_preview_light(
        file_path=file_path,
        target_table=target_table,
        column_mappings=metadata.get("column_mappings") or {},
        column_toggles=metadata.get("column_toggles") or {},
        encoding=encoding,
        delimiter=delimiter,
        organization_id=organization_id,
        preview_limit=preview_limit,
    )


def process_catalog_preview_light(
    file_path: str,
    target_table: str,
    column_mappings: Dict[str, Dict[str, Any]],
    column_toggles: Dict[str, bool],
    encoding: str = "utf-8",
    delimiter: str = ",",
    organization_id: Optional[str] = None,
    preview_limit: int = 20,
) -> Tuple[Dict[str, Any], Path]:
    """
    Step 3: mapping preview only (no table validation).
    Reads a small row sample; total_rows comes from file metadata/count.
    Full validation runs in Step 4 via file_processor worker.
    """
    pdf, total_rows, path, _catalog = _read_and_transform_catalog(
        file_path,
        target_table,
        column_mappings,
        column_toggles,
        encoding=encoding,
        delimiter=delimiter,
        organization_id=organization_id,
        preview_row_limit=preview_limit,
    )
    preview_dicts = _build_preview_records(pdf, preview_limit)
    stats: Dict[str, Any] = {
        "load_type": "catalog",
        "preview_only": True,
        "has_error": False,
        "total_rows": total_rows,
        "preview_data": preview_dicts,
    }
    return to_json_safe(stats), path


def process_catalog_preview(
    file_path: str,
    target_table: str,
    column_mappings: Dict[str, Dict[str, Any]],
    column_toggles: Dict[str, bool],
    encoding: str = "utf-8",
    delimiter: str = ",",
    db_session=None,
    preview_limit: int = 20,
    organization_id: Optional[str] = None,
) -> Tuple[Dict[str, Any], Path]:
    """
    Full catalog validation (used outside wizard step 3 if needed).
    Map file columns, validate against catalog rules, return stats + original path.
    """
    pdf, total_rows, path, catalog = _read_and_transform_catalog(
        file_path,
        target_table,
        column_mappings,
        column_toggles,
        encoding=encoding,
        delimiter=delimiter,
        organization_id=organization_id,
    )

    db_schema = catalog.get("target_schema", "public")
    db_table = catalog.get("target_table") or target_table

    extra_issues: List[Dict[str, Any]] = []
    extra_issues.extend(_check_required_mapped(pdf, catalog["required_columns"]))
    extra_issues.extend(_check_composite_unique(pdf, catalog["unique_keys"]))

    not_null_cols = load_db_not_null_columns(
        db_session,
        db_schema,
        db_table,
    )
    extra_issues.extend(check_not_null_row_issues(pdf, not_null_cols))
    extra_issues.extend(check_catalog_enum_issues(pdf, target_table))

    system_managed = load_db_system_managed_columns(db_session, db_schema, db_table)
    validation_rules = filter_catalog_validation_rules(
        load_validation_rules(target_table),
        system_managed,
    )
    validator = DataValidator(db_session=db_session)
    val_summary = validator.validate_dataframe(
        pdf,
        rules=validation_rules,
        table_context=f"{db_schema}.{db_table}",
    )

    detailed = list(val_summary.get("detailed_issues", []))
    detailed.extend(extra_issues)

    has_critical = val_summary.get("critical_issues", 0) > 0 or any(
        i.get("severity") == "critical" for i in extra_issues
    )
    has_error = (
        not val_summary.get("passed", True)
        or has_critical
        or any(i.get("severity") in ("critical", "error") for i in extra_issues)
    )

    error_detail = None
    if has_error:
        for issue in detailed:
            if issue.get("severity") in ("critical", "error"):
                error_detail = issue.get("message")
                break
        if not error_detail:
            error_detail = "Validation failed for catalog data"

    preview_dicts = _build_preview_records(pdf, preview_limit)

    stats: Dict[str, Any] = {
        "load_type": "catalog",
        "has_error": has_error,
        "error_detail": error_detail,
        "total_rows": total_rows,
        "valid_rows": total_rows if not has_error else max(0, total_rows - val_summary.get("error_issues", 0)),
        "rejected_rows": sum(i.get("count", 0) for i in detailed if i.get("severity") in ("critical", "error")),
        "validation_passed": val_summary.get("passed", False) and not has_critical,
        "validation_score": val_summary.get("score", 0),
        "validation_grade": val_summary.get("grade", "F"),
        "critical_issues": val_summary.get("critical_issues", 0)
        + sum(1 for i in extra_issues if i.get("severity") == "critical"),
        "error_issues": val_summary.get("error_issues", 0),
        "warning_issues": val_summary.get("warning_issues", 0),
        "issues": detailed,
        "preview_data": preview_dicts,
    }

    return to_json_safe(stats), path

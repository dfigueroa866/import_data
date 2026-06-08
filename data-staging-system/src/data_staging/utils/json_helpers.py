"""Helpers to make API responses JSON-serializable (numpy/pandas types)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def to_json_safe(obj: Any) -> Any:
    """Recursively convert numpy/pandas scalars to native Python types."""
    if obj is None:
        return None
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        if np.isnan(obj):
            return None
        return float(obj)
    if isinstance(obj, np.ndarray):
        return [to_json_safe(x) for x in obj.tolist()]
    if isinstance(obj, dict):
        return {str(k): to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_json_safe(x) for x in obj]
    if isinstance(obj, str):
        return obj
    try:
        if pd.isna(obj):
            return None
    except (TypeError, ValueError):
        pass
    return str(obj)

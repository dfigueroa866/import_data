"""Helpers for wizard column mapping keys (file vs virtual/fixed columns)."""


def is_virtual_mapping_key(file_col: str) -> bool:
    """True when the key is not a real CSV column (custom/fixed values)."""
    if not file_col:
        return False
    return file_col.startswith("__custom") or file_col.startswith("__fixed_")

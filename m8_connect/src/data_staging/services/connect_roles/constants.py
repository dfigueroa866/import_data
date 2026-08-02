"""Constants for M8 Connect RBAC."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

CONNECT_ROLE_ADMIN = "admin_m8_connect"
CONNECT_ROLE_LOADER = "loader"

VALID_CONNECT_ROLES = frozenset({CONNECT_ROLE_ADMIN, CONNECT_ROLE_LOADER})

DEFAULT_LOADER_PERMISSIONS: Dict[str, Any] = {
    "menus": {
        "panel": True,
        "upload": True,
        "batches": True,
        "monitoring": False,
        "config": False,
        "incremental": False,
    },
    "upload": {
        "history": True,
        "catalogs": True,
    },
    "config": {
        "catalogs_view": False,
        "history_view": False,
        "incremental_view": False,
    },
}

ADMIN_PERMISSIONS: Dict[str, Any] = {
    "menus": {
        "panel": True,
        "upload": True,
        "batches": True,
        "monitoring": True,
        "config": True,
        "incremental": True,
    },
    "upload": {
        "history": True,
        "catalogs": True,
    },
    "config": {
        "catalogs_view": True,
        "history_view": True,
        "roles": True,
        "incremental_view": True,
    },
}


def deep_copy_permissions(permissions: Dict[str, Any]) -> Dict[str, Any]:
    return deepcopy(permissions)

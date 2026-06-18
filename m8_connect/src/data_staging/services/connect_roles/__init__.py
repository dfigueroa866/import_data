"""M8 Connect application roles (isolated from public.UserRole)."""

from data_staging.services.connect_roles.constants import (
    CONNECT_ROLE_ADMIN,
    CONNECT_ROLE_LOADER,
    DEFAULT_LOADER_PERMISSIONS,
)
from data_staging.services.connect_roles.service import (
    assign_role,
    clear_role,
    get_effective_permissions,
    get_loader_profile,
    list_users_with_roles,
    resolve_connect_role,
    update_loader_profile,
)

__all__ = [
    "CONNECT_ROLE_ADMIN",
    "CONNECT_ROLE_LOADER",
    "DEFAULT_LOADER_PERMISSIONS",
    "assign_role",
    "clear_role",
    "get_effective_permissions",
    "get_loader_profile",
    "list_users_with_roles",
    "resolve_connect_role",
    "update_loader_profile",
]

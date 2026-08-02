"""Tests for batch list organization scoping."""

from data_staging.api.v1.upload import _batch_scope_organization_id
from data_staging.schemas.auth import TokenUser
from data_staging.services.connect_roles.constants import CONNECT_ROLE_ADMIN


def _user(role: str, org_id: str = "org-1") -> TokenUser:
    return TokenUser(
        id="u1",
        email="u@test.com",
        role="user",
        organization_id=org_id,
        m8_connect_role=role,
    )


def test_admin_sees_all_batches_no_org_filter():
    admin = _user(CONNECT_ROLE_ADMIN)
    assert _batch_scope_organization_id(admin) is None


def test_loader_scoped_to_organization():
    loader = _user("loader", "org-42")
    assert _batch_scope_organization_id(loader) == "org-42"

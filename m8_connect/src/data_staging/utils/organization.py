"""Organization lookup helpers."""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def fetch_organization_name(db: Session, organization_id: str) -> Optional[str]:
    """Resolve display name from public.organizations."""
    if not organization_id:
        return None
    try:
        row = db.execute(
            text(
                """
                SELECT name
                FROM public.organizations
                WHERE id = :organization_id
                LIMIT 1
                """
            ),
            {"organization_id": organization_id},
        ).fetchone()
        return str(row[0]).strip() if row and row[0] else None
    except Exception as exc:
        logger.warning("Could not load organization name for %s: %s", organization_id, exc)
        return None

"""Layer between auth and services: pins the active AIDAA root on the request's db session.

AIDAA master data is shared inside ONE root organisation (the audited universe), and the Internal
Audit Unit normally audits that whole tree from a child org. A user usually holds AIDAA roles in a
single root, which is then derived automatically. When the same user holds AIDAA roles in several
roots (separate group companies), the caller picks the active root with `root_id` (query parameter)
or the `X-DH-Root` header, and we validate it is one of the roots the user may act in.

Root-dependent services read the chosen root via audit_setting.get_root(db, user_id).
"""
from typing import Optional
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps_auth import get_current_user
from app.services.audit_setting import ROOT_ATTR, get_accessible_roots


def resolve_root(
    root_id: Optional[UUID] = Query(default=None),
    x_dh_root: Optional[UUID] = Header(default=None, alias="X-DH-Root"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    roots = get_accessible_roots(db, current_user.user_id)
    chosen = root_id if root_id is not None else x_dh_root
    if chosen is not None:
        if not any(str(r) == str(chosen) for r in roots):
            raise HTTPException(
                status_code=403,
                detail="Access denied: no AIDAA role is held in this root organization",
            )
    elif len(roots) == 1:
        chosen = roots[0]
    if chosen is not None:
        setattr(db, ROOT_ATTR, chosen)
    return db
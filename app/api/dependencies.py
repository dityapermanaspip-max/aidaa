"""Compatibility shim: routers keep importing from here. New code imports the specific module.

deps_auth         get_current_user, require_permission, require_any_permission
deps_org          accessible orgs, org of a record, check_org_permission, assert_org_access
deps_assignment   ROLES_*, authorize_assignment, authorize_view, authorize_pic
deps_permissions  one named wrapper per permission code
services.logs     log_audit
"""
from app.api.deps_auth import get_current_user, require_permission, require_any_permission, oauth2_scheme  # noqa: F401
from app.api.deps_org import (  # noqa: F401
    _ORG_RESOURCES, get_user_accessible_org_ids, get_resource_org_id,
    check_org_permission, check_org_any_permission, assert_org_access,
)
from app.api.deps_assignment import (  # noqa: F401
    ROLES_WORK, ROLES_LEAD, ROLES_SUP, ROLES_LEAD_SUP,
    authorize_assignment, authorize_view, authorize_pic,
)
from app.api.deps_permissions import *  # noqa: F401,F403
from app.services.logs import log_audit  # noqa: F401
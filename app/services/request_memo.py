"""Request-scoped memoisation for read-only authorisation answers.

AIDAA asks the same IAM questions several times per request: the callable orgs
for one permission, the caller's global roles, the caller's roots. AIDAA never
writes IAM tables, so those answers cannot change inside one request. They are
cached on the request's SQLAlchemy Session (``Session.info``); get_db creates a
new Session per request and closes it afterwards, so the cache dies with the
request and never crosses users.

Only IAM-derived answers belong here. Assignment, team and plan rows are written
by this app inside the same request, so services keep reading those fresh.

``None`` is a real answer ("this permission applies to every organisation"), so
lookups use key presence, not truthiness, when deciding whether to load.
"""

from typing import Callable, Hashable, TypeVar

from sqlalchemy.orm import Session

_MEMO_KEY = "_aidaa_auth_memo"

T = TypeVar("T")


def memo(db: Session, key: Hashable, load: Callable[[], T]) -> T:
    """Return the value cached under ``key`` for this request, loading once."""
    cache = db.info.setdefault(_MEMO_KEY, {})
    if key not in cache:
        cache[key] = load()
    return cache[key]

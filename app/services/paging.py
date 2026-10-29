"""Shared list pagination.

The upscale audit found list endpoints serialising whole tables (every auditor,
every assignment) with no LIMIT. A cross-record list now takes the same two
query parameters, and the service appends ``LIMIT :lim OFFSET :off``:

    limit: Optional[int] = None, offset: int = 0
    ...
    **page(limit, offset)

Routers declare the same parameters with FastAPI bounds, so the contract does
not depend on the clamp here. The response stays a plain array: callers detect
another page from ``len(rows) == limit``.

Reference lists (locations, units, audit types, org options) feed dropdowns and
are read whole on purpose, so they get a much wider default; they are still
bounded, so a runaway master table cannot serialise itself into memory.

Defaults sit at the cap on purpose. The frontend has no pager yet, and silently
dropping rows a screen expects would be a regression, so a normal org (under
200 auditors) sees exactly what it saw before. Lower ``DEFAULT_LIMIT`` to 50 in
one line once the pager ships (owner decision 2026-10-29).
"""

from typing import Optional

DEFAULT_LIMIT = 200
MAX_LIMIT = 200

REFERENCE_DEFAULT_LIMIT = 1000
REFERENCE_MAX_LIMIT = 2000


def page(limit: Optional[int] = None, offset: Optional[int] = None, *,
         default: int = DEFAULT_LIMIT, maximum: int = MAX_LIMIT) -> dict:
    """Clamp one page request and return the SQL bind parameters."""
    size = default if limit is None else max(1, min(int(limit), maximum))
    return {"lim": size, "off": max(0, int(offset or 0))}


def reference_page(limit: Optional[int] = None, offset: Optional[int] = None) -> dict:
    """Wide page for master data that dropdowns read whole."""
    return page(limit, offset, default=REFERENCE_DEFAULT_LIMIT, maximum=REFERENCE_MAX_LIMIT)

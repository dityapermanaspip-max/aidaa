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

Defaults sit at the cap on purpose. The frontend now always sends an explicit
limit (2026-11-13: the Auditor and Surat Tugas screens page, pickers read 200-row
pages until a short one), but an older deployed frontend does not, and silently
dropping rows it expects would be a regression. Lower ``DEFAULT_LIMIT`` to 50 in
one line once the new frontend is deployed (owner decision 2026-10-29).
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

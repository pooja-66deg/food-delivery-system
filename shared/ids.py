"""Bounded integer types for anything a caller supplies.

Every service types its ids as a bare ``int``. Python's ``int`` is unbounded and
Pydantic will not narrow it, so ``2147483648`` validates, reaches asyncpg, and
raises while encoding an ``int4`` bind parameter — an unhandled 500 on nine
endpoint families across six services, reachable unauthenticated on restaurant
detail and review listing. The boundary was exact and the contrast damning:
``2147483647`` returned a clean 404, one more returned a stack trace.

Two things follow, and both matter:

- The bound belongs at the edge, not at the query. A value that cannot identify
  a row is a *request* problem, and saying so costs one annotation. The
  DBAPIError handler in shared/errors.py is the net underneath, not the fix.
- The bound has to be the column's, not a guess. These constants are the
  Postgres limits the models actually use, so widening a column is what changes
  them — nothing else should.

Pagination is here for the same reason: ``?limit=-1`` reached ``LIMIT -1`` and
Postgres refused it, which is a 422 the route could have answered itself.

Usage — annotate, don't re-derive::

    from shared.ids import EntityId, Limit, Offset

    @router.get("/orders/{order_id}")
    async def get_order(order_id: EntityId): ...

    @router.get("/payments")
    async def history(limit: Limit = 20, offset: Offset = 0): ...

For ids inside a request *body*, use ``BodyId`` — a path/query annotation
carries FastAPI location metadata that a Pydantic model field must not.
"""

from typing import Annotated

from fastapi import Path, Query
from pydantic import Field

#: Postgres ``integer``. Every primary key in this platform is one of these.
INT32_MAX = 2_147_483_647

#: Postgres ``bigint``, for the few columns that are one — and for OFFSET, which
#: Postgres takes as bigint, so the int32 bound would reject values it accepts.
INT64_MAX = 9_223_372_036_854_775_807

#: An id in the path. ``ge=1`` because these are all identity sequences: zero and
#: negatives cannot exist, so 422 is more honest than a 404 for a row that could
#: never have been there.
EntityId = Annotated[int, Path(ge=1, le=INT32_MAX)]

#: An id in a query string — ``?ids=1,2`` style lookups parse their own list, so
#: this is for single-value params.
QueryId = Annotated[int, Query(ge=1, le=INT32_MAX)]

#: An id in a request body, for Pydantic model fields.
BodyId = Annotated[int, Field(ge=1, le=INT32_MAX)]

#: Page size. Capped so a caller cannot ask for the whole table, and floored at 1
#: because ``LIMIT 0`` is a request for nothing that looks like an empty result.
Limit = Annotated[int, Query(ge=1, le=100)]

#: Page offset. Bounded by bigint, matching what Postgres will accept.
Offset = Annotated[int, Query(ge=0, le=INT64_MAX)]


def clamp_id(value: int | None) -> int | None:
    """``value`` if it could identify a row, else None.

    For internal endpoints that take a comma-separated list of ids and should
    skip the impossible ones rather than fail the whole batch — one unusable id
    in ``?ids=1,2147483648`` should not cost the caller the other results.
    """
    if value is None or value < 1 or value > INT32_MAX:
        return None
    return value

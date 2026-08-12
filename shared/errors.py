"""The error contract, shared by every service.

Not shared for convenience — shared because it is a contract. The frontend
handles a 409 from the users service and a 409 from the orders service with the
same code, and once those are separate deployments the only thing keeping their
error shapes identical is that they are generated from here.

Mirrors ``src/core/exceptions.py`` so a router moving out of the monolith keeps
raising exactly what it raised before. Imports nothing but FastAPI, because it is
copied into each service image as ``shared/``.
"""

from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# SQLAlchemy is present in every service image, but this module is also imported
# by things that only need the exception types (the gateway, tooling), and the
# stated rule for shared/ is that it drags nothing in. A guarded import keeps
# both true: the driver-level handler installs when there is a driver to fail.
# Registered on DBAPIError, not DatabaseError: SQLAlchemy only narrows to a
# subclass when the dialect maps the driver's error, and asyncpg's do not all map
# — the tracebacks in production read `sqlalchemy.exc.DBAPIError`, so anything
# registered lower down never fires.
try:
    from sqlalchemy.exc import DBAPIError as _DBAPIError
except ImportError:                             # pragma: no cover
    _DBAPIError = None  # type: ignore[assignment]


class AppException(Exception):
    """Base application exception."""

    def __init__(
        self, message: str, status_code: int = 400, details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class ValidationException(AppException):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status.HTTP_422_UNPROCESSABLE_ENTITY, details)


class UnauthorizedException(AppException):
    def __init__(self, message: str = "Unauthorized"):
        super().__init__(message, status.HTTP_401_UNAUTHORIZED)


class ForbiddenException(AppException):
    def __init__(self, message: str = "Forbidden"):
        super().__init__(message, status.HTTP_403_FORBIDDEN)


class NotFoundException(AppException):
    def __init__(self, resource: str, identifier: str):
        super().__init__(
            f"{resource} with ID {identifier} not found", status.HTTP_404_NOT_FOUND
        )


class ConflictException(AppException):
    def __init__(self, message: str):
        super().__init__(message, status.HTTP_409_CONFLICT)


class TooManyRequestsException(AppException):
    def __init__(self, message: str = "Too many requests"):
        super().__init__(message, status.HTTP_429_TOO_MANY_REQUESTS)


class ServiceUnavailableException(AppException):
    """A dependency this request genuinely could not proceed without.

    New in the split, and worth its own type. It means "we could not answer,
    try again" — distinct from a 4xx, which means "we answered, and the answer
    is no". Retrying a 409 is pointless; retrying this is exactly right, and the
    frontend can only tell them apart if the status code does.
    """

    def __init__(self, message: str = "A required service is unavailable"):
        super().__init__(message, status.HTTP_503_SERVICE_UNAVAILABLE)


#: Largest value a Postgres ``integer`` column holds. Python ints are unbounded
#: and Pydantic will not narrow them on its own, so anything typed as a bare
#: ``int`` and handed to a query against an int4 column is a 500 waiting for a
#: caller to type one more digit. See INT32 note in shared/ids.py.
_INT32_MAX = 2_147_483_647


def _finite(value: Any) -> Any:
    """``value`` with non-finite floats replaced by their spelling.

    ``json.dumps`` is called with ``allow_nan=False`` by Starlette, so an ``inf``
    or ``nan`` anywhere in a response body raises *while rendering the response*.
    FastAPI's own validation handler echoes the offending input back, which is
    exactly where those values live — so a 422 about a non-finite float became a
    500 about serialising one, and the client learned nothing.
    """
    if isinstance(value, float):
        if value != value:                      # NaN, which is not equal to itself
            return "NaN"
        if value in (float("inf"), float("-inf")):
            return "Infinity" if value > 0 else "-Infinity"
        return value
    if isinstance(value, dict):
        return {k: _finite(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_finite(v) for v in value]
    return value


def install_error_handlers(app: FastAPI) -> None:
    """Render AppExceptions as the same JSON body in every service."""

    @app.exception_handler(AppException)
    async def _handle(request: Request, exc: AppException) -> JSONResponse:
        body: Dict[str, Any] = {"detail": exc.message}
        if exc.details:
            body["details"] = exc.details
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """FastAPI's 422, but one that can always be serialised.

        Only differs from the default in passing the errors through ``_finite``.
        Without it the framework's own handler is the thing that crashes.
        """
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": _finite(jsonable_encoder(exc.errors()))},
        )

    if _DBAPIError is None:                     # SQLAlchemy absent: nothing to catch
        return

    @app.exception_handler(_DBAPIError)
    async def _handle_dbapi(request: Request, exc: Any) -> JSONResponse:
        """A driver-level failure as an answer rather than a stack trace.

        Three distinct faults arrive here and conflating them is how all three
        stayed unhandled: SQLAlchemy's own class does not reliably say which one
        it is, so the driver's exception underneath is what gets asked.

        **Out of range / malformed value** — an id past int32, a negative LIMIT.
        Raised while *binding parameters*, before anything reaches the wire, so
        nothing was written and the pool is unharmed. A client error: 422. The
        bounded types in shared/ids.py stop it being reached at all; this is the
        backstop for whatever they miss.

        **Constraint violation** — a null in a NOT NULL column, a duplicate key.
        Also the caller's doing. Unique collisions are 409, the rest 422.

        **Cannot reach the database** — connection slots exhausted, proxy
        refused. Not the caller's fault and worth retrying, which a 503 says and
        a 500 does not. This had been surfacing as an unhandled 500 out of
        checkout whenever the pool ran dry.

        Anything else is re-raised: a genuine server fault should stay a 500 and
        keep its traceback rather than be dressed up as a client error.
        """
        orig = getattr(exc, "orig", None)
        name = type(orig).__name__ if orig is not None else ""

        if isinstance(orig, (OSError, ConnectionError)) or name in {
            "TooManyConnectionsError", "ConnectionDoesNotExistError",
            "CannotConnectNowError", "ConnectionFailureError", "TimeoutError",
        }:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"detail": "The database is unavailable. Please retry."},
            )

        if name == "UniqueViolationError":
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={"detail": "That value is already taken."},
            )

        if name in {
            "DataError", "NumericValueOutOfRangeError", "InvalidTextRepresentationError",
            "InvalidRowCountInLimitClauseError", "InvalidRowCountInResultOffsetClauseError",
            "NotNullViolationError", "CheckViolationError", "ForeignKeyViolationError",
            "StringDataRightTruncationError", "InvalidDatetimeFormatError",
        } or isinstance(orig, (ValueError, OverflowError)):
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content={"detail": "A value in this request is not valid for this field."},
            )

        raise exc

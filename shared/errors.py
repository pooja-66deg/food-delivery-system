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
from fastapi.responses import JSONResponse


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


def install_error_handlers(app: FastAPI) -> None:
    """Render AppExceptions as the same JSON body in every service."""

    @app.exception_handler(AppException)
    async def _handle(request: Request, exc: AppException) -> JSONResponse:
        body: Dict[str, Any] = {"detail": exc.message}
        if exc.details:
            body["details"] = exc.details
        return JSONResponse(status_code=exc.status_code, content=body)

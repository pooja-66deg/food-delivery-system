"""Core utilities and exceptions."""

from typing import Any, Dict
from fastapi import status


class AppException(Exception):
    """Base application exception."""

    def __init__(self, message: str, status_code: int = 400, details: Dict[str, Any] = None):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class ValidationException(AppException):
    """Validation error exception."""

    def __init__(self, message: str, details: Dict[str, Any] = None):
        super().__init__(message, status.HTTP_422_UNPROCESSABLE_ENTITY, details)


class UnauthorizedException(AppException):
    """Unauthorized access exception."""

    def __init__(self, message: str = "Unauthorized"):
        super().__init__(message, status.HTTP_401_UNAUTHORIZED)


class ForbiddenException(AppException):
    """Forbidden access exception."""

    def __init__(self, message: str = "Forbidden"):
        super().__init__(message, status.HTTP_403_FORBIDDEN)


class NotFoundException(AppException):
    """Resource not found exception."""

    def __init__(self, resource: str, identifier: str):
        message = f"{resource} with ID {identifier} not found"
        super().__init__(message, status.HTTP_404_NOT_FOUND)


class ConflictException(AppException):
    """Conflict exception."""

    def __init__(self, message: str):
        super().__init__(message, status.HTTP_409_CONFLICT)


class TooManyRequestsException(AppException):
    """Rate-limit exceeded exception."""

    def __init__(self, message: str = "Too many requests"):
        super().__init__(message, status.HTTP_429_TOO_MANY_REQUESTS)

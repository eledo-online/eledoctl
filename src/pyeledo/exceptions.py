"""Exception hierarchy for pyeledo."""

from __future__ import annotations


class EledoError(Exception):
    """Base exception for all pyeledo errors."""


class EledoAuthenticationError(EledoError):
    """Raised when authentication or token validation fails."""


class EledoApiError(EledoError):
    """Raised when Eledo returns a structured API error."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class EledoInvalidResponseError(EledoError):
    """Raised when Eledo returns an unexpected response shape or media type."""

"""Exception hierarchy for pyeledo."""


class EledoError(Exception):
    """Base exception for all pyeledo errors."""


class EledoAuthError(EledoError):
    """Raised when authentication or token validation fails."""


class EledoApiError(EledoError):
    """Raised when Eledo API returns an error response."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code

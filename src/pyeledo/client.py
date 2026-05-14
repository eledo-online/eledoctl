"""Async Eledo REST API client."""

from __future__ import annotations

from types import TracebackType
from typing import Any, Self

import httpx

from pyeledo.exceptions import EledoApiError, EledoAuthError


class EledoClient:
    """Async-native Eledo REST API client.

    The client intentionally exposes only asynchronous methods. A synchronous wrapper
    can be added later if a real requirement appears and maintenance is justified.
    """

    def __init__(self, *, base_url: str, token: str | None = None, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> Self:
        await self.open()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()

    async def open(self) -> None:
        """Open the underlying HTTP client."""
        if self._client is None:
            headers = {}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"

            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=self.timeout,
            )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Perform an authenticated API request."""
        if self._client is None:
            await self.open()

        assert self._client is not None
        response = await self._client.request(method, path, **kwargs)

        if response.status_code == 401:
            raise EledoAuthError("Eledo authentication failed.")

        if response.status_code >= 400:
            raise EledoApiError(
                f"Eledo API request failed with status {response.status_code}.",
                status_code=response.status_code,
            )

        return response

    async def get_json(self, path: str, **kwargs: Any) -> dict[str, Any] | list[Any]:
        """Perform GET request and decode JSON response."""
        response = await self.request("GET", path, **kwargs)
        return response.json()

    async def post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any] | list[Any]:
        """Perform POST request with JSON payload and decode JSON response."""
        response = await self.request("POST", path, json=payload)
        return response.json()

    async def validate_token(self) -> bool:
        """Validate current token against Eledo.

        Endpoint is provisional until Eledo exposes the final authentication API.
        """
        await self.get_json("/me")
        return True

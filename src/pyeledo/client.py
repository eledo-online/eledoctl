"""Async Eledo REST API client."""

from __future__ import annotations

from types import TracebackType
from typing import Any, Self

import httpx

from pyeledo.exceptions import (
    EledoApiError,
    EledoAuthenticationError,
    EledoInvalidResponseError,
)
from pyeledo.generate import GeneratedPdf, build_generate_payload, parse_generate_response
from pyeledo.profile import Profile, parse_profile_response
from pyeledo.schema import parse_schema_response, schema_path
from pyeledo.templates import TemplateList, TemplateScope, parse_template_list_response
from pyeledo.types import JsonObject
from pyeledo.utils import api_path, extract_error_message, response_json_object

DEFAULT_BASE_URL = "https://eledo.online"


class EledoClient:
    """Async-native Eledo REST API client.

    The client never stores credentials. Tokens are provided by callers and attached
    to requests as the Eledo ``Api-Key`` header.
    """

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        token: str = "",
        timeout: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._transport = transport

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
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"Api-Key": self.token} if self.token else {},
                timeout=self.timeout,
                transport=self._transport,
            )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Perform an Eledo API request."""
        if self._client is None:
            await self.open()
        assert self._client is not None

        response = await self._client.request(method, path, **kwargs)
        if response.status_code == 401:
            raise EledoAuthenticationError("Eledo authentication failed.")
        if response.status_code >= 400:
            self._raise_response_error(response)
        return response

    async def get_json(self, path: str, **kwargs: Any) -> JsonObject:
        """Perform GET request and decode a JSON object response."""
        response = await self.request("GET", path, **kwargs)
        return response_json_object(response)

    async def post_json(self, path: str, payload: JsonObject) -> JsonObject:
        """Perform POST request and decode a JSON object response."""
        response = await self.request("POST", path, json=payload)
        return response_json_object(response)

    @staticmethod
    def _raise_response_error(response: httpx.Response) -> None:
        content_type = response.headers.get("content-type", "").lower()
        if "application/json" in content_type:
            try:
                data = response_json_object(response)
            except EledoInvalidResponseError:
                data = {}
            raise EledoApiError(extract_error_message(data), status_code=response.status_code)
        raise EledoApiError(
            f"Eledo API request failed with status {response.status_code}.",
            status_code=response.status_code,
        )

    async def get_profile(self) -> Profile:
        """Fetch profile for the current token.

        This method also acts as token validation for CLI callers.
        """
        data = await self.get_json(api_path("/Profile"))
        return parse_profile_response(data)

    async def get_templates(
        self,
        *,
        scope: TemplateScope = TemplateScope.PRIVATE,
    ) -> TemplateList:
        """Fetch Eledo templates for a semantic scope."""
        data = await self.get_json(api_path("/List"), params={"scope": scope.value})
        return parse_template_list_response(data)

    async def get_schema(
        self,
        template_id: str,
        template_version: int | None = None,
    ) -> JsonObject:
        """Fetch the native Eledo schema for a template."""
        data = await self.get_json(schema_path(template_id, template_version))
        return parse_schema_response(data)

    async def generate_pdf(
        self,
        *,
        template_id: str,
        file_data: JsonObject | None = None,
        template_version: int | None = None,
    ) -> GeneratedPdf:
        """Generate a PDF using the primary Eledo /Generate endpoint."""
        payload = build_generate_payload(
            template_id=template_id,
            file_data=file_data,
            template_version=template_version,
        )
        response = await self.request("POST", api_path("/Generate"), json=payload)
        return parse_generate_response(response)

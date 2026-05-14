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
from pyeledo.models import (
    EledoSchema,
    GeneratedPdf,
    JsonObject,
    Profile,
    Template,
    TemplateList,
    TemplateScope,
)
from pyeledo.schema import parse_schema_response
from pyeledo.utils import api_path, extract_filename, quote_path_part

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
        return self._response_json_object(response)

    async def post_json(self, path: str, payload: JsonObject) -> JsonObject:
        """Perform POST request and decode a JSON object response."""
        response = await self.request("POST", path, json=payload)
        return self._response_json_object(response)

    async def get_profile(self) -> Profile:
        """Fetch profile for the current token.

        This method also acts as token validation for CLI callers.
        """
        data = await self.get_json(api_path("/Profile"))
        account = data.get("account")
        if not isinstance(account, str):
            raise EledoInvalidResponseError("Invalid response from Eledo API: expected account.")
        return Profile(account=account)

    async def get_templates(self, *, scope: TemplateScope = TemplateScope.PRIVATE) -> TemplateList:
        """Fetch Eledo templates for a semantic scope."""
        data = await self.get_json(api_path("/List"), params={"scope": scope.value})
        return self._parse_template_list(data)

    async def get_schema(
        self,
        template_id: str,
        template_version: int | None = None,
    ) -> EledoSchema:
        """Fetch the native Eledo schema for a template."""
        safe_id = quote_path_part(template_id)
        if template_version is None:
            path = api_path(f"/Schema/{safe_id}")
        else:
            if template_version <= 0:
                raise ValueError("template_version must be greater than zero.")
            path = api_path(f"/Schema/{safe_id}/{quote_path_part(template_version)}")
        return parse_schema_response(await self.get_json(path))

    async def generate_pdf(
        self,
        *,
        template_id: str,
        file_data: JsonObject | None = None,
        template_version: int | None = None,
    ) -> GeneratedPdf:
        """Generate a PDF using the primary Eledo /Generate endpoint."""
        if not template_id:
            raise ValueError("template_id is required.")
        if template_version is not None and template_version <= 0:
            raise ValueError("template_version must be greater than zero.")

        payload: JsonObject = {"templateId": template_id, "file": file_data}
        if template_version is not None:
            payload["templateVersion"] = template_version

        response = await self.request("POST", api_path("/Generate"), json=payload)
        content_type = response.headers.get("content-type", "").lower()
        if "application/pdf" in content_type:
            filename = extract_filename(response.headers.get("content-disposition")) or "document.pdf"
            return GeneratedPdf(
                content=response.content,
                filename=filename,
                mime_type="application/pdf",
            )
        if "application/json" in content_type:
            data = self._response_json_object(response)
            message = self._extract_error_message(data)
            raise EledoApiError(message, status_code=response.status_code)
        raise EledoInvalidResponseError(
            f"Invalid response from Eledo API: expected PDF or JSON error, got {content_type!r}."
        )

    def _response_json_object(self, response: httpx.Response) -> JsonObject:
        try:
            data = response.json()
        except ValueError as exc:
            raise EledoInvalidResponseError("Invalid JSON response from Eledo API.") from exc
        if not isinstance(data, dict):
            raise EledoInvalidResponseError("Invalid response from Eledo API: expected JSON object.")
        return data

    def _raise_response_error(self, response: httpx.Response) -> None:
        content_type = response.headers.get("content-type", "").lower()
        if "application/json" in content_type:
            try:
                data = self._response_json_object(response)
            except EledoInvalidResponseError:
                data = {}
            raise EledoApiError(self._extract_error_message(data), status_code=response.status_code)
        raise EledoApiError(
            f"Eledo API request failed with status {response.status_code}.",
            status_code=response.status_code,
        )

    def _extract_error_message(self, data: JsonObject) -> str:
        error = data.get("error") or data.get("message")
        return error if isinstance(error, str) and error else "Eledo API request failed."

    def _parse_template_list(self, data: JsonObject) -> TemplateList:
        raw_templates = data.get("templates")
        if not isinstance(raw_templates, list):
            raise EledoInvalidResponseError("Invalid response from Eledo API: expected templates array.")
        templates: list[Template] = []
        for raw_template in raw_templates:
            if not isinstance(raw_template, dict):
                raise EledoInvalidResponseError("Invalid template item from Eledo API.")
            name = raw_template.get("name")
            if not isinstance(name, str):
                raise EledoInvalidResponseError("Invalid template item from Eledo API: expected name.")
            templates.append(
                Template(
                    id=raw_template.get("id") if isinstance(raw_template.get("id"), str) else None,
                    date=raw_template.get("date") if isinstance(raw_template.get("date"), int) else None,
                    name=name,
                    thumbnail_url=raw_template.get("thumbnailUrl")
                    if isinstance(raw_template.get("thumbnailUrl"), str)
                    else None,
                    type=raw_template.get("type") if isinstance(raw_template.get("type"), int) else None,
                    version=raw_template.get("version")
                    if isinstance(raw_template.get("version"), int)
                    else None,
                    bulk=raw_template.get("bulk") if isinstance(raw_template.get("bulk"), bool) else None,
                )
            )
        total = data.get("total") if isinstance(data.get("total"), int) else None
        return TemplateList(total=total, templates=templates)

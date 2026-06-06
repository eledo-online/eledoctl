"""Small reusable helpers for pyeledo."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any, TypeGuard
from urllib.parse import quote, unquote

import httpx

from pyeledo.exceptions import EledoError, EledoInvalidResponseError
from pyeledo.types import JsonObject, JsonValue

_FILENAME_RE = re.compile(r"filename\*?=(?:UTF-8\'\'|\")?([^\";\n]+)\"?", re.IGNORECASE)


def api_path(path: str) -> str:
    """Normalize an API path under Eledo RESTv1."""
    clean = path if path.startswith("/") else f"/{path}"
    return f"/api/RESTv1{clean}"


def quote_path_part(value: str | int) -> str:
    """Quote a single URL path segment."""
    return quote(str(value), safe="")


def extract_filename(content_disposition: str | None) -> str | None:
    """Extract a filename from a Content-Disposition header.

    Supports both ``filename=`` and RFC 5987-style ``filename*=UTF-8''`` forms.
    The function is intentionally best-effort and non-throwing.
    """
    if not content_disposition:
        return None
    match = _FILENAME_RE.search(content_disposition)
    if not match:
        return None
    raw = match.group(1)
    try:
        return unquote(raw)
    except EledoError:
        return raw


def is_json_object(value: JsonValue) -> TypeGuard[JsonObject]:
    """Return true when value is a JSON object."""
    return isinstance(value, dict)


def parse_json_object(text: str) -> JsonObject:
    """Parse text as a JSON object.

    Empty text is treated as an empty object. Arrays and scalar values are rejected.
    """
    stripped = text.strip()

    if stripped == "":
        return {}

    try:
        parsed: JsonValue = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise EledoInvalidResponseError("Invalid JSON payload.") from exc

    if not isinstance(parsed, dict):
        raise EledoInvalidResponseError("JSON payload must be an object.")

    return parsed


def ensure_mapping(value: object, *, message: str) -> Mapping[str, Any]:
    """Ensure an external value is a mapping."""
    if not isinstance(value, Mapping):
        raise EledoInvalidResponseError(message)
    return value


def extract_error_message(data: JsonObject) -> str:
    """Extract a human-readable error message from an Eledo API response."""
    error = data.get("error") or data.get("message")
    return error if isinstance(error, str) and error else "Eledo API request failed."


def response_json_object(response: httpx.Response) -> JsonObject:
    """Decode an HTTP response and validate that it contains a JSON object."""
    try:
        data = response.json()
    except ValueError as exc:
        raise EledoInvalidResponseError("Invalid JSON response from Eledo API.") from exc
    if not isinstance(data, dict):
        raise EledoInvalidResponseError("Invalid response from Eledo API: expected JSON object.")
    return data

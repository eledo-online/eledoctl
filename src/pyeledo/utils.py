"""Small reusable helpers for pyeledo."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote, unquote

from pyeledo.exceptions import EledoInvalidResponseError

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
    except Exception:
        return raw


def is_json_object(value: object) -> bool:
    """Return true when value is a JSON object shape."""
    return isinstance(value, dict)


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse text as a JSON object.

    Empty text is treated as an empty object. Arrays and scalar values are rejected.
    """
    stripped = text.strip()
    if stripped == "":
        return {}
    try:
        parsed = json.loads(stripped)
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

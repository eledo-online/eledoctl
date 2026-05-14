"""Typed models used by pyeledo."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class TemplateScope(StrEnum):
    """Semantic template scopes exposed by pyeledo.

    Values intentionally mirror the underlying Eledo API values so the enum can be
    passed directly to query serialization, while the enum names remain Pythonic.
    """

    PRIVATE = "Mine"
    PUBLIC = "Public"


class PrimitiveType(StrEnum):
    """Primitive field types used by the native Eledo schema."""

    STRING = "String"
    NUMBER = "Number"
    BOOLEAN = "Boolean"
    DATE = "Date"


JsonObject = dict[str, Any]


@dataclass(frozen=True, slots=True)
class Profile:
    """Authenticated Eledo profile."""

    account: str


@dataclass(frozen=True, slots=True)
class Template:
    """Eledo template list item."""

    id: str | None
    date: int | None
    name: str
    thumbnail_url: str | None
    type: int | None
    version: int | None
    bulk: bool | None


@dataclass(frozen=True, slots=True)
class TemplateList:
    """Response returned by the template list endpoint."""

    total: int | None
    templates: list[Template]


@dataclass(frozen=True, slots=True)
class EledoSchema:
    """Native Eledo schema response."""

    schema: JsonObject


@dataclass(frozen=True, slots=True)
class PrimitiveField:
    """Top-level primitive field extracted from an Eledo schema."""

    key: str
    type: PrimitiveType


@dataclass(frozen=True, slots=True)
class GeneratedPdf:
    """Generated PDF returned by Eledo."""

    content: bytes
    filename: str = "document.pdf"
    mime_type: str = "application/pdf"

    def as_bytes(self) -> bytes:
        """Return the raw PDF bytes.

        Raw bytes are the primary representation because the Eledo Generate
        endpoint returns binary PDF data on success.
        """
        return self.content

    def as_base64(self) -> str:
        """Return the PDF content as a base64-encoded string."""
        return base64.b64encode(self.content).decode("ascii")

    def as_json(self) -> JsonObject:
        """Return a JSON-serializable payload with metadata and base64 content.

        This is a presentation helper for CLI/integration layers. It does not
        change the primary in-memory representation, which remains raw bytes.
        """
        return {
            "filename": self.filename,
            "mimeType": self.mime_type,
            "data": self.as_base64(),
        }

    def as_base64_payload(self) -> JsonObject:
        """Return JSON metadata with base64 content.

        Backwards-compatible alias for :meth:`as_json`.
        """
        return self.as_json()

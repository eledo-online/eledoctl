"""Helpers for native Eledo schemas."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from pyeledo.exceptions import EledoInvalidResponseError
from pyeledo.types import JsonObject, JsonValue
from pyeledo.utils import api_path, quote_path_part


class PrimitiveType(StrEnum):
    """Primitive field types used by the native Eledo schema."""

    STRING = "String"
    NUMBER = "Number"
    BOOLEAN = "Boolean"
    DATE = "Date"


@dataclass(frozen=True, slots=True)
class PrimitiveField:
    """Top-level primitive field extracted from an Eledo schema."""

    key: str
    type: PrimitiveType


def schema_path(template_id: str, template_version: int | None = None) -> str:
    """Build the Eledo schema endpoint path for a template."""
    safe_id = quote_path_part(template_id)

    if template_version is None:
        return api_path(f"/Schema/{safe_id}")

    if template_version <= 0:
        raise ValueError("template_version must be greater than zero.")

    return api_path(f"/Schema/{safe_id}/{quote_path_part(template_version)}")


def parse_schema_response(value: JsonValue) -> JsonObject:
    """Parse a native Eledo schema response."""
    if not isinstance(value, dict) or "schema" not in value:
        raise EledoInvalidResponseError("Invalid response from Eledo API: expected schema.")

    schema = value["schema"]

    if not isinstance(schema, dict):
        raise EledoInvalidResponseError("Invalid response from Eledo API: expected schema object.")

    return schema


def pick_primitive_fields(
    schema: JsonObject,
    allowed: Iterable[PrimitiveType] | None = None,
) -> list[PrimitiveField]:
    """Extract top-level primitive fields from a native Eledo schema.

    Only fields matching the allowed primitive types are returned. Nested
    objects, arrays, and unsupported field types are ignored.
    """
    allowed_set = set(allowed or PrimitiveType)

    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return []

    fields: list[PrimitiveField] = []

    for key, definition in properties.items():
        if not isinstance(key, str) or not isinstance(definition, dict):
            continue

        raw_type: JsonValue | None = definition.get("type")

        if not isinstance(raw_type, str):
            continue

        try:
            field_type = PrimitiveType(raw_type)
        except ValueError:
            continue

        if field_type in allowed_set:
            fields.append(PrimitiveField(key=key, type=field_type))

    return fields

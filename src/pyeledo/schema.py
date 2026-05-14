"""Helpers for native Eledo schemas."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pyeledo.models import EledoSchema, PrimitiveField, PrimitiveType


def parse_schema_response(value: object) -> EledoSchema:
    """Parse a native Eledo schema response."""
    if not isinstance(value, dict) or "schema" not in value:
        from pyeledo.exceptions import EledoInvalidResponseError

        raise EledoInvalidResponseError("Invalid response from Eledo API: expected schema.")
    schema = value["schema"]
    if not isinstance(schema, dict):
        from pyeledo.exceptions import EledoInvalidResponseError

        raise EledoInvalidResponseError("Invalid response from Eledo API: expected schema object.")
    return EledoSchema(schema=schema)


def pick_primitive_fields(
    schema: EledoSchema,
    allowed: Iterable[PrimitiveType] | None = None,
) -> list[PrimitiveField]:
    """Extract top-level primitive fields from a native Eledo schema."""
    allowed_set = set(allowed or PrimitiveType)
    properties = schema.schema.get("properties")
    if not isinstance(properties, dict):
        return []

    fields: list[PrimitiveField] = []
    for key, definition in properties.items():
        if not isinstance(key, str) or not isinstance(definition, dict):
            continue
        raw_type: Any = definition.get("type")
        try:
            field_type = PrimitiveType(raw_type)
        except ValueError:
            continue
        if field_type in allowed_set:
            fields.append(PrimitiveField(key=key, type=field_type))
    return fields

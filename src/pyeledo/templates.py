"""Template API helpers."""

from dataclasses import dataclass
from enum import StrEnum

from pyeledo.exceptions import EledoInvalidResponseError
from pyeledo.types import JsonObject


class TemplateScope(StrEnum):
    """Semantic template scopes exposed by pyeledo.

    Values intentionally mirror the underlying Eledo API values so the enum can be
    passed directly to query serialization, while the enum names remain Pythonic.
    """

    PRIVATE = "Mine"
    PUBLIC = "Public"


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


def parse_template_list_response(data: JsonObject) -> TemplateList:
    """Parse and validate a template list response returned by the Eledo API."""

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

        template_id = raw_template.get("id")
        date = raw_template.get("date")
        thumbnail_url = raw_template.get("thumbnailUrl")
        template_type = raw_template.get("type")
        version = raw_template.get("version")
        bulk = raw_template.get("bulk")

        templates.append(
            Template(
                id=template_id if isinstance(template_id, str) else None,
                date=date if isinstance(date, int) else None,
                name=name,
                thumbnail_url=thumbnail_url if isinstance(thumbnail_url, str) else None,
                type=template_type if isinstance(template_type, int) else None,
                version=version if isinstance(version, int) else None,
                bulk=bulk if isinstance(bulk, bool) else None,
            )
        )

    raw_total = data.get("total")
    total = raw_total if isinstance(raw_total, int) else None

    return TemplateList(total=total, templates=templates)

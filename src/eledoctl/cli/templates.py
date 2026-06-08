"""Template CLI commands."""

from __future__ import annotations

import json

import click

from eledoctl.cli.common import DEFAULT_BASE_URL, run
from pyeledo import EledoClient, TemplateScope, pick_primitive_fields
from pyeledo.types import JsonValue


@click.group("templates")
def templates_group() -> None:
    """Template inspection commands."""


@templates_group.command("list")
@click.option("--base-url", default=DEFAULT_BASE_URL, show_default=True, help="Eledo base URL.")
@click.option("--token", default="", help="Eledo API token. Temporary explicit input.")
@click.option(
    "--scope",
    type=click.Choice(["private", "public"], case_sensitive=False),
    default="private",
    show_default=True,
    help="Template scope.",
)
def list_templates(base_url: str, token: str, scope: str) -> None:
    """List Eledo templates."""
    template_scope = TemplateScope.PUBLIC if scope.lower() == "public" else TemplateScope.PRIVATE
    run(_list_templates(base_url=base_url, token=token, scope=template_scope))


async def _list_templates(*, base_url: str, token: str, scope: TemplateScope) -> None:
    async with EledoClient(base_url=base_url, token=token) as client:
        result = await client.get_templates(scope=scope)

    payload: JsonValue = {
        "total": result.total,
        "templates": [
            {
                "id": template.id,
                "name": template.name,
                "version": template.version,
                "bulk": template.bulk,
            }
            for template in result.templates
        ],
    }

    click.echo(json.dumps(payload, indent=2))


@templates_group.command("schema")
@click.argument("template_id")
@click.option("--base-url", default=DEFAULT_BASE_URL, show_default=True, help="Eledo base URL.")
@click.option("--token", default="", help="Eledo API token. Temporary explicit input.")
@click.option("--template-version", type=int, default=None, help="Optional template version.")
@click.option("--primitive-fields", is_flag=True, help="Output only top-level primitive fields.")
def get_schema(
    template_id: str,
    base_url: str,
    token: str,
    template_version: int | None,
    primitive_fields: bool,
) -> None:
    """Fetch native Eledo schema for a template."""
    run(
        _get_schema(
            template_id=template_id,
            base_url=base_url,
            token=token,
            template_version=template_version,
            primitive_fields=primitive_fields,
        )
    )


async def _get_schema(
    *,
    template_id: str,
    base_url: str,
    token: str,
    template_version: int | None,
    primitive_fields: bool,
) -> None:
    async with EledoClient(base_url=base_url, token=token) as client:
        result = await client.get_schema(
            template_id,
            template_version=template_version,
        )

    payload: JsonValue

    if primitive_fields:
        fields = pick_primitive_fields(result)
        payload = [{"key": field.key, "type": field.type.value} for field in fields]
    else:
        payload = {"schema": result}

    click.echo(json.dumps(payload, indent=2))

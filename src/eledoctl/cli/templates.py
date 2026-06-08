"""Template CLI commands."""

from __future__ import annotations

import json

import click

from eledoctl.cli.common import DEFAULT_BASE_URL, run
from pyeledo import EledoClient, TemplateScope
from pyeledo.types import JsonValue


@click.command("templates")
@click.option("--base-url", default=DEFAULT_BASE_URL, show_default=True, help="Eledo base URL.")
@click.option("--token", default="", help="Eledo API token. Temporary explicit input.")
@click.option(
    "--scope",
    type=click.Choice(["private", "public"], case_sensitive=False),
    default="private",
    show_default=True,
    help="Template scope.",
)
def templates(base_url: str, token: str, scope: str) -> None:
    """List Eledo templates."""
    template_scope = TemplateScope.PUBLIC if scope.lower() == "public" else TemplateScope.PRIVATE
    run(_templates(base_url=base_url, token=token, scope=template_scope))


async def _templates(*, base_url: str, token: str, scope: TemplateScope) -> None:
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

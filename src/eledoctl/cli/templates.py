"""Template CLI commands."""

from __future__ import annotations

import json

import click

from eledoctl.cli.common import require_connection_settings, run
from eledoctl.config.settings import ConnectionSettings
from pyeledo import EledoClient, TemplateScope
from pyeledo.types import JsonValue


@click.command("templates")
@click.option(
    "--scope",
    type=click.Choice(["private", "public"], case_sensitive=False),
    default="private",
    show_default=True,
    help="Template scope.",
)
def templates(scope: str) -> None:
    """List Eledo templates."""
    settings = require_connection_settings()
    template_scope = TemplateScope.PUBLIC if scope.lower() == "public" else TemplateScope.PRIVATE
    run(_templates(settings=settings, scope=template_scope))


async def _templates(*, settings: ConnectionSettings, scope: TemplateScope) -> None:
    async with EledoClient(base_url=settings.base_url, token=settings.token) as client:
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

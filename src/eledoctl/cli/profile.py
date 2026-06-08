"""Profile CLI command."""

from __future__ import annotations

import json

import click

from eledoctl.cli.common import require_connection_settings, run
from eledoctl.config.settings import ConnectionSettings
from pyeledo import EledoClient


@click.command("profile")
def profile() -> None:
    """Fetch current Eledo profile."""
    settings = require_connection_settings()
    run(_profile(settings=settings))


async def _profile(*, settings: ConnectionSettings) -> None:
    async with EledoClient(base_url=settings.base_url, token=settings.token) as client:
        result = await client.get_profile()

    click.echo(json.dumps({"account": result.account}, indent=2))

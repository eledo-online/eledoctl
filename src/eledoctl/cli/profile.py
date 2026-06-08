"""Profile CLI command."""

from __future__ import annotations

import json

import click

from eledoctl.cli.common import DEFAULT_BASE_URL, run
from pyeledo import EledoClient


@click.command("profile")
@click.option("--base-url", default=DEFAULT_BASE_URL, show_default=True, help="Eledo base URL.")
@click.option("--token", default="", help="Eledo API token. Temporary explicit input.")
def profile(base_url: str, token: str) -> None:
    """Fetch current Eledo profile."""
    run(_profile(base_url=base_url, token=token))


async def _profile(*, base_url: str, token: str) -> None:
    async with EledoClient(base_url=base_url, token=token) as client:
        result = await client.get_profile()

    click.echo(json.dumps({"account": result.account}, indent=2))

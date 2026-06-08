"""Login CLI command."""

from __future__ import annotations

import click

from eledoctl.cli.common import DEFAULT_BASE_URL, run
from pyeledo import EledoClient


@click.command("login")
@click.option(
    "--base-url",
    default=DEFAULT_BASE_URL,
    show_default=True,
    help="Eledo base URL.",
)
@click.option(
    "--token",
    prompt="Eledo API token",
    hide_input=True,
    help="Eledo API token to validate.",
)
def login(base_url: str, token: str) -> None:
    """Validate an Eledo API token.

    Persistent token storage will be added later in eledoctl.
    """
    run(_login(base_url=base_url, token=token))


async def _login(*, base_url: str, token: str) -> None:
    """Validate an Eledo API token against the profile endpoint."""
    async with EledoClient(base_url=base_url, token=token) as client:
        profile = await client.get_profile()

    click.echo(f"Authenticated as {profile.account}.")

"""Login CLI command."""

from __future__ import annotations

import json
import webbrowser
from typing import cast

import click

from eledoctl.cli.common import run
from eledoctl.config.settings import DEFAULT_BASE_URL, ConnectionSettings, save_connection_settings
from pyeledo import EledoApiError, EledoAuthenticationError, EledoClient
from pyeledo.profile import Profile

LOGIN_PATH = "/app/login/start"


@click.command("login")
@click.option("--base-url", default=DEFAULT_BASE_URL, show_default=True, help="Eledo base URL.")
@click.option(
    "--token",
    envvar="ELEDO_API_TOKEN",
    default=None,
    help="Eledo API token. Can also be provided through ELEDO_API_TOKEN.",
)
def login(base_url: str, token: str | None) -> None:
    """Authenticate eledoctl with an Eledo API token."""
    normalized_base_url = base_url.rstrip("/")

    if token is None:
        token = _prompt_for_token(normalized_base_url)

    token = token.strip()
    if not token:
        raise click.ClickException("The API token cannot be empty.")

    settings = ConnectionSettings(base_url=normalized_base_url, token=token)

    try:
        profile = run(_validate_token(settings))
    except (EledoApiError, EledoAuthenticationError) as exc:
        raise click.ClickException(f"Authentication failed: {exc}") from exc

    try:
        save_connection_settings(settings)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise click.ClickException(f"Could not save the local configuration: {exc}") from exc

    click.echo()
    click.echo(f"Authenticated as {profile.account}.")
    click.echo("The API token has been saved to the local eledoctl configuration.")


def _prompt_for_token(base_url: str) -> str:
    login_url = f"{base_url}{LOGIN_PATH}"

    click.echo("Opening Eledo in your browser.")
    click.echo()
    click.echo("To obtain your API token:")
    click.echo("  1. Log in to your Eledo account.")
    click.echo("  2. Open Profile in the bottom-left corner.")
    click.echo("  3. Open the API tab under Your Profile.")
    click.echo("  4. Generate an API key if needed, then copy it.")
    click.echo()
    click.echo(f"Login URL: {login_url}")

    if not webbrowser.open(login_url, new=2):
        click.echo("The browser could not be opened automatically. Open the URL above manually.", err=True)

    click.echo()

    return cast(str, click.prompt("Paste your Eledo API token", type=str, hide_input=True))


async def _validate_token(settings: ConnectionSettings) -> Profile:
    """Validate an Eledo API token and return its profile."""
    async with EledoClient(base_url=settings.base_url, token=settings.token) as client:
        return await client.get_profile()

"""Login CLI command."""

from __future__ import annotations

import json
import webbrowser

import click

from eledoctl.cli.common import DEFAULT_BASE_URL, run
from eledoctl.config.settings import save_token
from pyeledo import EledoApiError, EledoClient

LOGIN_PATH = "/app/login/start"


@click.command("login")
@click.option(
    "--base-url",
    default=DEFAULT_BASE_URL,
    show_default=True,
    help="Eledo base URL.",
)
def login(base_url: str) -> None:
    """Authenticate eledoctl with an Eledo API token."""
    normalized_base_url = base_url.rstrip("/")
    login_url = f"{normalized_base_url}{LOGIN_PATH}"

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
        click.echo("The browser could not be opened automatically. Open the URL above manually.")

    click.echo()
    token = click.prompt("Paste your Eledo API token", hide_input=True).strip()

    if not token:
        raise click.ClickException("The API token cannot be empty.")

    try:
        profile = run(
            _validate_token(
                base_url=normalized_base_url,
                token=token,
            )
        )
    except EledoApiError as exc:
        raise click.ClickException(f"Authentication failed: {exc}") from exc

    try:
        save_token(
            base_url=normalized_base_url,
            token=token,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise click.ClickException(f"Could not save the local configuration: {exc}") from exc

    click.echo()
    click.echo(f"Authenticated as {profile.account}.")
    click.echo("The API token has been saved to the local eledoctl configuration.")


async def _validate_token(*, base_url: str, token: str):
    """Validate an Eledo API token and return its profile."""
    async with EledoClient(base_url=base_url, token=token) as client:
        return await client.get_profile()
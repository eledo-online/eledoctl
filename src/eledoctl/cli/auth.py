"""Authentication commands."""

from __future__ import annotations

import asyncio
import webbrowser

import typer
from rich.console import Console

from eledoctl.config.settings import save_token

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command("login")
def login(
    base_url: str = typer.Option("https://app.eledo.online", help="Eledo base URL."),
    token: str | None = typer.Option(None, help="API token. If omitted, paste interactively."),
    open_browser: bool = typer.Option(True, help="Open Eledo login page in browser."),
) -> None:
    """Store an Eledo API token locally.

    Token validation will be connected after the final Eledo auth endpoint is available.
    """
    asyncio.run(_login_async(base_url=base_url, token=token, open_browser=open_browser))


async def _login_async(*, base_url: str, token: str | None, open_browser: bool) -> None:
    if open_browser:
        webbrowser.open(base_url)

    if token is None:
        token = typer.prompt("Paste Eledo API token", hide_input=True)

    save_token(base_url=base_url, token=token)
    console.print("[green]Eledo token saved.[/green]")

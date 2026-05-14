"""Template commands."""

from __future__ import annotations

import typer
from rich.console import Console

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command("list")
def list_templates() -> None:
    """List available Eledo templates."""
    console.print("[yellow]Template listing is not implemented yet.[/yellow]")

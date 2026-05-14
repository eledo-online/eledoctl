"""PDF generation commands."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command("generate")
def generate_pdf(
    template: str = typer.Argument(..., help="Template ID or slug."),
    payload: Path | None = typer.Option(None, "--payload", "-p", help="JSON payload file."),
) -> None:
    """Generate PDF from an Eledo template."""
    console.print(
        f"[yellow]PDF generation is not implemented yet.[/yellow] template={template!r}, payload={payload}"
    )

"""Internal documentation synchronization commands."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command("sync")
def sync_docs(
    path: Path = typer.Argument(..., help="Documentation root or subtree to synchronize."),
    review_report: Path | None = typer.Option(
        None,
        "--review-report",
        help="Optional path where manual review report will be written.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Analyze without uploading changes."),
) -> None:
    """Synchronize Git documentation into Eledo CMS.

    Implementation will be added after the Eledo CMS CRUD API is available.
    """
    console.print(
        "[yellow]Documentation sync scaffold is ready, but implementation is pending.[/yellow]"
    )
    console.print(f"path={path}")
    console.print(f"review_report={review_report}")
    console.print(f"dry_run={dry_run}")

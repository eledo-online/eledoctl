"""Internal documentation synchronization CLI commands."""

from __future__ import annotations

from pathlib import Path

import click


@click.group("internal")
def internal_group() -> None:
    """Internal Eledo operational tooling."""


@internal_group.group("docs")
def internal_docs_group() -> None:
    """Internal documentation synchronization tooling."""


@internal_docs_group.command("sync")
@click.argument("path", type=click.Path(path_type=Path))
@click.option(
    "--review-report",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help="Optional path where manual review report will be written.",
)
@click.option("--dry-run", is_flag=True, help="Analyze without uploading changes.")
def sync_docs(path: Path, review_report: Path | None, dry_run: bool) -> None:
    """Synchronize Git documentation into Eledo CMS.

    Implementation will be added after the Eledo CMS CRUD API is available.
    """
    click.echo("Documentation sync scaffold is ready, but implementation is pending.")
    click.echo(f"path={path}")
    click.echo(f"review_report={review_report}")
    click.echo(f"dry_run={dry_run}")

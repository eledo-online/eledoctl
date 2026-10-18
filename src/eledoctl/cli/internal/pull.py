"""Manual CMS -> Git documentation recovery command."""

from __future__ import annotations

from pathlib import Path

import click

from eledoctl.cli.common import require_connection_settings, run
from eledoctl.cli.internal.docs import _should_show_progress
from eledoctl.config.settings import ConnectionSettings
from eledoctl.internal.docs.reverse import (
    PullResult,
    pull_one_document,
    summarize_pull,
    write_pull_log,
)
from eledoctl.internal.docs.uploader import SyncItem, SyncOptions, build_sync_plan
from pyeledo import EledoClient
from pyeledo.internal.cms import CmsClient


@click.command("pull")
@click.argument("source_root", type=click.Path(path_type=Path, exists=True))
@click.argument("selection", required=False, type=click.Path(path_type=Path, exists=True))
@click.option(
    "--destination-root",
    default="/documentation",
    show_default=True,
    help="Remote CMS subtree corresponding to SOURCE_ROOT.",
)
@click.option("--dry-run", is_flag=True, help="Detect recoverable edits without modifying local files.")
@click.option(
    "--log-file",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help="Optional JSONL log; failed files require manual review.",
)
@click.option("--progress/--no-progress", default=True, show_default=True)
def pull_docs(
    *,
    source_root: Path,
    selection: Path | None,
    destination_root: str,
    dry_run: bool,
    log_file: Path | None,
    progress: bool,
) -> None:
    """Pull CMS editorial changes into existing Git/MDX files for manual review.

    Does not change the CMS, make Git commits, or create/delete local files.
    Ambiguous transformations are logged and leave the local file untouched.
    """
    settings = require_connection_settings()
    try:
        plan = build_sync_plan(
            SyncOptions(source_root=source_root, selection=selection, destination_root=destination_root)
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(f"Source root: {plan.source_root}")
    click.echo(f"Selection: {plan.selection}")
    click.echo(f"Remote root: {destination_root}")
    click.echo(f"Files: {len(plan.items)}")
    click.echo(f"Dry run: {dry_run}")
    click.echo()

    results = run(
        _pull_docs(
            settings=settings, items=plan.items, dry_run=dry_run, show_progress=progress and _should_show_progress()
        )
    )
    if log_file is not None:
        write_pull_log(log_file, results)
        click.echo(f"Pull log written to: {log_file}")
    summary = summarize_pull(results, dry_run=dry_run)
    click.echo("\nSummary:")
    click.echo(f"  total: {summary.total}")
    click.echo(f"  updated: {summary.updated}")
    click.echo(f"  unchanged: {summary.unchanged}")
    click.echo(f"  failures: {summary.failed}")
    if summary.failed:
        for result in results:
            if result.messages:
                click.echo(f"  {result.target_path}: {'; '.join(result.messages)}", err=True)
        raise click.ClickException(f"Reverse sync failed for {summary.failed} file(s).")


async def _pull_docs(
    *,
    settings: ConnectionSettings,
    items: tuple[SyncItem, ...],
    dry_run: bool,
    show_progress: bool,
) -> list[PullResult]:
    results: list[PullResult] = []
    async with EledoClient(base_url=settings.base_url, token=settings.token) as client:
        cms = CmsClient(client)
        if show_progress:
            with click.progressbar(items, length=len(items), label="Pulling", show_percent=False, show_pos=True) as bar:
                for item in bar:
                    results.append(await pull_one_document(cms=cms, item=item, dry_run=dry_run))
        else:
            for item in items:
                results.append(await pull_one_document(cms=cms, item=item, dry_run=dry_run))
    return results

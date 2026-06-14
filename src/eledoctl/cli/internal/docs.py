"""Internal documentation synchronization CLI commands."""

from __future__ import annotations

import os
import sys
from dataclasses import fields
from pathlib import Path
from typing import Any

import click

from eledoctl.cli.common import require_connection_settings, run
from eledoctl.config.settings import ConnectionSettings
from eledoctl.internal.docs.transformer import TransformOptions
from eledoctl.internal.docs.uploader import (
    SyncFileResult,
    SyncItem,
    SyncOptions,
    build_sync_plan,
    summarize_results,
    sync_one_document,
    write_inspection_file,
    write_log_file,
)
from pyeledo import EledoClient
from pyeledo.internal.cms import CmsClient

_TRANSFORM_OPTION_NAMES = {field.name.replace("_", "-"): field.name for field in fields(TransformOptions)}


@click.group("internal")
def internal_group() -> None:
    """Internal Eledo operational tooling."""


@internal_group.group("docs")
def internal_docs_group() -> None:
    """Internal documentation synchronization tooling."""


@internal_docs_group.command("sync")
@click.argument(
    "source_root",
    type=click.Path(path_type=Path, exists=True),
)
@click.argument(
    "selection",
    required=False,
    type=click.Path(path_type=Path, exists=True),
)
@click.option(
    "--destination-root",
    default="/documentation",
    show_default=True,
    help="Root CMS article path where documentation will be synced.",
)
@click.option(
    "--tag",
    required=True,
    callback=lambda _ctx, _param, value: _validate_tag(value),
    help="Required sync tag. Passed to Eledo CMS as the label query parameter.",
)
@click.option("--dry-run", is_flag=True, help="Fetch and transform documents without uploading changes.")
@click.option(
    "--skip-unchanged/--no-skip-unchanged",
    default=True,
    show_default=True,
    help="Skip upload when transformed content and effective metadata match the existing CMS article.",
)
@click.option(
    "--log-file",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help="Optional JSONL sync log path.",
)
@click.option(
    "--inspect-file",
    "--review-report",
    "inspect_file",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help="Optional path where files requiring manual inspection will be written.",
)
@click.option(
    "--progress/--no-progress",
    default=True,
    show_default=True,
    help="Show a progress bar when running interactively.",
)
@click.option(
    "--disable-transform",
    type=click.Choice(sorted(_TRANSFORM_OPTION_NAMES), case_sensitive=False),
    multiple=True,
    help="Disable one transformer stage. May be repeated.",
)
def sync_docs(
    *,
    source_root: Path,
    selection: Path | None,
    destination_root: str,
    tag: str,
    dry_run: bool,
    skip_unchanged: bool,
    log_file: Path | None,
    inspect_file: Path | None,
    progress: bool,
    disable_transform: tuple[str, ...],
) -> None:
    """Synchronize source Markdown documentation into Eledo CMS."""
    settings = require_connection_settings()

    options = SyncOptions(
        source_root=source_root,
        selection=selection,
        destination_root=destination_root,
        tag=tag,
        dry_run=dry_run,
        skip_unchanged=skip_unchanged,
        transform_options=_transform_options(disable_transform),
    )

    try:
        plan = build_sync_plan(options)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(f"Source root: {plan.source_root}")
    click.echo(f"Selection: {plan.selection}")
    click.echo(f"Destination root: {destination_root}")
    click.echo(f"Files: {len(plan.items)}")
    click.echo(f"Dry run: {dry_run}")
    click.echo()

    results = run(
        _sync_docs(
            settings=settings,
            options=options,
            items=plan.items,
            show_progress=progress and _should_show_progress(),
        )
    )

    if log_file is not None:
        write_log_file(log_file, results)
        click.echo(f"Sync log written to: {log_file}")

    if inspect_file is not None:
        write_inspection_file(inspect_file, results)
        click.echo(f"Manual inspection list written to: {inspect_file}")

    summary = summarize_results(results, dry_run=dry_run)

    click.echo()
    click.echo("Summary:")
    click.echo(f"  total: {summary.total}")
    click.echo(f"  created: {summary.created}")
    click.echo(f"  updated: {summary.updated}")
    click.echo(f"  skipped: {summary.skipped}")
    click.echo(f"  warnings: {summary.warnings}")
    click.echo(f"  failures: {summary.failures}")

    if summary.failures > 0:
        raise click.ClickException(f"Documentation sync failed for {summary.failures} file(s).")


async def _sync_docs(
    *,
    settings: ConnectionSettings,
    options: SyncOptions,
    items: tuple[SyncItem, ...],
    show_progress: bool,
) -> list[SyncFileResult]:
    results: list[SyncFileResult] = []

    async with EledoClient(base_url=settings.base_url, token=settings.token) as client:
        cms = CmsClient(client)

        if show_progress:
            with click.progressbar(
                items,
                length=len(items),
                label="Uploading",
                show_percent=False,
                show_pos=True,
            ) as progress_items:
                for item in progress_items:
                    results.append(await sync_one_document(cms=cms, item=item, options=options))
        else:
            for item in items:
                results.append(await sync_one_document(cms=cms, item=item, options=options))

    return results


def _transform_options(disabled_transforms: tuple[str, ...]) -> TransformOptions:
    values: dict[str, Any] = {field.name: True for field in fields(TransformOptions)}

    for disabled_transform in disabled_transforms:
        field_name = _TRANSFORM_OPTION_NAMES[disabled_transform.lower()]
        values[field_name] = False

    return TransformOptions(**values)


def _validate_tag(value: str) -> str:
    normalized = value.strip()

    if not normalized:
        raise click.BadParameter("Tag cannot be empty.")

    return normalized


def _should_show_progress() -> bool:
    return sys.stdout.isatty() and not _is_ci_environment()


def _is_ci_environment() -> bool:
    return os.environ.get("CI", "").lower() in {"1", "true", "yes"} or os.environ.get("GITHUB_ACTIONS", "").lower() in {
        "1",
        "true",
        "yes",
    }

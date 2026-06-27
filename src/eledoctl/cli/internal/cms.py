from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import click

from eledoctl.cli.common import require_connection_settings, run
from eledoctl.internal.cms.validator import CmsValidationResult, validate_cms_tree, write_validation_log
from pyeledo import EledoClient
from pyeledo.internal.cms import CmsClient


@click.group("cms")
def internal_cms_group() -> None:
    """Internal documentation synchronization tooling."""


@internal_cms_group.command("validate")
@click.option(
    "--remote-path",
    default="documentation",
    show_default=True,
    help="Remote CMS article path to validate, for example documentation or documentation/api.",
)
@click.option(
    "--log-file",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Write validation warnings as JSON Lines.",
)
@click.option(
    "--fail-on-warning",
    is_flag=True,
    help="Exit with a non-zero status code when validation warnings are found.",
)
@click.option(
    "--progress/--no-progress",
    default=True,
    show_default=True,
    help="Show progress while validating CMS articles. Disabled automatically in CI.",
)
def validate(
    remote_path: str,
    log_file: Path | None,
    fail_on_warning: bool,
    progress: bool,
) -> None:
    """Validate CMS articles for suspicious leftover Docusaurus references."""
    settings = require_connection_settings()
    show_progress = _should_show_progress(progress)

    progress_callback: Callable[[tuple[str, ...], int], None] | None = None

    if show_progress:
        with click.progressbar(
            length=1,
            label="Validating CMS",
            show_pos=True,
        ) as bar:

            def update_progress(_target_segments: tuple[str, ...], discovered_children: int) -> None:
                bar.length = (bar.length or 0) + discovered_children
                bar.update(1)

            progress_callback = update_progress

            result = run(
                _validate_cms(
                    base_url=settings.base_url,
                    token=settings.token,
                    remote_path=remote_path,
                    progress_callback=progress_callback,
                )
            )
    else:
        result = run(
            _validate_cms(
                base_url=settings.base_url,
                token=settings.token,
                remote_path=remote_path,
                progress_callback=None,
            )
        )

    if log_file is not None:
        write_validation_log(path=log_file, result=result)

    click.echo("CMS validation complete.")
    click.echo(f"  checked articles: {result.checked_articles}")
    click.echo(f"  warnings: {result.warning_count}")

    if log_file is not None:
        click.echo(f"  log file: {log_file}")

    if fail_on_warning and result.warning_count > 0:
        raise click.ClickException(f"CMS validation found {result.warning_count} warning(s).")


async def _validate_cms(
    *,
    base_url: str,
    token: str,
    remote_path: str,
    progress_callback: Callable[[tuple[str, ...], int], None] | None,
) -> CmsValidationResult:
    async with EledoClient(base_url=base_url, token=token) as client:
        cms = CmsClient(client)

        return await validate_cms_tree(
            cms=cms,
            remote_path=remote_path,
            progress_callback=progress_callback,
        )


def _is_ci_environment() -> bool:
    """Return whether the command appears to run in CI."""
    return any(
        os.environ.get(name)
        for name in (
            "CI",
            "GITHUB_ACTIONS",
            "GITLAB_CI",
            "BUILDKITE",
            "CIRCLECI",
            "JENKINS_URL",
        )
    )


def _should_show_progress(progress: bool) -> bool:
    """Return whether progress output should be shown."""
    return progress and not _is_ci_environment() and click.get_text_stream("stderr").isatty()

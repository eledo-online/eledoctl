from __future__ import annotations

from pathlib import Path
from typing import Any

import click

from eledoctl.cli.common import require_connection_settings, run
from eledoctl.internal.cms.validator import validate_cms_tree, write_validation_log
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
def validate(remote_path: str, log_file: Path | None) -> None:
    """Validate CMS articles for suspicious leftover Docusaurus references."""
    settings = require_connection_settings()

    result = run(
        _validate_cms(
            base_url=settings.base_url,
            token=settings.token,
            remote_path=remote_path,
        )
    )

    if log_file is not None:
        write_validation_log(path=log_file, result=result)

    click.echo("CMS validation complete.")
    click.echo(f"  checked articles: {result.checked_articles}")
    click.echo(f"  warnings: {result.warning_count}")

    if log_file is not None:
        click.echo(f"  log file: {log_file}")


async def _validate_cms(
    *,
    base_url: str,
    token: str,
    remote_path: str,
) -> Any:
    async with EledoClient(base_url=base_url, token=token) as client:
        cms_client = CmsClient(client)

        return await validate_cms_tree(
            cms=cms_client,
            remote_path=remote_path,
        )

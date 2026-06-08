"""PDF generation CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

import click

from eledoctl.cli.common import require_connection_settings, run
from eledoctl.config.settings import ConnectionSettings
from pyeledo import EledoClient
from pyeledo.utils import parse_json_object


@click.group("documents")
def documents_group() -> None:
    """PDF generation commands."""


@documents_group.command("generate")
@click.argument("template_id")
@click.option("--template-version", type=int, default=None, help="Optional template version.")
@click.option(
    "--payload",
    "payload_path",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    default=None,
    help='JSON file containing the content of the Eledo "file" object.',
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help="PDF output path. Defaults to filename returned by Eledo.",
)
@click.option("--base64-json", is_flag=True, help="Print JSON metadata with base64 PDF content.")
def generate_pdf(
    template_id: str,
    template_version: int | None,
    payload_path: Path | None,
    output_path: Path | None,
    base64_json: bool,
) -> None:
    """Generate a PDF from an Eledo template."""
    settings = require_connection_settings()
    run(
        _generate_pdf(
            template_id=template_id,
            settings=settings,
            template_version=template_version,
            payload_path=payload_path,
            output_path=output_path,
            base64_json=base64_json,
        )
    )


async def _generate_pdf(
    *,
    template_id: str,
    settings: ConnectionSettings,
    template_version: int | None,
    payload_path: Path | None,
    output_path: Path | None,
    base64_json: bool,
) -> None:
    file_data = None

    if payload_path is not None:
        parsed = parse_json_object(payload_path.read_text(encoding="utf-8"))
        file_data = parsed or None

    async with EledoClient(base_url=settings.base_url, token=settings.token) as client:
        result = await client.generate_pdf(
            template_id=template_id,
            template_version=template_version,
            file_data=file_data,
        )

    if base64_json:
        click.echo(json.dumps(result.as_json(), indent=2))
        return

    destination = output_path or Path(result.filename)
    destination.write_bytes(result.content)
    click.echo(str(destination))

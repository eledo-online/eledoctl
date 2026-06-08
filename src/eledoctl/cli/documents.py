"""PDF generation CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

import click

from eledoctl.cli.common import DEFAULT_BASE_URL, run
from pyeledo import EledoClient
from pyeledo.utils import parse_json_object


@click.group("documents")
def documents_group() -> None:
    """PDF generation commands."""


@documents_group.command("generate")
@click.argument("template_id")
@click.option("--base-url", default=DEFAULT_BASE_URL, show_default=True, help="Eledo base URL.")
@click.option("--token", default="", help="Eledo API token. Temporary explicit input.")
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
    base_url: str,
    token: str,
    template_version: int | None,
    payload_path: Path | None,
    output_path: Path | None,
    base64_json: bool,
) -> None:
    """Generate a PDF from an Eledo template."""
    run(
        _generate_pdf(
            template_id=template_id,
            base_url=base_url,
            token=token,
            template_version=template_version,
            payload_path=payload_path,
            output_path=output_path,
            base64_json=base64_json,
        )
    )


async def _generate_pdf(
    *,
    template_id: str,
    base_url: str,
    token: str,
    template_version: int | None,
    payload_path: Path | None,
    output_path: Path | None,
    base64_json: bool,
) -> None:
    file_data = None

    if payload_path is not None:
        parsed = parse_json_object(payload_path.read_text(encoding="utf-8"))
        file_data = parsed or None

    async with EledoClient(base_url=base_url, token=token) as client:
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

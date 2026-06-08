"""PDF generation CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

import click

from eledoctl.cli.common import require_connection_settings, run
from eledoctl.config.settings import ConnectionSettings
from pyeledo import EledoClient
from pyeledo.types import JsonObject
from pyeledo.utils import parse_json_object


@click.group("documents")
def documents_group() -> None:
    """PDF generation commands."""


@documents_group.command("generate")
@click.argument("template_id")
@click.option("--template-version", type=int, default=None, help="Optional template version.")
@click.option(
    "--payload",
    type=str,
    default=None,
    help='Inline JSON containing the Eledo "file" object.',
)
@click.option(
    "--payload-file",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    default=None,
    help='Read the Eledo "file" object from a JSON file.',
)
@click.option(
    "--payload-stdin",
    is_flag=True,
    help='Read the Eledo "file" object from standard input.',
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help="PDF output path. Defaults to filename returned by Eledo.",
)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=None,
    help="Directory for the generated PDF when --output is not provided.",
)
@click.option("--base64-json", is_flag=True, help="Print JSON metadata with base64 PDF content.")
def generate_pdf(
    template_id: str,
    template_version: int | None,
    payload: str | None,
    payload_file: Path | None,
    payload_stdin: bool,
    output_path: Path | None,
    output_dir: Path | None,
    base64_json: bool,
) -> None:
    """Generate a PDF from an Eledo template."""
    settings = require_connection_settings()
    run(
        _generate_pdf(
            template_id=template_id,
            settings=settings,
            template_version=template_version,
            file_data=_resolve_payload(payload=payload, payload_file=payload_file, payload_stdin=payload_stdin),
            output_path=output_path,
            output_dir=output_dir,
            base64_json=base64_json,
        )
    )


async def _generate_pdf(
    *,
    template_id: str,
    settings: ConnectionSettings,
    template_version: int | None,
    file_data: JsonObject | None,
    output_path: Path | None,
    output_dir: Path | None,
    base64_json: bool,
) -> None:
    async with EledoClient(base_url=settings.base_url, token=settings.token) as client:
        result = await client.generate_pdf(
            template_id=template_id,
            template_version=template_version,
            file_data=file_data,
        )

    if base64_json:
        click.echo(json.dumps(result.as_json(), indent=2))
        return

    destination = _resolve_output_path(
        filename=result.filename,
        output_path=output_path,
        output_dir=output_dir,
    )
    destination.write_bytes(result.content)
    click.echo(str(destination))

def _resolve_payload(
    *,
    payload: str | None,
    payload_file: Path | None,
    payload_stdin: bool,
) -> JsonObject | None:
    """Read and parse document data from one configured input source."""
    source_count = sum(
        (
            payload is not None,
            payload_file is not None,
            payload_stdin,
        )
    )

    if source_count > 1:
        raise click.ClickException(
            "Use only one of --payload, --payload-file, or --payload-stdin."
        )

    if payload is not None:
        parsed = parse_json_object(payload)
    elif payload_file is not None:
        parsed = parse_json_object(payload_file.read_text(encoding="utf-8"))
    elif payload_stdin:
        parsed = parse_json_object(click.get_text_stream("stdin").read())
    else:
        return None

    return parsed or None

def _resolve_output_path(
    *,
    filename: str,
    output_path: Path | None,
    output_dir: Path | None,
) -> Path:
    """Resolve the destination path for a generated PDF."""
    if output_path is not None:
        return output_path

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir / filename

    return Path(filename)
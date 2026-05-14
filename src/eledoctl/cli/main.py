"""Top-level eledoctl command tree."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import click

from pyeledo import EledoClient, PrimitiveType, TemplateScope, pick_primitive_fields
from pyeledo.utils import parse_json_object

DEFAULT_BASE_URL = "https://eledo.online"


def run(coro: Any) -> Any:
    """Run an async command implementation from Click."""
    return asyncio.run(coro)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def main() -> None:
    """Command-line toolkit for Eledo."""


@main.command("profile")
@click.option("--base-url", default=DEFAULT_BASE_URL, show_default=True, help="Eledo base URL.")
@click.option("--token", default="", help="Eledo API token. Temporary explicit input.")
def profile(base_url: str, token: str) -> None:
    """Fetch current Eledo profile."""
    run(_profile(base_url=base_url, token=token))


async def _profile(*, base_url: str, token: str) -> None:
    async with EledoClient(base_url=base_url, token=token) as client:
        result = await client.get_profile()
    click.echo(json.dumps({"account": result.account}, indent=2))


@main.group("templates")
def templates_group() -> None:
    """Template inspection commands."""


@templates_group.command("list")
@click.option("--base-url", default=DEFAULT_BASE_URL, show_default=True, help="Eledo base URL.")
@click.option("--token", default="", help="Eledo API token. Temporary explicit input.")
@click.option(
    "--scope",
    type=click.Choice(["private", "public"], case_sensitive=False),
    default="private",
    show_default=True,
    help="Template scope.",
)
def list_templates(base_url: str, token: str, scope: str) -> None:
    """List Eledo templates."""
    template_scope = TemplateScope.PUBLIC if scope.lower() == "public" else TemplateScope.PRIVATE
    run(_list_templates(base_url=base_url, token=token, scope=template_scope))


async def _list_templates(*, base_url: str, token: str, scope: TemplateScope) -> None:
    async with EledoClient(base_url=base_url, token=token) as client:
        result = await client.get_templates(scope=scope)
    payload = {
        "total": result.total,
        "templates": [
            {
                "id": template.id,
                "name": template.name,
                "version": template.version,
                "bulk": template.bulk,
            }
            for template in result.templates
        ],
    }
    click.echo(json.dumps(payload, indent=2))


@templates_group.command("schema")
@click.argument("template_id")
@click.option("--base-url", default=DEFAULT_BASE_URL, show_default=True, help="Eledo base URL.")
@click.option("--token", default="", help="Eledo API token. Temporary explicit input.")
@click.option("--template-version", type=int, default=None, help="Optional template version.")
@click.option("--primitive-fields", is_flag=True, help="Output only top-level primitive fields.")
def get_schema(
    template_id: str,
    base_url: str,
    token: str,
    template_version: int | None,
    primitive_fields: bool,
) -> None:
    """Fetch native Eledo schema for a template."""
    run(
        _get_schema(
            template_id=template_id,
            base_url=base_url,
            token=token,
            template_version=template_version,
            primitive_fields=primitive_fields,
        )
    )


async def _get_schema(
    *,
    template_id: str,
    base_url: str,
    token: str,
    template_version: int | None,
    primitive_fields: bool,
) -> None:
    async with EledoClient(base_url=base_url, token=token) as client:
        result = await client.get_schema(template_id, template_version=template_version)
    if primitive_fields:
        fields = pick_primitive_fields(result)
        payload = [{"key": field.key, "type": field.type.value} for field in fields]
    else:
        payload = {"schema": result.schema}
    click.echo(json.dumps(payload, indent=2))


@main.group("pdf")
def pdf_group() -> None:
    """PDF generation commands."""


@pdf_group.command("generate")
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
        click.echo(json.dumps(result.as_base64_payload(), indent=2))
        return

    destination = output_path or Path(result.filename)
    destination.write_bytes(result.content)
    click.echo(str(destination))


@main.group("internal")
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


# Compatibility alias for direct function imports.
app = main


if __name__ == "__main__":
    main()

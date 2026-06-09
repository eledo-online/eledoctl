"""Tests for document generation CLI helpers."""

from __future__ import annotations

import json
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from eledoctl.cli.documents import (
    _build_field_payload,
    _resolve_output_path,
    _resolve_payload,
)


def test_build_field_payload_returns_none_when_no_fields() -> None:
    assert _build_field_payload(()) is None


def test_build_field_payload_builds_top_level_string_fields() -> None:
    assert _build_field_payload(("Notes=Hello", "QuoteNo=123")) == {
        "Notes": "Hello",
        "QuoteNo": "123",
    }


def test_build_field_payload_preserves_equals_signs_in_value() -> None:
    assert _build_field_payload(("Notes=A=B",)) == {"Notes": "A=B"}


def test_build_field_payload_strips_key_but_preserves_value() -> None:
    assert _build_field_payload((" Notes = Hello ",)) == {"Notes": " Hello "}


def test_build_field_payload_rejects_field_without_separator() -> None:
    with pytest.raises(click.ClickException, match="Expected KEY=VALUE"):
        _build_field_payload(("Notes",))


def test_build_field_payload_rejects_empty_key() -> None:
    with pytest.raises(click.ClickException, match="Field name cannot be empty"):
        _build_field_payload(("=Hello",))


def test_resolve_payload_returns_none_without_payload_sources_or_fields() -> None:
    assert (
        _resolve_payload(
            payload=None,
            payload_file=None,
            payload_stdin=False,
            fields=(),
        )
        is None
    )


def test_resolve_payload_reads_inline_json() -> None:
    assert _resolve_payload(
        payload='{"Notes": "Hello"}',
        payload_file=None,
        payload_stdin=False,
        fields=(),
    ) == {"Notes": "Hello"}


def test_resolve_payload_reads_json_file(tmp_path: Path) -> None:
    payload_file = tmp_path / "payload.json"
    payload_file.write_text('{"Notes": "From file"}', encoding="utf-8")

    assert _resolve_payload(
        payload=None,
        payload_file=payload_file,
        payload_stdin=False,
        fields=(),
    ) == {"Notes": "From file"}


def test_resolve_payload_reads_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()

    @click.command()
    def command() -> None:
        value = _resolve_payload(
            payload=None,
            payload_file=None,
            payload_stdin=True,
            fields=(),
        )
        click.echo(json.dumps(value))

    result = runner.invoke(command, input='{"Notes": "From stdin"}')

    assert result.exit_code == 0
    assert json.loads(result.output) == {"Notes": "From stdin"}


def test_resolve_payload_uses_fields_when_no_payload_source() -> None:
    assert _resolve_payload(
        payload=None,
        payload_file=None,
        payload_stdin=False,
        fields=("Notes=Hello",),
    ) == {"Notes": "Hello"}


@pytest.mark.parametrize(
    "kwargs",
    [
        {
            "payload": "{}",
            "payload_file": Path("payload.json"),
            "payload_stdin": False,
        },
        {
            "payload": "{}",
            "payload_file": None,
            "payload_stdin": True,
        },
        {
            "payload": None,
            "payload_file": Path("payload.json"),
            "payload_stdin": True,
        },
    ],
)
def test_resolve_payload_rejects_multiple_payload_sources(kwargs: dict[str, object]) -> None:
    with pytest.raises(click.ClickException, match="Use only one of"):
        _resolve_payload(
            payload=kwargs["payload"],  # type: ignore[arg-type]
            payload_file=kwargs["payload_file"],  # type: ignore[arg-type]
            payload_stdin=kwargs["payload_stdin"],  # type: ignore[arg-type]
            fields=(),
        )


def test_resolve_payload_payload_source_overrides_fields() -> None:
    assert _resolve_payload(
        payload='{"Notes": "From payload"}',
        payload_file=None,
        payload_stdin=False,
        fields=("Notes=From field",),
    ) == {"Notes": "From payload"}


def test_resolve_output_path_prefers_explicit_output(tmp_path: Path) -> None:
    output_path = tmp_path / "custom.pdf"
    output_dir = tmp_path / "generated"

    assert (
        _resolve_output_path(
            filename="returned.pdf",
            output_path=output_path,
            output_dir=output_dir,
        )
        == output_path
    )


def test_resolve_output_path_uses_output_dir_with_returned_filename(tmp_path: Path) -> None:
    output_dir = tmp_path / "generated"

    assert (
        _resolve_output_path(
            filename="returned.pdf",
            output_path=None,
            output_dir=output_dir,
        )
        == output_dir / "returned.pdf"
    )

    assert output_dir.exists()


def test_resolve_output_path_uses_current_directory_when_no_output_options() -> None:
    assert _resolve_output_path(
        filename="returned.pdf",
        output_path=None,
        output_dir=None,
    ) == Path("returned.pdf")

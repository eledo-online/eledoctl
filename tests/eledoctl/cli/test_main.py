"""Tests for the top-level CLI command tree."""

from __future__ import annotations

from click.testing import CliRunner

from eledoctl.cli.main import app, main


def test_app_alias_points_to_main() -> None:
    assert app is main


def test_main_help_lists_public_commands() -> None:
    result = CliRunner().invoke(main, ["--help"])

    assert result.exit_code == 0
    assert "Command-line toolkit for Eledo." in result.output
    assert "login" in result.output
    assert "profile" in result.output
    assert "templates" in result.output
    assert "documents" in result.output
    assert "internal" in result.output


def test_main_supports_short_help_option() -> None:
    result = CliRunner().invoke(main, ["-h"])

    assert result.exit_code == 0
    assert "Command-line toolkit for Eledo." in result.output

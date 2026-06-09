"""Tests for the profile CLI command."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

import eledoctl.cli.profile as profile_module
from eledoctl.cli.profile import profile
from eledoctl.config.settings import ConnectionSettings


def test_profile_prints_current_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = ConnectionSettings(
        base_url="https://eledo.online",
        token="secret",
    )

    async def profile_impl(*, settings: ConnectionSettings) -> None:
        profile_module.click.echo('{"account": "user@example.com"}')

    monkeypatch.setattr(
        profile_module,
        "require_connection_settings",
        lambda: settings,
    )
    monkeypatch.setattr(profile_module, "_profile", profile_impl)

    result = CliRunner().invoke(profile)

    assert result.exit_code == 0
    assert '"account": "user@example.com"' in result.output


def test_profile_requires_connection_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_error() -> ConnectionSettings:
        raise profile_module.click.ClickException("No Eledo credentials found. Run `eledoctl login` first.")

    monkeypatch.setattr(profile_module, "require_connection_settings", raise_error)

    result = CliRunner().invoke(profile)

    assert result.exit_code != 0
    assert "No Eledo credentials found." in result.output

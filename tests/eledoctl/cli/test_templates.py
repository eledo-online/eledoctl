"""Tests for the templates CLI command."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

import eledoctl.cli.templates as templates_module
from eledoctl.cli.templates import templates
from eledoctl.config.settings import ConnectionSettings
from pyeledo import TemplateScope


def test_templates_lists_private_templates_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = ConnectionSettings(
        base_url="https://eledo.online",
        token="secret",
    )
    calls: list[TemplateScope] = []

    async def templates_impl(*, settings: ConnectionSettings, scope: TemplateScope) -> None:
        calls.append(scope)
        templates_module.click.echo('{"total": 0, "templates": []}')

    monkeypatch.setattr(
        templates_module,
        "require_connection_settings",
        lambda: settings,
    )
    monkeypatch.setattr(templates_module, "_templates", templates_impl)

    result = CliRunner().invoke(templates)

    assert result.exit_code == 0
    assert calls == [TemplateScope.PRIVATE]
    assert '"templates": []' in result.output


def test_templates_lists_public_templates_when_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = ConnectionSettings(
        base_url="https://eledo.online",
        token="secret",
    )
    calls: list[TemplateScope] = []

    async def templates_impl(*, settings: ConnectionSettings, scope: TemplateScope) -> None:
        calls.append(scope)
        templates_module.click.echo('{"total": 0, "templates": []}')

    monkeypatch.setattr(
        templates_module,
        "require_connection_settings",
        lambda: settings,
    )
    monkeypatch.setattr(templates_module, "_templates", templates_impl)

    result = CliRunner().invoke(templates, ["--scope", "public"])

    assert result.exit_code == 0
    assert calls == [TemplateScope.PUBLIC]


def test_templates_scope_is_case_insensitive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = ConnectionSettings(
        base_url="https://eledo.online",
        token="secret",
    )
    calls: list[TemplateScope] = []

    async def templates_impl(*, settings: ConnectionSettings, scope: TemplateScope) -> None:
        calls.append(scope)

    monkeypatch.setattr(
        templates_module,
        "require_connection_settings",
        lambda: settings,
    )
    monkeypatch.setattr(templates_module, "_templates", templates_impl)

    result = CliRunner().invoke(templates, ["--scope", "PUBLIC"])

    assert result.exit_code == 0
    assert calls == [TemplateScope.PUBLIC]


def test_templates_requires_connection_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_error() -> ConnectionSettings:
        raise templates_module.click.ClickException("No Eledo credentials found. Run `eledoctl login` first.")

    monkeypatch.setattr(templates_module, "require_connection_settings", raise_error)

    result = CliRunner().invoke(templates)

    assert result.exit_code != 0
    assert "No Eledo credentials found." in result.output

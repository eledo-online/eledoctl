"""Tests for the login CLI command."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

import eledoctl.cli.login as login_module
from eledoctl.cli.login import login
from eledoctl.config.settings import ConnectionSettings
from pyeledo import EledoApiError, EledoAuthenticationError, Profile


def test_login_opens_browser_prompts_for_token_and_saves_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened_urls: list[str] = []
    saved_settings: list[ConnectionSettings] = []

    async def validate_token(settings: ConnectionSettings) -> Profile:
        assert settings == ConnectionSettings(
            base_url="https://eledo.online",
            token="secret-token",
        )
        return Profile(account="user@example.com")

    monkeypatch.setattr(
        login_module.webbrowser,
        "open",
        lambda url, new=0: opened_urls.append(url) or True,
    )
    monkeypatch.setattr(login_module, "_validate_token", validate_token)
    monkeypatch.setattr(
        login_module,
        "save_connection_settings",
        lambda settings: saved_settings.append(settings),
    )

    result = CliRunner().invoke(login, input="secret-token\n")

    assert result.exit_code == 0
    assert opened_urls == ["https://eledo.online/app/login/start"]
    assert saved_settings == [
        ConnectionSettings(
            base_url="https://eledo.online",
            token="secret-token",
        )
    ]
    assert "Authenticated as user@example.com." in result.output


def test_login_normalizes_custom_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened_urls: list[str] = []
    saved_settings: list[ConnectionSettings] = []

    async def validate_token(settings: ConnectionSettings) -> Profile:
        return Profile(account="user@example.com")

    monkeypatch.setattr(
        login_module.webbrowser,
        "open",
        lambda url, new=0: opened_urls.append(url) or True,
    )
    monkeypatch.setattr(login_module, "_validate_token", validate_token)
    monkeypatch.setattr(
        login_module,
        "save_connection_settings",
        lambda settings: saved_settings.append(settings),
    )

    result = CliRunner().invoke(
        login,
        ["--base-url", "https://example.eledo.local/"],
        input="secret-token\n",
    )

    assert result.exit_code == 0
    assert opened_urls == ["https://example.eledo.local/app/login/start"]
    assert saved_settings == [
        ConnectionSettings(
            base_url="https://example.eledo.local",
            token="secret-token",
        )
    ]


def test_login_warns_when_browser_cannot_be_opened(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def validate_token(settings: ConnectionSettings) -> Profile:
        return Profile(account="user@example.com")

    monkeypatch.setattr(login_module.webbrowser, "open", lambda url, new=0: False)
    monkeypatch.setattr(login_module, "_validate_token", validate_token)
    monkeypatch.setattr(login_module, "save_connection_settings", lambda settings: None)

    result = CliRunner().invoke(login, input="secret-token\n")

    assert result.exit_code == 0
    assert "The browser could not be opened automatically." in result.stderr


@pytest.mark.parametrize(
    "exception",
    [
        EledoApiError("Invalid token."),
        EledoAuthenticationError("Eledo authentication failed."),
    ],
)
def test_login_converts_authentication_errors_to_click_errors(
    monkeypatch: pytest.MonkeyPatch,
    exception: Exception,
) -> None:
    async def validate_token(settings: ConnectionSettings) -> Profile:
        raise exception

    monkeypatch.setattr(login_module.webbrowser, "open", lambda url, new=0: True)
    monkeypatch.setattr(login_module, "_validate_token", validate_token)

    result = CliRunner().invoke(login, input="bad-token\n")

    assert result.exit_code != 0
    assert "Authentication failed:" in result.output


@pytest.mark.parametrize(
    "exception",
    [
        OSError("cannot write config"),
        ValueError("invalid config"),
        json.JSONDecodeError("invalid json", "x", 0),
    ],
)
def test_login_converts_save_errors_to_click_errors(
    monkeypatch: pytest.MonkeyPatch,
    exception: Exception,
) -> None:
    async def validate_token(settings: ConnectionSettings) -> Profile:
        return Profile(account="user@example.com")

    def save_settings(settings: ConnectionSettings) -> None:
        raise exception

    monkeypatch.setattr(login_module.webbrowser, "open", lambda url, new=0: True)
    monkeypatch.setattr(login_module, "_validate_token", validate_token)
    monkeypatch.setattr(login_module, "save_connection_settings", save_settings)

    result = CliRunner().invoke(login, input="secret-token\n")

    assert result.exit_code != 0
    assert "Could not save the local configuration:" in result.output

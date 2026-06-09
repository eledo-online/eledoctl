"""Tests for shared CLI utilities."""

from __future__ import annotations

import json

import click
import pytest

import eledoctl.cli.common as common
from eledoctl.config.settings import ConnectionSettings


async def _return_value() -> int:
    return 42


def test_run_executes_async_command() -> None:
    assert common.run(_return_value()) == 42


def test_require_connection_settings_returns_loaded_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = ConnectionSettings(
        base_url="https://eledo.online",
        token="secret",
    )

    monkeypatch.setattr(
        common,
        "load_connection_settings",
        lambda: settings,
    )

    assert common.require_connection_settings() == settings


@pytest.mark.parametrize(
    ("exception", "expected_message"),
    [
        (OSError("cannot read config"), "cannot read config"),
        (ValueError("invalid config"), "invalid config"),
        (json.JSONDecodeError("invalid json", "x", 0), "invalid json"),
    ],
)
def test_require_connection_settings_converts_config_errors_to_click_exception(
    monkeypatch: pytest.MonkeyPatch,
    exception: Exception,
    expected_message: str,
) -> None:
    def raise_exception() -> ConnectionSettings:
        raise exception

    monkeypatch.setattr(
        common,
        "load_connection_settings",
        raise_exception,
    )

    with pytest.raises(click.ClickException) as exc_info:
        common.require_connection_settings()

    assert expected_message in str(exc_info.value)

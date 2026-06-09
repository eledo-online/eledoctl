"""Tests for local configuration persistence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import eledoctl.config.settings as settings_module
from eledoctl.config.settings import (
    ConnectionSettings,
    load_config,
    load_connection_settings,
    save_config,
    save_connection_settings,
)


@pytest.fixture
def isolated_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings_module, "config_dir", lambda: tmp_path)
    return tmp_path


def test_load_config_returns_empty_object_when_file_does_not_exist(
    isolated_config_dir: Path,
) -> None:
    assert load_config() == {}


def test_load_config_reads_json_object(isolated_config_dir: Path) -> None:
    config_path = isolated_config_dir / settings_module.CONFIG_FILE
    config_path.write_text('{"default": {"base_url": "https://eledo.online"}}', encoding="utf-8")

    assert load_config() == {
        "default": {
            "base_url": "https://eledo.online",
        }
    }


def test_load_config_rejects_json_array(isolated_config_dir: Path) -> None:
    config_path = isolated_config_dir / settings_module.CONFIG_FILE
    config_path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="Configuration root must be a JSON object"):
        load_config()


def test_load_config_rejects_invalid_json(isolated_config_dir: Path) -> None:
    config_path = isolated_config_dir / settings_module.CONFIG_FILE
    config_path.write_text("{", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        load_config()


def test_save_config_writes_json_object(isolated_config_dir: Path) -> None:
    save_config({"default": {"base_url": "https://eledo.online", "token": "secret"}})

    config_path = isolated_config_dir / settings_module.CONFIG_FILE
    assert json.loads(config_path.read_text(encoding="utf-8")) == {
        "default": {
            "base_url": "https://eledo.online",
            "token": "secret",
        }
    }


def test_load_connection_settings_returns_default_connection(
    isolated_config_dir: Path,
) -> None:
    save_config({"default": {"base_url": "https://eledo.online", "token": "secret"}})

    assert load_connection_settings() == ConnectionSettings(
        base_url="https://eledo.online",
        token="secret",
    )


def test_load_connection_settings_rejects_missing_default(
    isolated_config_dir: Path,
) -> None:
    save_config({})

    with pytest.raises(ValueError, match="No Eledo credentials found"):
        load_connection_settings()


@pytest.mark.parametrize(
    "config",
    [
        {"default": {"token": "secret"}},
        {"default": {"base_url": "", "token": "secret"}},
        {"default": {"base_url": 123, "token": "secret"}},
    ],
)
def test_load_connection_settings_rejects_invalid_base_url(
    isolated_config_dir: Path,
    config: dict,
) -> None:
    save_config(config)

    with pytest.raises(ValueError, match="Stored Eledo base URL is missing or invalid"):
        load_connection_settings()


@pytest.mark.parametrize(
    "config",
    [
        {"default": {"base_url": "https://eledo.online"}},
        {"default": {"base_url": "https://eledo.online", "token": ""}},
        {"default": {"base_url": "https://eledo.online", "token": 123}},
    ],
)
def test_load_connection_settings_rejects_invalid_token(
    isolated_config_dir: Path,
    config: dict,
) -> None:
    save_config(config)

    with pytest.raises(ValueError, match="Stored Eledo API token is missing or invalid"):
        load_connection_settings()


def test_save_connection_settings_normalizes_base_url(
    isolated_config_dir: Path,
) -> None:
    save_connection_settings(
        ConnectionSettings(
            base_url="https://eledo.online/",
            token="secret",
        )
    )

    assert load_connection_settings() == ConnectionSettings(
        base_url="https://eledo.online",
        token="secret",
    )

"""Local configuration persistence for eledoctl."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir

from pyeledo.types import JsonObject, JsonValue

APP_NAME = "eledoctl"
CONFIG_FILE = "config.json"


def config_dir() -> Path:
    """Return user configuration directory."""
    path = Path(user_config_dir(APP_NAME))
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    """Return user configuration file path."""
    return config_dir() / CONFIG_FILE


def load_config() -> JsonObject:
    """Load local configuration."""
    path = config_path()

    if not path.exists():
        return {}

    data: JsonValue = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        raise ValueError("Configuration root must be a JSON object")

    return data


def save_config(config: dict[str, Any]) -> None:
    """Save local configuration."""
    config_path().write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8")


def save_token(*, base_url: str, token: str) -> None:
    """Persist default Eledo token.

    This is a simple first implementation. OS keychain support may be added later.
    """
    config = load_config()
    config["default"] = {"base_url": base_url, "token": token}
    save_config(config)

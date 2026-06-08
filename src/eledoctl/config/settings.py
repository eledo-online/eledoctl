"""Local configuration persistence for eledoctl."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import click
from platformdirs import user_config_path

from pyeledo.types import JsonObject, JsonValue

APP_NAME = "eledoctl"
CONFIG_FILE = "config.json"

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ConnectionSettings:
    base_url: str
    token: str

def load_connection_settings() -> ConnectionSettings:
    """Load the default persisted Eledo connection settings."""
    config = load_config()
    default = config.get("default")

    if not isinstance(default, dict):
        raise ValueError("No Eledo credentials found. Run `eledoctl login` first.")

    base_url = default.get("base_url")
    token = default.get("token")

    if not isinstance(base_url, str) or not base_url:
        raise ValueError("Stored Eledo base URL is missing or invalid.")

    if not isinstance(token, str) or not token:
        raise ValueError("Stored Eledo API token is missing or invalid.")

    return ConnectionSettings(
        base_url=base_url,
        token=token,
    )

def config_dir() -> Path:
    """Return the user configuration directory."""
    path = user_config_path(APP_NAME, ensure_exists=True)

    if os.name == "posix":
        path.chmod(0o700)

    return path


def config_path() -> Path:
    """Return the local configuration file path."""
    return config_dir() / CONFIG_FILE


def load_config() -> JsonObject:
    """Load the local eledoctl configuration."""
    path = config_path()

    if not path.exists():
        return {}

    data: JsonValue = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        raise ValueError("Configuration root must be a JSON object.")

    return data


def save_config(config: JsonObject) -> None:
    """Persist the local configuration atomically."""
    destination = config_path()

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary_file:
        json.dump(config, temporary_file, indent=2, sort_keys=True)
        temporary_file.write("\n")
        temporary_path = Path(temporary_file.name)

    if os.name == "posix":
        temporary_path.chmod(0o600)

    temporary_path.replace(destination)


def save_token(*, base_url: str, token: str) -> None:
    """Persist the default Eledo connection and API token."""
    config = load_config()
    config["default"] = {
        "base_url": base_url.rstrip("/"),
        "token": token,
    }
    save_config(config)
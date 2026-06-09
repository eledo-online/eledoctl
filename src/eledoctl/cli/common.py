"""Shared CLI utilities."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Coroutine
from typing import Any

import click

from eledoctl.config.settings import ConnectionSettings, load_connection_settings


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run an asynchronous command implementation."""
    return asyncio.run(coro)


def require_connection_settings() -> ConnectionSettings:
    """Load persisted connection settings or raise a user-facing CLI error."""
    try:
        return load_connection_settings()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise click.ClickException(str(exc)) from exc

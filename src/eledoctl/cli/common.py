"""Shared CLI utilities."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

DEFAULT_BASE_URL = "https://eledo.online"


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run an asynchronous command implementation."""
    return asyncio.run(coro)

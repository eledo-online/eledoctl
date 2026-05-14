from __future__ import annotations

import httpx
import pytest


@pytest.fixture
def mock_transport():
    def _make(handler):
        return httpx.MockTransport(handler)

    return _make


@pytest.fixture
def json_response():
    def _make(status_code: int = 200, payload: dict | None = None) -> httpx.Response:
        return httpx.Response(status_code, json=payload or {})

    return _make

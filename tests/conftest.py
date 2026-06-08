"""Fixtures for Cardinal CLiC tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

# Make the bundled `custom_components` and `fake` packages importable.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fake.server import FakeState, build_app  # noqa: E402

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the bundled custom_components/clic."""
    yield


@pytest.fixture(autouse=True)
def _enable_socket(socket_enabled):
    """Allow real sockets so the integration can hit the local fake server."""
    yield


@pytest.fixture
def fake_state() -> FakeState:
    """A fresh 4-channel fake controller (matches the 3-4 zone install)."""
    return FakeState.with_channels(4)


@pytest.fixture
async def fake_server(fake_state: FakeState):
    """Run the fake HC-108 on a real local TCP port."""
    app: web.Application = build_app(fake_state)
    server = TestServer(app, host="127.0.0.1")
    await server.start_server()
    yield server
    await server.close()

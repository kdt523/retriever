from __future__ import annotations

import socket
from collections.abc import Iterator
from typing import Any

import pytest

_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def _is_loopback(address: Any) -> bool:
    host = address[0] if isinstance(address, tuple) and address else address
    return isinstance(host, str) and host in _LOOPBACK


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Tests never hit the network: any outbound connect fails loudly.

    Loopback stays allowed: asyncio on Windows opens a local socket pair for its event loop
    (used by Streamlit's AppTest), which is not network access.
    """
    real_connect = socket.socket.connect
    real_create = socket.create_connection

    def guarded_connect(self: socket.socket, address: Any) -> Any:
        if _is_loopback(address):
            return real_connect(self, address)
        raise RuntimeError(f"network access is disabled in tests: {address!r}")

    def guarded_create(address: Any, *args: Any, **kwargs: Any) -> Any:
        if _is_loopback(address):
            return real_create(address, *args, **kwargs)
        raise RuntimeError(f"network access is disabled in tests: {address!r}")

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "create_connection", guarded_create)
    yield

from __future__ import annotations

import socket
from collections.abc import Iterator
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Tests never hit the network: any outbound connect fails loudly."""

    def guard(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("network access is disabled in tests")

    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket, "create_connection", guard)
    yield

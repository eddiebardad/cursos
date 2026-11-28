from __future__ import annotations

import socket
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def offline_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    def resolve_public_test_host(
        host: str,
        port: int | str | None,
        *args: Any,
        **kwargs: Any,
    ) -> list[tuple[Any, ...]]:
        del host, args, kwargs
        resolved_port = int(port) if isinstance(port, (int, str)) else 443
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("93.184.216.34", resolved_port),
            )
        ]

    monkeypatch.setattr(socket, "getaddrinfo", resolve_public_test_host)

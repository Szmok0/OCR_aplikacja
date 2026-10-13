from __future__ import annotations

import _socket
import logging
import os
import socket
import threading

import pytest

from lokalocr import netguard
from lokalocr.netguard import NetworkBlockedError

# Documentation-only addresses (RFC 5737 / RFC 3849): never routed, and the
# guard must refuse them before any packet is sent anyway.
EXTERNAL_V4 = ("203.0.113.10", 443)
EXTERNAL_V6 = ("2001:db8::1", 443, 0, 0)
EXTERNAL_NAME = "example.com"


def _ipv6_available() -> bool:
    try:
        socket.socket(socket.AF_INET6, socket.SOCK_STREAM).close()
    except OSError:
        return False
    return True


needs_ipv6 = pytest.mark.skipif(not _ipv6_available(), reason="no IPv6 on this machine")


def test_guard_is_active_for_test_session() -> None:
    assert netguard.is_installed()


def test_connect_to_external_ip_is_blocked() -> None:
    with (
        socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s,
        pytest.raises(NetworkBlockedError),
    ):
        s.connect(EXTERNAL_V4)


def test_connect_ex_to_external_ip_is_blocked() -> None:
    with (
        socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s,
        pytest.raises(NetworkBlockedError),
    ):
        s.connect_ex(EXTERNAL_V4)


@needs_ipv6
def test_connect_to_external_ipv6_is_blocked() -> None:
    with (
        socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as s,
        pytest.raises(NetworkBlockedError),
    ):
        s.connect(EXTERNAL_V6)


def test_udp_sendto_external_is_blocked() -> None:
    with (
        socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s,
        pytest.raises(NetworkBlockedError),
    ):
        s.sendto(b"x", EXTERNAL_V4)


def test_create_connection_external_is_blocked() -> None:
    with pytest.raises(NetworkBlockedError):
        socket.create_connection((EXTERNAL_NAME, 443), timeout=1)


@pytest.mark.parametrize(
    "resolve",
    [
        lambda: socket.getaddrinfo(EXTERNAL_NAME, 443),
        lambda: socket.gethostbyname(EXTERNAL_NAME),
        lambda: socket.gethostbyname_ex(EXTERNAL_NAME),
    ],
    ids=["getaddrinfo", "gethostbyname", "gethostbyname_ex"],
)
def test_dns_resolution_of_external_name_is_blocked(resolve: object) -> None:
    with pytest.raises(NetworkBlockedError):
        resolve()  # type: ignore[operator]


def test_blocked_error_is_oserror() -> None:
    # Libraries that degrade gracefully when offline catch OSError.
    assert issubclass(NetworkBlockedError, OSError)


def test_blocked_attempt_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    with (
        caplog.at_level(logging.WARNING, logger="lokalocr.netguard"),
        pytest.raises(NetworkBlockedError),
    ):
        socket.create_connection(EXTERNAL_V4, timeout=1)
    assert any("Blocked outbound network attempt" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost"])
def test_loopback_connection_is_allowed(host: str) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        accepted: list[bytes] = []

        def accept() -> None:
            conn, _ = server.accept()
            with conn:
                accepted.append(conn.recv(16))

        t = threading.Thread(target=accept)
        t.start()
        with socket.create_connection((host, port), timeout=5) as client:
            client.sendall(b"ping")
        t.join(timeout=5)
    assert accepted == [b"ping"]


def test_socketpair_is_allowed() -> None:
    # Used internally by asyncio and Qt on Windows.
    a, b = socket.socketpair()
    with a, b:
        a.sendall(b"ok")
        assert b.recv(2) == b"ok"


@pytest.mark.parametrize(
    "host",
    [None, "localhost", "127.0.0.1", "0.0.0.0", pytest.param("::1", marks=needs_ipv6)],
)
def test_local_name_resolution_is_allowed(host: str | None) -> None:
    assert socket.getaddrinfo(host, 80, type=socket.SOCK_STREAM)


def test_offline_env_vars_are_set() -> None:
    for key, value in netguard.OFFLINE_ENV.items():
        assert os.environ.get(key) == value


@pytest.mark.usefixtures("fresh_guard")
def test_install_is_idempotent_and_uninstall_restores() -> None:
    assert not netguard.is_installed()
    assert socket.socket.connect is _socket.socket.connect

    assert netguard.install()
    patched = socket.socket.connect
    assert netguard.install()
    assert socket.socket.connect is patched

    netguard.uninstall()
    assert socket.socket.connect is _socket.socket.connect
    assert "connect" not in vars(socket.socket)


@pytest.mark.usefixtures("fresh_guard")
def test_allow_net_env_disables_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(netguard.ALLOW_NET_ENV, "1")
    assert netguard.install() is False
    assert not netguard.is_installed()
    assert socket.socket.connect is _socket.socket.connect


@pytest.mark.usefixtures("fresh_guard")
@pytest.mark.parametrize("value", ["0", "true", "yes", ""])
def test_only_exact_opt_out_value_disables_guard(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv(netguard.ALLOW_NET_ENV, value)
    assert netguard.install() is True
    assert netguard.is_installed()

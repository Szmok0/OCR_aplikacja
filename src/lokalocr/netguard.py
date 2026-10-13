"""Process-wide network guard (CLAUDE.md §6.1-6.2).

``install()`` must run at process start, before any other LokalOCR import that
could pull in third-party libraries. It:

* sets offline environment variables for libraries that honour them
  (Hugging Face Hub, Transformers, Datasets),
* patches the ``socket`` module so that only loopback / local IPC traffic is
  allowed; every other attempt raises :class:`NetworkBlockedError` and is
  logged (destination only, never document content).

Developer scripts may opt out with ``LOKALOCR_ALLOW_NET=1``. The application
itself never sets it.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import socket
import threading
from collections.abc import Callable
from typing import Any

__all__ = [
    "ALLOW_NET_ENV",
    "OFFLINE_ENV",
    "NetworkBlockedError",
    "install",
    "is_installed",
    "uninstall",
]

ALLOW_NET_ENV = "LOKALOCR_ALLOW_NET"

# Libraries that look for these read them at import time, so they are set
# before anything else gets imported.
OFFLINE_ENV: dict[str, str] = {
    "HF_HUB_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_DATASETS_OFFLINE": "1",
}

_LOCAL_HOSTNAMES = frozenset({"localhost", "localhost.localdomain", "ip6-localhost"})

_log = logging.getLogger(__name__)
_lock = threading.Lock()
# (owner, attribute name, original value, whether owner defined it itself)
_originals: list[tuple[Any, str, Any, bool]] = []


class NetworkBlockedError(OSError):
    """Raised when code tries to reach anything other than the local machine.

    Subclasses ``OSError`` so libraries that already cope with being offline
    (e.g. falling back to a local cache) keep working.
    """


def _is_local_host(host: object, *, allow_unspecified: bool = False) -> bool:
    if host is None:
        return True
    if isinstance(host, bytes):
        try:
            host = host.decode("ascii")
        except UnicodeDecodeError:
            return False
    if not isinstance(host, str):
        return False
    if host == "":
        return allow_unspecified
    name = host.strip().rstrip(".").lower()
    if name in _LOCAL_HOSTNAMES:
        return True
    # Strip IPv6 zone id ("fe80::1%eth0") before parsing.
    try:
        ip = ipaddress.ip_address(name.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_loopback or (allow_unspecified and ip.is_unspecified)


def _is_local_address(address: object) -> bool:
    # AF_UNIX paths (str / bytes) are local IPC; inet addresses are tuples.
    if isinstance(address, str | bytes):
        return True
    if isinstance(address, tuple) and address:
        return _is_local_host(address[0])
    return False


def _blocked(operation: str, target: object) -> NetworkBlockedError:
    # Destination only: no document content and no file names ever reach logs.
    _log.warning("Blocked outbound network attempt: operation=%s target=%r", operation, target)
    return NetworkBlockedError(f"LokalOCR is offline-only; blocked {operation} to {target!r}")


def _guard_connect(original: Callable[..., Any], operation: str) -> Callable[..., Any]:
    def guarded(self: socket.socket, address: Any, *args: Any, **kwargs: Any) -> Any:
        if not _is_local_address(address):
            raise _blocked(operation, address)
        return original(self, address, *args, **kwargs)

    guarded.__wrapped__ = original  # type: ignore[attr-defined]
    return guarded


def _guard_sendto(original: Callable[..., Any]) -> Callable[..., Any]:
    # sendto(data, address) or sendto(data, flags, address)
    def guarded(self: socket.socket, *args: Any) -> Any:
        if len(args) >= 2 and not _is_local_address(args[-1]):
            raise _blocked("sendto", args[-1])
        return original(self, *args)

    guarded.__wrapped__ = original  # type: ignore[attr-defined]
    return guarded


def _guard_create_connection(original: Callable[..., Any]) -> Callable[..., Any]:
    def guarded(address: Any, *args: Any, **kwargs: Any) -> Any:
        if not _is_local_address(address):
            raise _blocked("create_connection", address)
        return original(address, *args, **kwargs)

    guarded.__wrapped__ = original  # type: ignore[attr-defined]
    return guarded


def _guard_resolver(original: Callable[..., Any], operation: str) -> Callable[..., Any]:
    # Name resolution of anything but localhost would leak a DNS query.
    def guarded(host: Any, *args: Any, **kwargs: Any) -> Any:
        if not _is_local_host(host, allow_unspecified=True):
            raise _blocked(operation, host)
        return original(host, *args, **kwargs)

    guarded.__wrapped__ = original  # type: ignore[attr-defined]
    return guarded


def _patch(owner: Any, name: str, wrapper: Callable[..., Any]) -> None:
    # socket.socket inherits connect() etc. from _socket.socket; remember
    # whether the attribute was the owner's own so uninstall() restores
    # exactly the previous state.
    own = name in vars(owner)
    _originals.append((owner, name, vars(owner).get(name), own))
    setattr(owner, name, wrapper)


def is_installed() -> bool:
    return bool(_originals)


def install() -> bool:
    """Enable the guard. Returns ``False`` if disabled via ``LOKALOCR_ALLOW_NET=1``.

    Safe to call more than once.
    """
    for key, value in OFFLINE_ENV.items():
        os.environ.setdefault(key, value)

    if os.environ.get(ALLOW_NET_ENV) == "1":
        _log.warning("Network guard disabled by %s=1 (developer scripts only)", ALLOW_NET_ENV)
        return False

    with _lock:
        if _originals:
            return True
        sock_cls = socket.socket
        _patch(sock_cls, "connect", _guard_connect(sock_cls.connect, "connect"))
        _patch(sock_cls, "connect_ex", _guard_connect(sock_cls.connect_ex, "connect_ex"))
        _patch(sock_cls, "sendto", _guard_sendto(sock_cls.sendto))
        _patch(socket, "create_connection", _guard_create_connection(socket.create_connection))
        _patch(socket, "getaddrinfo", _guard_resolver(socket.getaddrinfo, "getaddrinfo"))
        _patch(socket, "gethostbyname", _guard_resolver(socket.gethostbyname, "gethostbyname"))
        _patch(
            socket,
            "gethostbyname_ex",
            _guard_resolver(socket.gethostbyname_ex, "gethostbyname_ex"),
        )
    _log.info("Network guard installed")
    return True


def uninstall() -> None:
    """Restore the original ``socket`` functions. Intended for tests only."""
    with _lock:
        for owner, name, original, own in reversed(_originals):
            if own:
                setattr(owner, name, original)
            else:
                delattr(owner, name)
        _originals.clear()

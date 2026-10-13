from __future__ import annotations

import pytest

from lokalocr import netguard


def pytest_sessionstart(session: pytest.Session) -> None:
    # The whole test suite runs offline, like the application (§6).
    netguard.install()


@pytest.fixture
def fresh_guard() -> object:
    """Give a test an uninstalled guard and reinstall it afterwards."""
    netguard.uninstall()
    yield
    netguard.uninstall()
    netguard.install()

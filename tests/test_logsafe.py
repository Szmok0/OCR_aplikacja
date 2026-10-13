from __future__ import annotations

import logging

import pytest

from lokalocr.logsafe import log_unexpected


def test_exception_message_is_not_logged(caplog: pytest.LogCaptureFixture) -> None:
    secret = "C:/Users/jan/umowa_poufna.pdf Zażółć PESEL 00000000000"
    try:
        raise FileNotFoundError(secret)
    except FileNotFoundError as exc:
        with caplog.at_level(logging.ERROR):
            log_unexpected(logging.getLogger("t"), exc, "test")
    text = caplog.text
    assert "FileNotFoundError" in text
    assert "test_logsafe.py" in text
    assert "umowa" not in text and "PESEL" not in text

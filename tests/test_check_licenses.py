from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_licenses.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_licenses", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cl = _load()


@pytest.mark.parametrize(
    ("expr", "package"),
    [
        ("MIT", "anything"),
        ("Apache-2.0", "anything"),
        ("BSD-3-Clause OR GPL-2.0-only", "anything"),
        ("(MIT AND BSD-3-Clause)", "anything"),
        ("LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only", "PySide6"),
        ("LGPL-3.0-only", "shiboken6"),
    ],
)
def test_allowed(expr: str, package: str) -> None:
    assert cl.expression_allowed(expr, package)


@pytest.mark.parametrize(
    ("expr", "package"),
    [
        ("AGPL-3.0-only", "pymupdf"),
        ("GPL-3.0-only", "anything"),
        ("LGPL-3.0-only", "some-other-lib"),
        ("MIT AND GPL-3.0-only", "anything"),
        ("UNKNOWN", "anything"),
        ("Proprietary", "anything"),
    ],
)
def test_rejected(expr: str, package: str) -> None:
    assert not cl.expression_allowed(expr, package)


def test_runtime_closure_excludes_dev_extra() -> None:
    names = {cl.normalize_name(d.metadata["Name"]) for d in cl.runtime_closure()}
    assert not names & {"pytest", "ruff", "mypy", "pre-commit"}


def test_current_runtime_dependencies_pass() -> None:
    assert all(v.ok for v in cl.check()), [v for v in cl.check() if not v.ok]


@pytest.mark.parametrize(
    ("expr", "package"),
    [
        ("Apache-2.0 AND Apache-2.0 WITH LLVM-exception AND BSL-1.0 AND MIT", "torch"),
        ("Apache-2.0 AND CNRI-Python", "regex"),
    ],
)
def test_allowed_with_exceptions(expr: str, package: str) -> None:
    assert cl.expression_allowed(expr, package)


def test_extras_markers_are_parsed() -> None:
    match = cl._REQ_NAME.match("docling-slim[standard, format-pdf]==2.1; extra == 'x'")
    assert match is not None and match.group(1) == "docling-slim"
    assert cl._EXTRA_MARKER.findall("extra == 'asr' or extra == \"all\"") == ["asr", "all"]

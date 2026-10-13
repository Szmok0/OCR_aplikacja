"""Static check that application code never imports network libraries (§6.3).

Complements ruff's banned-api rule (configured in pyproject.toml) so the
guarantee holds even if lint is skipped.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"

BANNED_MODULES = frozenset(
    {
        "requests",
        "httpx",
        "urllib3",
        "aiohttp",
        "urllib.request",
        "http.client",
    }
)


def _is_banned(module: str) -> bool:
    return any(module == b or module.startswith(b + ".") for b in BANNED_MODULES)


def _imported_modules(tree: ast.AST) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.append((node.lineno, node.module))
            # "from urllib import request" / "from http import client"
            found.extend((node.lineno, f"{node.module}.{alias.name}") for alias in node.names)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute | ast.Name)
            and (node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id)
            in {"import_module", "__import__"}
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            found.append((node.lineno, node.args[0].value))
    return found


def _violations(source: str, name: str = "<test>") -> list[str]:
    tree = ast.parse(source, filename=name)
    return [f"{name}:{line}: {mod}" for line, mod in _imported_modules(tree) if _is_banned(mod)]


def test_src_has_python_files() -> None:
    assert list(SRC.rglob("*.py")), "expected application sources under src/"


def test_no_network_imports_in_src() -> None:
    violations: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        violations += _violations(path.read_text(encoding="utf-8"), str(path.relative_to(SRC)))
    assert not violations, "Banned network imports found:\n" + "\n".join(violations)


@pytest.mark.parametrize(
    "source",
    [
        "import requests",
        "import requests.adapters",
        "from httpx import Client",
        "import urllib3 as u",
        "import aiohttp",
        "import urllib.request",
        "from urllib import request",
        "from urllib.request import urlopen",
        "from http import client",
        "import importlib\nimportlib.import_module('requests')",
        "__import__('httpx')",
    ],
)
def test_checker_detects_banned_import(source: str) -> None:
    assert _violations(source)


@pytest.mark.parametrize(
    "source",
    [
        "import urllib.parse",
        "from urllib.parse import quote",
        "from http import HTTPStatus",
        "import socket",
        "from . import requests",
    ],
)
def test_checker_allows_harmless_imports(source: str) -> None:
    assert not _violations(source)

"""Run all local quality checks, the same as CI: ``python scripts/check.py``.

Cross-platform replacement for ``make check`` (the main target is Windows).
"""

from __future__ import annotations

import os
import subprocess
import sys

STEPS: list[tuple[str, list[str]]] = [
    ("ruff lint", [sys.executable, "-m", "ruff", "check", "."]),
    ("ruff format", [sys.executable, "-m", "ruff", "format", "--check", "."]),
    ("mypy", [sys.executable, "-m", "mypy"]),
    # The primary target is Windows; catch platform-specific typing on any OS.
    ("mypy (win32)", [sys.executable, "-m", "mypy", "--platform", "win32"]),
    ("pytest", [sys.executable, "-m", "pytest"]),
    ("licenses", [sys.executable, "scripts/check_licenses.py"]),
]


def main() -> int:
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    env.pop("LOKALOCR_ALLOW_NET", None)
    failed = []
    for name, cmd in STEPS:
        print(f"\n=== {name} ===", flush=True)
        if subprocess.run(cmd, env=env, check=False).returncode != 0:
            failed.append(name)
    if failed:
        print(f"\nFAILED: {', '.join(failed)}")
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

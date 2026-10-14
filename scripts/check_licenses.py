"""Check licenses of LokalOCR's runtime dependencies (CLAUDE.md §0.4, §11).

Walks the installed dependency closure of the ``lokalocr`` distribution
(runtime requirements only, no ``dev`` extra) and fails if any package has a
license outside the allowlist. LGPL is accepted only for the dynamically
linked Qt bindings listed in ``LGPL_ALLOWED``.

Usage: ``python scripts/check_licenses.py [--extras NAME ...]``
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from importlib import metadata

ROOT_DIST = "lokalocr"

# SPDX identifiers accepted for any dependency.
PERMISSIVE = frozenset(
    {
        "MIT",
        "MIT-0",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "Apache-2.0",
        "MPL-2.0",
        "ISC",
        "PSF-2.0",
        "Python-2.0",
        "Unlicense",
        "0BSD",
        "HPND",
        "MIT-CMU",  # Pillow
        "BSL-1.0",  # Boost (parts of torch)
        "CNRI-Python",  # regex (old Python licence, permissive)
        "Zlib",
        "CC0-1.0",  # numpy (bundled pieces)
    }
)

LGPL = frozenset({"LGPL-3.0-only", "LGPL-3.0-or-later", "LGPL-2.1-only", "LGPL-2.1-or-later"})

# LGPL only for dynamically linked libraries (§0.4).
LGPL_ALLOWED = frozenset({"pyside6", "pyside6-essentials", "pyside6-addons", "shiboken6"})

# Packages whose metadata is missing or wrong, verified by hand.
# Each entry: normalized name -> SPDX expression, with a comment on the source.
OVERRIDES: dict[str, str] = {
    # Metadata only has free text "BSD-3-Clause, Apache-2.0, dependency licenses".
    # pypdfium2 itself is Apache-2.0 OR BSD-3-Clause; the bundled PDFium build
    # licenses (BUILD_LICENSES/: pdfium, freetype, libjpeg-turbo, libpng, zlib,
    # lcms, openjpeg, icu, abseil, agg, fast_float, simdutf, llvm-libc) were
    # checked by hand in 5.14.0 and are all permissive.
    "pypdfium2": "Apache-2.0 OR BSD-3-Clause",
}

_CLASSIFIER_TO_SPDX = {
    "MIT License": "MIT",
    "MIT No Attribution License (MIT-0)": "MIT-0",
    "BSD License": "BSD-3-Clause",
    "Apache Software License": "Apache-2.0",
    "Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "ISC License (ISCL)": "ISC",
    "Python Software Foundation License": "PSF-2.0",
    "The Unlicense (Unlicense)": "Unlicense",
    "Historical Permission Notice and Disclaimer (HPND)": "HPND",
    "GNU Lesser General Public License v3 (LGPLv3)": "LGPL-3.0-only",
    "GNU Lesser General Public License v3 or later (LGPLv3+)": "LGPL-3.0-or-later",
    "GNU Lesser General Public License v2 or later (LGPLv2+)": "LGPL-2.1-or-later",
    "GNU General Public License (GPL)": "GPL",
    "GNU General Public License v2 (GPLv2)": "GPL-2.0-only",
    "GNU General Public License v3 (GPLv3)": "GPL-3.0-only",
    "GNU Affero General Public License v3": "AGPL-3.0-only",
}

_FREE_TEXT_TO_SPDX = {
    "mit": "MIT",
    "mit license": "MIT",
    "bsd": "BSD-3-Clause",
    "bsd license": "BSD-3-Clause",
    "new bsd": "BSD-3-Clause",
    "bsd-3-clause": "BSD-3-Clause",
    "3-clause bsd": "BSD-3-Clause",
    "bsd-2-clause": "BSD-2-Clause",
    "apache 2.0": "Apache-2.0",
    "apache 2.0 license": "Apache-2.0",
    "apache license": "Apache-2.0",
    "apache-2.0": "Apache-2.0",
    "apache license 2.0": "Apache-2.0",
    "apache license, version 2.0": "Apache-2.0",
    "apache software license": "Apache-2.0",
    "mpl-2.0": "MPL-2.0",
    "mpl 2.0": "MPL-2.0",
    "isc": "ISC",
    "isc license": "ISC",
    "psf": "PSF-2.0",
    "psf-2.0": "PSF-2.0",
}


def normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


@dataclass(frozen=True)
class Verdict:
    package: str
    license: str
    ok: bool


def _split_top_level(expr: str, op: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    tokens = re.split(r"(\(|\)|\s+)", expr)
    for tok in tokens:
        if tok == "(":
            depth += 1
        elif tok == ")":
            depth -= 1
        if depth == 0 and tok == op:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(tok)
    parts.append("".join(current).strip())
    return [p for p in parts if p]


def _strip_parens(expr: str) -> str:
    expr = expr.strip()
    while expr.startswith("(") and expr.endswith(")"):
        inner = expr[1:-1]
        if inner.count("(") != inner.count(")"):
            break
        expr = inner.strip()
    return expr


def expression_allowed(expr: str, package: str) -> bool:
    """Evaluate a (simple) SPDX expression against the allowlist."""
    expr = _strip_parens(expr)
    alternatives = _split_top_level(expr, "OR")
    if len(alternatives) > 1:
        return any(expression_allowed(a, package) for a in alternatives)
    required = _split_top_level(expr, "AND")
    if len(required) > 1:
        return all(expression_allowed(r, package) for r in required)
    # "Apache-2.0 WITH LLVM-exception": an exception only adds permissions.
    spdx = expr.split(" WITH ", 1)[0].strip().removesuffix("+")
    if spdx in PERMISSIVE:
        return True
    return spdx in LGPL and normalize_name(package) in LGPL_ALLOWED


def _first(dist: metadata.Distribution, field: str) -> str | None:
    values = dist.metadata.get_all(field)
    return str(values[0]) if values else None


def license_of(dist: metadata.Distribution) -> str:
    """Best-effort SPDX expression for an installed distribution."""
    name = normalize_name(dist.metadata["Name"])
    if name in OVERRIDES:
        return OVERRIDES[name]
    expression = _first(dist, "License-Expression")
    if expression:
        return expression
    spdx_from_classifiers = [
        _CLASSIFIER_TO_SPDX.get(c.split(" :: ")[-1], c.split(" :: ")[-1])
        for c in dist.metadata.get_all("Classifier") or []
        if c.startswith("License :: ")
    ]
    # "License :: OSI Approved" alone carries no information.
    spdx_from_classifiers = [s for s in spdx_from_classifiers if s != "OSI Approved"]
    if spdx_from_classifiers:
        # Multiple classifiers mean the user may pick one.
        return " OR ".join(sorted(set(spdx_from_classifiers)))
    free_text = (_first(dist, "License") or "").strip()
    first_line = free_text.splitlines()[0].strip().lower() if free_text else ""
    return _FREE_TEXT_TO_SPDX.get(first_line, free_text.splitlines()[0] if free_text else "UNKNOWN")


_REQ_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[([^\]]*)\])?")
_EXTRA_MARKER = re.compile(r"\bextra\s*==\s*['\"]([^'\"]+)['\"]")


def _norm_extra(extra: str) -> str:
    return re.sub(r"[-_.]+", "-", extra.strip()).lower()


def runtime_closure(
    root: str = ROOT_DIST, extras: frozenset[str] = frozenset()
) -> list[metadata.Distribution]:
    """Installed runtime dependencies of ``root`` (transitively).

    Extras are followed only where a parent requests them (``pkg[extra]``);
    the root's own optional extras (e.g. ``dev``) are not part of the closure.
    """
    seen: dict[str, metadata.Distribution] = {}
    done: set[tuple[str, str]] = set()  # (package, extra or "")
    stack: list[tuple[str, frozenset[str]]] = [(root, frozenset(_norm_extra(e) for e in extras))]
    while stack:
        raw_name, extras = stack.pop()
        name = normalize_name(raw_name)
        todo = {""} | set(extras)
        todo -= {e for (n, e) in done if n == name}
        if not todo:
            continue
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            # Platform-specific requirement that is not installed here.
            continue
        seen[name] = dist
        done.update((name, e) for e in todo)
        for req in dist.requires or []:
            requirement, _, marker = req.partition(";")
            marker_extras = {_norm_extra(e) for e in _EXTRA_MARKER.findall(marker)}
            if marker_extras and not (marker_extras & todo):
                continue
            if not marker_extras and "" not in todo:
                continue  # base requirements were handled on an earlier visit
            match = _REQ_NAME.match(requirement)
            if match:
                wanted = frozenset(
                    _norm_extra(e) for e in (match.group(2) or "").split(",") if e.strip()
                )
                stack.append((match.group(1), wanted))
    seen.pop(normalize_name(root), None)
    return sorted(seen.values(), key=lambda d: normalize_name(d.metadata["Name"]))


def check(root: str = ROOT_DIST, extras: frozenset[str] = frozenset()) -> list[Verdict]:
    verdicts = []
    for dist in runtime_closure(root, extras):
        name = dist.metadata["Name"]
        lic = license_of(dist)
        verdicts.append(Verdict(name, lic, expression_allowed(lic, name)))
    return verdicts


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Check runtime dependency licences.")
    parser.add_argument(
        "--extras", nargs="*", default=[],
        help="also check these optional extras of lokalocr (e.g. dev)",
    )  # fmt: skip
    args = parser.parse_args(argv)
    try:
        metadata.distribution(ROOT_DIST)
    except metadata.PackageNotFoundError:
        print(f"{ROOT_DIST} is not installed; run `pip install -e .` first.", file=sys.stderr)
        return 2
    verdicts = check(extras=frozenset(args.extras))
    for v in verdicts:
        print(f"{'ok ' if v.ok else 'BAD'}  {v.package:<30} {v.license}")
    bad = [v for v in verdicts if not v.ok]
    if bad:
        print(
            f"\n{len(bad)} dependency license(s) not allowed (CLAUDE.md §0.4). "
            "Verify by hand and add to OVERRIDES only if the metadata is wrong.",
            file=sys.stderr,
        )
        return 1
    print(f"\nAll {len(verdicts)} runtime dependencies have allowed licenses.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

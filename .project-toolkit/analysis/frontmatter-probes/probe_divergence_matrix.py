#!/usr/bin/env python3
"""Divergence matrix for the four frontmatter parsers named in issue #5275.

Runs each parser plus ``python-frontmatter`` over ten fence shapes and prints an
agreement table. Evidence for `.project-toolkit/analysis/frontmatter-parser-build-vs-buy.md`.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

import frontmatter  # noqa: E402
from frontmatter.default_handlers import YAMLHandler  # noqa: E402

from scripts.validation.yaml_utils import _parse_yaml_frontmatter  # noqa: E402

# Quoted verbatim from build/scripts/generate_adr_index.py:84.
_FRONTMATTER_RE = re.compile(r"^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$")


def _load(name: str, relative: str) -> ModuleType:
    """Import a module by path so skill scripts outside the package tree load."""
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {relative}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


detect_adr = _load("_probe_detect_adr", ".claude/skills/adr-review/scripts/detect_adr_changes.py")
adr_lifecycle = _load("_probe_adr_lifecycle", "scripts/validation/check_adr_lifecycle.py")

BODY = "id: ADR-999\nstatus: accepted"

CASES: dict[str, str] = {
    "baseline (clean)": f"---\n{BODY}\n---\nBody.\n",
    "close fence + 1 space": f"---\n{BODY}\n--- \nBody.\n",
    "close fence + trailing text": f"---\n{BODY}\n--- nope\nBody.\n",
    "close fence 4 dashes": f"---\n{BODY}\n----\nBody.\n",
    "CRLF line endings": f"---\r\n{BODY}\r\n---\r\nBody.\r\n",
    "open fence + 1 space": f"--- \n{BODY}\n---\nBody.\n",
    "no closing fence": f"---\n{BODY}\nBody.\n",
    "close fence, EOF no newline": f"---\n{BODY}\n---",
    "close fence + tab": f"---\n{BODY}\n---\t\nBody.\n",
    "BOM before open fence": f"﻿---\n{BODY}\n---\nBody.\n",
}


def _verdict(parse: Callable[[str], object], text: str) -> str:
    """Normalise any parser's outcome to OK / None / RAISE for the table."""
    try:
        result = parse(text)
    except Exception as exc:
        return f"RAISE {type(exc).__name__}"
    if isinstance(result, tuple):
        return "OK" if result and result[0] else "None"
    return "OK" if result else "None"


PARSERS: dict[str, Callable[[str], object]] = {
    "yaml_utils": _parse_yaml_frontmatter,
    "adr_lifecycle": adr_lifecycle._split_frontmatter,
    "detect_adr": detect_adr._split_frontmatter,
    "adr_index_re": _FRONTMATTER_RE.match,
    "python-frontmatter": lambda text: frontmatter.loads(text).metadata,
}


def main() -> int:
    widths = {name: max(len(name), 10) for name in PARSERS}
    header = "| " + f"{'case':<30}" + " | "
    header += " | ".join(f"{name:<{widths[name]}}" for name in PARSERS) + " |"
    print(header)
    print("|" + "-" * 32 + "|" + "|".join("-" * (widths[n] + 2) for n in PARSERS) + "|")
    for case, text in CASES.items():
        row = " | ".join(f"{_verdict(p, text):<{widths[n]}}" for n, p in PARSERS.items())
        print(f"| {case:<30} | {row} |")

    print()
    print(f"YAMLHandler.FM_BOUNDARY: {YAMLHandler.FM_BOUNDARY.pattern!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

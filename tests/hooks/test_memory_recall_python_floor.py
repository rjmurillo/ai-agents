#!/usr/bin/env python3
"""The shipped recall package parses and runs at the launcher's Python 3.10 floor.

The plugin launcher accepts any interpreter >= 3.10 (``hooks.json``), so the
shipped ``memory_enhancement`` tree must avoid 3.11+ names and syntax. A scan
over the shipped tree is deterministic; the 3.10 runtime variant lives in
``test_plugin_memory_recall_runtime.py``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SHIPPED = REPO_ROOT / "src" / "claude" / "lib" / "memory_enhancement"
FLOOR = (3, 10)

# Names added after 3.10: (module, name) pairs importable with `from m import n`.
_NEW_IMPORTS = {
    ("datetime", "UTC"),
    ("typing", "Self"),
    ("typing", "LiteralString"),
    ("typing", "Never"),
    ("typing", "assert_never"),
    ("enum", "StrEnum"),
    ("asyncio", "TaskGroup"),
    ("asyncio", "timeout"),
}
_NEW_MODULES = {"tomllib"}
_NEW_ATTRIBUTES = {"UTC", "StrEnum", "TaskGroup", "ExceptionGroup"}


def findings(source: str, filename: str = "<memory>") -> list[str]:
    """Return one line per 3.11+ construct in *source*."""
    tree = ast.parse(source, filename=filename, feature_version=FLOOR)
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            found.extend(
                f"{filename}:{node.lineno} from {node.module} import {alias.name}"
                for alias in node.names
                if (node.module, alias.name) in _NEW_IMPORTS
            )
        elif isinstance(node, ast.Import):
            found.extend(
                f"{filename}:{node.lineno} import {alias.name}"
                for alias in node.names
                if alias.name in _NEW_MODULES
            )
        elif isinstance(node, ast.Attribute) and node.attr in _NEW_ATTRIBUTES:
            found.append(f"{filename}:{node.lineno} .{node.attr}")
        elif isinstance(node, ast.TryStar):
            found.append(f"{filename}:{node.lineno} except*")
    return found


def _shipped_files() -> list[Path]:
    return sorted(p for p in SHIPPED.rglob("*.py") if "__pycache__" not in p.parts)


def test_the_scan_has_files_to_scan() -> None:
    assert len(_shipped_files()) >= 10


@pytest.mark.parametrize("path", _shipped_files(), ids=lambda p: p.relative_to(SHIPPED).as_posix())
def test_shipped_module_uses_nothing_newer_than_python_310(path: Path) -> None:
    assert findings(path.read_text(encoding="utf-8"), path.name) == []


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("from datetime import UTC\n", "from datetime import UTC"),
        ("import datetime\nx = datetime.UTC\n", ".UTC"),
        ("from enum import StrEnum\n", "from enum import StrEnum"),
        ("import tomllib\n", "import tomllib"),
    ],
)
def test_the_scan_flags_what_it_exists_to_catch(source: str, expected: str) -> None:
    """Negative control: a clean result above is not a scanner that sees nothing."""
    assert any(expected in line for line in findings(source))


def test_the_scan_accepts_timezone_utc() -> None:
    assert (
        findings("from datetime import datetime, timezone\nx = datetime.now(timezone.utc)\n") == []
    )


def test_the_source_tree_matches_the_shipped_tree_on_the_same_names() -> None:
    """The shipped copy is rendered from scripts/, so scanning the source agrees."""
    source = REPO_ROOT / "scripts" / "memory_enhancement"
    for path in sorted(p for p in source.rglob("*.py") if "__pycache__" not in p.parts):
        assert findings(path.read_text(encoding="utf-8"), path.name) == [], path

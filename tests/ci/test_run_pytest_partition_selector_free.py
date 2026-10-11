"""The partition runner has no selector import and reads no selection input.

Issue #6239 acceptance criteria covered here:

- AC1: no file imports ``scripts.test_selection``.
"""

from __future__ import annotations

import ast
from pathlib import Path

from scripts.ci import run_pytest_partition as mod

_MODULE_PATH = Path(mod.__file__)


def test_module_never_imports_the_selector() -> None:
    """AC1: the runner has no import of scripts.test_selection."""
    tree = ast.parse(_MODULE_PATH.read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            imported.append(base)
            imported.extend(f"{base}.{alias.name}" for alias in node.names)
    assert not [name for name in imported if "test_selection" in name], imported


def test_module_reads_no_selection_env_or_git() -> None:
    source = _MODULE_PATH.read_text(encoding="utf-8")
    assert "PYTEST_SELECT_" not in source
    assert "subprocess" not in source

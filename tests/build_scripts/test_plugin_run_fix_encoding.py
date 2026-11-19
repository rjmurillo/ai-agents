"""`test_plugin_run_fix.py` decodes git output as UTF-8 in every text-mode subprocess call.

The production helper ``plugin_run_fix._git`` passes ``encoding="utf-8"`` and
``errors="replace"``. A test call that passes only ``text=True`` decodes with the host
locale and fails on a platform whose default is not UTF-8.
"""

from __future__ import annotations

import ast
from pathlib import Path

TARGET = Path(__file__).with_name("test_plugin_run_fix.py")


def _text_runs_missing_an_encoding(tree: ast.AST) -> list[int]:
    """Return the line of each ``subprocess.run(..., text=True)`` call without both keywords."""
    missing: list[int] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and ast.unparse(node.func) == "subprocess.run"):
            continue
        names = {keyword.arg for keyword in node.keywords}
        if "text" in names and not {"encoding", "errors"} <= names:
            missing.append(node.lineno)
    return missing


def test_every_text_mode_subprocess_call_in_test_plugin_run_fix_names_its_encoding() -> None:
    """Without it, git output decodes with the host locale, as `fix._git` avoids."""
    tree = ast.parse(TARGET.read_text(encoding="utf-8"))
    assert _text_runs_missing_an_encoding(tree) == []


def test_the_encoding_scan_flags_a_call_that_omits_one() -> None:
    """Negative control: the scan above can fail."""
    bad = ast.parse(
        "subprocess.run(['git'], text=True)\nsubprocess.run(['git'], text=True, errors='replace')"
    )
    assert _text_runs_missing_an_encoding(bad) == [1, 2]

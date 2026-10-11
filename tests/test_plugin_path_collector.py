"""Verify ``_collect_python_files`` filters on path components, not substrings."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from test_plugin_path_resolution import _collect_python_files


# _collect_python_files filters on relative path components, not substrings.
def test_parent_dir_containing_tests_substring_does_not_hide_files(tmp_path: Path) -> None:
    root = tmp_path / "tests-root-dir"
    kept = root / "skill" / "scripts" / "a.py"
    skipped_tests = root / "tests" / "b.py"
    skipped_cache = root / "__pycache__" / "c.py"
    for f in (kept, skipped_tests, skipped_cache):
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("")

    assert _collect_python_files(root) == [kept]


def test_nested_tests_and_pycache_dirs_are_excluded(tmp_path: Path) -> None:
    kept = tmp_path / "a" / "ok.py"
    nested_tests = tmp_path / "a" / "tests" / "x.py"
    nested_cache = tmp_path / "a" / "__pycache__" / "y.py"
    for f in (kept, nested_tests, nested_cache):
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("")

    assert _collect_python_files(tmp_path) == [kept]


def test_file_named_with_tests_substring_is_kept(tmp_path: Path) -> None:
    kept = tmp_path / "latests.py"
    kept.write_text("")

    assert _collect_python_files(tmp_path) == [kept]


def test_empty_directory_returns_empty_list(tmp_path: Path) -> None:
    assert _collect_python_files(tmp_path) == []

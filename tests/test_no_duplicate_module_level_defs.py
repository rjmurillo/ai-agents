"""Gate: no two module-level test functions in the same file may share a name.

Ruff F811 is silent on underscore-prefixed names (e.g. `_setup_repo`) because
ruff's `dummy-variable-rgx` treats them as intentional discards. A duplicate
module-level helper named `_foo` silently shadows the earlier `_foo`, so the
wrong fixture is used in every test that follows the shadowing definition.

This gate walks every `.py` file under the repository's `tests/` tree and
fails if any two `FunctionDef` or `AsyncFunctionDef` nodes share a name. It
does NOT descend into classes (where test method names are scoped and
intentionally repeated across test classes), nor into `_SKIP` directories.
Restricting the root prevents ignored repository-local pytest artifacts from
entering the corpus. Read, decode, and syntax failures remain visible instead
of reducing the scan silently.

Issue: #4060. Confirmed zero duplicates in the repository when this gate was
added, so it is purely a regression guard.

Exit codes (ADR-035):
    0 - no duplicates found
    1 - one or more duplicates found
"""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TESTS_ROOT = _REPO_ROOT / "tests"
_SKIP = frozenset((".venv", "node_modules", ".git", "site-packages", "worktrees"))


def _module_level_function_names(path: Path) -> dict[str, list[int]]:
    """Return {name: [lineno, ...]} for every module-level function in path."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))

    by_name: dict[str, list[int]] = defaultdict(list)
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            by_name[node.name].append(node.lineno)
    return dict(by_name)


def collect_duplicates(root: Path) -> list[tuple[Path, str, list[int]]]:
    """Return (path, name, [lineno1, lineno2, ...]) for every duplicate."""
    results: list[tuple[Path, str, list[int]]] = []
    for py in sorted(root.rglob("*.py")):
        if any(part in _SKIP for part in py.relative_to(root).parts):
            continue
        for name, linenos in _module_level_function_names(py).items():
            if len(linenos) > 1:
                results.append((py, name, linenos))
    return results


class TestNoDuplicateModuleLevelTestFunctions:
    """Regression guard: duplicate module-level function names in tests/."""

    def test_no_duplicate_names(self) -> None:
        """Fail if any test file defines the same module-level function twice."""
        duplicates = collect_duplicates(_TESTS_ROOT)
        if not duplicates:
            return

        lines = [
            "Duplicate module-level function name(s) detected in tests/.",
            "F811 is silent on underscore-prefixed names; this gate closes the gap.",
            "",
        ]
        for path, name, linenos in sorted(duplicates):
            rel = path.relative_to(_REPO_ROOT)
            lno_str = ", ".join(str(n) for n in linenos)
            lines.append(f"  {rel}: `{name}` defined at lines {lno_str}")
        pytest.fail("\n".join(lines))


# ---------------------------------------------------------------------------
# Self-contained unit tests for the helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_returns_empty_for_clean_file(self, tmp_path: Path) -> None:
        p = tmp_path / "clean.py"
        p.write_text("def foo():\n    pass\ndef bar():\n    pass\n", encoding="utf-8")
        result = _module_level_function_names(p)
        assert result == {"foo": [1], "bar": [3]}

    def test_detects_duplicate(self, tmp_path: Path) -> None:
        p = tmp_path / "dup.py"
        p.write_text("def foo():\n    pass\ndef foo():\n    return 1\n", encoding="utf-8")
        result = _module_level_function_names(p)
        assert result == {"foo": [1, 3]}

    def test_underscore_duplicate_is_detected(self, tmp_path: Path) -> None:
        """The main motivation: underscore-prefixed names slip past F811."""
        p = tmp_path / "dup_under.py"
        p.write_text(
            "def _setup_repo(tmp_path):\n    pass\ndef _setup_repo(path):\n    return path\n",
            encoding="utf-8",
        )
        result = _module_level_function_names(p)
        assert len(result["_setup_repo"]) == 2, "_setup_repo should appear twice"

    def test_class_methods_are_ignored(self, tmp_path: Path) -> None:
        src = (
            "class TestFoo:\n    def helper(self): pass\n"
            "class TestBar:\n    def helper(self): pass\n"
        )
        p = tmp_path / "classes.py"
        p.write_text(src, encoding="utf-8")
        result = _module_level_function_names(p)
        assert result == {}, "methods inside classes must not be collected"

    def test_syntax_error_fails_closed(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.py"
        p.write_text("def f(\n", encoding="utf-8")
        with pytest.raises(SyntaxError):
            _module_level_function_names(p)

    def test_invalid_utf8_fails_closed(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.py"
        p.write_bytes(b"\xff\xfe")
        with pytest.raises(UnicodeDecodeError):
            _module_level_function_names(p)

    def test_gate_root_is_tests_directory(self) -> None:
        assert _TESTS_ROOT == _REPO_ROOT / "tests"

    def test_ignored_root_artifacts_are_outside_scan(self, tmp_path: Path) -> None:
        tests_root = tmp_path / "tests"
        tests_root.mkdir()
        (tests_root / "clean.py").write_text("def clean(): pass\n", encoding="utf-8")
        artifact = tmp_path / ".pytest_tmp"
        artifact.mkdir()
        (artifact / "bin.py").write_bytes(b"\xff\xfe")

        assert collect_duplicates(tests_root) == []

    def test_collect_duplicates_finds_nothing_in_clean_dir(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("def foo(): pass\n", encoding="utf-8")
        (tmp_path / "b.py").write_text("def foo(): pass\n", encoding="utf-8")
        # Same name in DIFFERENT files is not a duplicate.
        dups = collect_duplicates(tmp_path)
        assert dups == []

    def test_collect_duplicates_finds_intra_file_dup(self, tmp_path: Path) -> None:
        (tmp_path / "bad.py").write_text("def foo(): pass\ndef foo(): pass\n", encoding="utf-8")
        dups = collect_duplicates(tmp_path)
        assert len(dups) == 1
        assert dups[0][1] == "foo"

    def test_skips_venv(self, tmp_path: Path) -> None:
        venv = tmp_path / ".venv" / "lib"
        venv.mkdir(parents=True)
        (venv / "dup.py").write_text("def foo(): pass\ndef foo(): pass\n", encoding="utf-8")
        dups = collect_duplicates(tmp_path)
        assert dups == [], ".venv should be skipped"


# ---------------------------------------------------------------------------
# Isolating negative control: proves the gate is load-bearing
# ---------------------------------------------------------------------------


class TestIsolatingNegativeControl:
    def test_gate_catches_real_duplicate(self, tmp_path: Path) -> None:
        """Removing collect_duplicates would make this vacuously pass.

        This test constructs an intra-file duplicate and asserts that
        collect_duplicates reports it -- proving the check is not a no-op.
        """
        p = tmp_path / "bad.py"
        p.write_text("def _setup(): pass\ndef _setup(): return 1\n", encoding="utf-8")
        dups = collect_duplicates(tmp_path)
        assert len(dups) == 1, "duplicate must be reported, not silently ignored"
        assert dups[0][1] == "_setup"

    def test_gate_is_silent_on_same_name_in_different_files(self, tmp_path: Path) -> None:
        """Same name in two files is not a collision; guard must stay silent."""
        (tmp_path / "a.py").write_text("def helper(): pass\n", encoding="utf-8")
        (tmp_path / "b.py").write_text("def helper(): pass\n", encoding="utf-8")
        dups = collect_duplicates(tmp_path)
        assert dups == []

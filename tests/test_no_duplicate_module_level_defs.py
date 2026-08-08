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

import subprocess
from pathlib import Path

import pytest

from scripts.validation import check_duplicate_test_helpers as checker

_REPO_ROOT = Path(__file__).resolve().parents[1]


def collect_duplicates(repo_root: Path) -> list[tuple[Path, str, list[int]]]:
    """Return (path, name, [lineno1, lineno2, ...]) for every duplicate."""
    return [
        (path, name, [first_line, duplicate_line])
        for path, name, first_line, duplicate_line in (
            checker.find_duplicate_module_level_helpers(repo_root)
        )
    ]


class TestNoDuplicateModuleLevelTestFunctions:
    """Regression guard: duplicate module-level function names in tests/."""

    def test_no_duplicate_names(self) -> None:
        """Fail if any test file defines the same module-level function twice."""
        duplicates = collect_duplicates(_REPO_ROOT)
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
    def test_syntax_error_fails_closed(self, tmp_path: Path) -> None:
        tests = tmp_path / "tests"
        tests.mkdir()
        p = tests / "bad.py"
        p.write_text("def f(\n", encoding="utf-8")
        with pytest.raises(checker.ScanError):
            collect_duplicates(tmp_path)

    def test_invalid_utf8_fails_closed(self, tmp_path: Path) -> None:
        tests = tmp_path / "tests"
        tests.mkdir()
        p = tests / "bad.py"
        p.write_bytes(b"\xff\xfe")
        with pytest.raises(checker.ScanError):
            collect_duplicates(tmp_path)

    def test_ignored_test_artifacts_are_outside_scan(self, tmp_path: Path) -> None:
        tests_root = tmp_path / "tests"
        tests_root.mkdir()
        (tests_root / "clean.py").write_text("def clean(): pass\n", encoding="utf-8")
        artifact = tests_root / "tmp"
        artifact.mkdir()
        (artifact / "bin.py").write_bytes(b"\xff\xfe")
        (tmp_path / ".gitignore").write_text("tests/tmp/\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        subprocess.run(
            ["git", "add", ".gitignore", "tests/clean.py"], cwd=tmp_path, check=True
        )

        assert collect_duplicates(tmp_path) == []

    def test_collect_duplicates_finds_nothing_in_clean_dir(self, tmp_path: Path) -> None:
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "a.py").write_text("def foo(): pass\n", encoding="utf-8")
        (tests / "b.py").write_text("def foo(): pass\n", encoding="utf-8")
        # Same name in DIFFERENT files is not a duplicate.
        dups = collect_duplicates(tmp_path)
        assert dups == []

    def test_collect_duplicates_finds_intra_file_dup(self, tmp_path: Path) -> None:
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "bad.py").write_text(
            "def foo(): pass\ndef foo(): pass\n", encoding="utf-8"
        )
        dups = collect_duplicates(tmp_path)
        assert len(dups) == 1
        assert dups[0][1] == "foo"

    def test_skips_venv(self, tmp_path: Path) -> None:
        venv = tmp_path / "tests" / ".venv" / "lib"
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
        tests = tmp_path / "tests"
        tests.mkdir()
        p = tests / "bad.py"
        p.write_text("def _setup(): pass\ndef _setup(): return 1\n", encoding="utf-8")
        dups = collect_duplicates(tmp_path)
        assert len(dups) == 1, "duplicate must be reported, not silently ignored"
        assert dups[0][1] == "_setup"

    def test_gate_is_silent_on_same_name_in_different_files(self, tmp_path: Path) -> None:
        """Same name in two files is not a collision; guard must stay silent."""
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "a.py").write_text("def helper(): pass\n", encoding="utf-8")
        (tests / "b.py").write_text("def helper(): pass\n", encoding="utf-8")
        dups = collect_duplicates(tmp_path)
        assert dups == []

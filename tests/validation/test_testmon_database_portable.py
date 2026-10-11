"""A testmon database built in one checkout path works in another (issue #6239).

The CI seed job builds `.testmondata` on a runner and a developer's checkout
sits elsewhere, so the hook's download only helps if testmon stores paths
relative to rootdir and keys on file content, not on where the checkout lives.
This builds a database in one directory, copies the whole tree to a different
path, and runs testmon there. Nothing changed, so nothing may be selected. The
control edits a source file in the copy and requires its test to be selected,
so a testmon that ignored the database (or selected nothing ever) fails.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("testmon")

_SOURCE = "def double(value):\n    return value * 2\n"
_TEST = (
    "from calc import double\n\n\n"
    "def test_double():\n    assert double(2) == 4\n\n\n"
    "def test_double_zero():\n    assert double(0) == 0\n"
)
_UNRELATED = "def test_unrelated():\n    assert True\n"


def _write_project(root: Path) -> None:
    root.mkdir()
    (root / "calc.py").write_text(_SOURCE, encoding="utf-8")
    (root / "test_calc.py").write_text(_TEST, encoding="utf-8")
    (root / "test_unrelated.py").write_text(_UNRELATED, encoding="utf-8")
    (root / "pytest.ini").write_text("[pytest]\npythonpath = .\n", encoding="utf-8")


def _environment() -> dict[str, str]:
    kept = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("COVERAGE", "PYTEST", "XDIST"))
    }
    # The hook forces ctrace for testmon on Python 3.14; match it.
    kept["COVERAGE_CORE"] = "ctrace"
    return kept


def _testmon(root: Path) -> str:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--testmon", "-q", "-n", "0"],
        cwd=root,
        env=_environment(),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    return result.stdout + result.stderr


def _passed(output: str) -> int:
    match = re.search(r"(\d+) passed", output)
    return int(match.group(1)) if match else 0


@pytest.fixture
def two_checkouts(tmp_path: Path) -> tuple[Path, Path]:
    built = tmp_path / "ci-runner" / "work" / "repo"
    built.parent.mkdir(parents=True)
    _write_project(built)
    first = _testmon(built)
    assert _passed(first) == 3, first
    moved = tmp_path / "home" / "dev" / "worktrees" / "a-different-path"
    moved.parent.mkdir(parents=True)
    shutil.copytree(built, moved)
    return built, moved


def test_the_database_is_a_single_file(two_checkouts: tuple[Path, Path]) -> None:
    built, _moved = two_checkouts
    assert (built / ".testmondata").is_file()
    assert not (built / ".testmondata-wal").exists()


def test_a_copied_database_selects_nothing_when_nothing_changed(
    two_checkouts: tuple[Path, Path],
) -> None:
    _built, moved = two_checkouts
    output = _testmon(moved)
    assert _passed(output) == 0, output
    assert "no tests ran" in output, output


def test_a_copied_database_selects_the_tests_a_change_affects(
    two_checkouts: tuple[Path, Path],
) -> None:
    """Control: the copied database is used, so a real change selects its tests only."""
    _built, moved = two_checkouts
    (moved / "calc.py").write_text(_SOURCE + "\n\ndef triple(value):\n    return value * 3\n")
    output = _testmon(moved)
    assert _passed(output) == 2, output

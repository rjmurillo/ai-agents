"""Real ``--testmon`` processes accept and keep their own lane databases (issue #6477).

The unit tests prove the files are copied and named. This one proves testmon
2.2.0 reads a backup copy through ``TESTMON_DATAFILE``, selects nothing when
nothing changed, re-runs only that lane's tests after a change, and leaves the
base database alone.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest

from scripts.validation import testmon_lane_db

TESTS_PER_PARTITION = 5
BASE = ".testmondata"


def _env(datafile: str | None) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("PYTEST_")}
    env.pop("TESTMON_DATAFILE", None)
    env["COVERAGE_CORE"] = "ctrace"
    if datafile:
        env["TESTMON_DATAFILE"] = datafile
    return env


def _pytest(project: Path, target: str, datafile: str | None) -> str:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--testmon",
            "--testmon-forceselect",
            "-m",
            "not integration",
            "-q",
            "-o",
            "addopts=",
            target,
        ],
        cwd=project,
        env=_env(datafile),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    assert result.returncode in (0, 5), result.stdout + result.stderr
    return result.stdout


def _build_project(project: Path) -> None:
    (project / "conftest.py").write_text("")
    (project / "pkg.py").write_text("def value():\n    return 1\n")
    body = "from pkg import value\n\n" + "".join(
        f"def test_case_{index}():\n    assert value() == 1\n"
        for index in range(TESTS_PER_PARTITION)
    )
    for name in ("part_a", "part_b"):
        (project / name).mkdir()
        (project / name / f"test_{name}.py").write_text(body)


def _executions(path: Path) -> int:
    with closing(sqlite3.connect(path)) as database:
        assert database.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        return database.execute("SELECT count(*) FROM test_execution").fetchone()[0]


def test_lane_copies_select_nothing_then_rerun_only_their_own_tests(tmp_path: Path) -> None:
    pytest.importorskip("testmon")
    _build_project(tmp_path)
    _pytest(tmp_path, ".", None)  # the sequential first build
    base_before = _executions(tmp_path / BASE)
    assert base_before == 2 * TESTS_PER_PARTITION
    lanes = testmon_lane_db.prepare_lane_datafiles(tmp_path, BASE, 2)

    unchanged = [_pytest(tmp_path, "part_a", lanes[0]), _pytest(tmp_path, "part_b", lanes[1])]
    assert all("no tests ran" in output for output in unchanged), unchanged

    (tmp_path / "pkg.py").write_text("def value():\n    extra = 1\n    return 1 + extra - extra\n")
    changed = [_pytest(tmp_path, "part_a", lanes[0]), _pytest(tmp_path, "part_b", lanes[1])]

    assert all(f"{TESTS_PER_PARTITION} passed" in output for output in changed), changed
    assert _executions(tmp_path / BASE) == base_before
    for lane in lanes:
        # testmon prunes what a run did not collect, so a lane keeps its own tests.
        assert _executions(tmp_path / lane) == TESTS_PER_PARTITION

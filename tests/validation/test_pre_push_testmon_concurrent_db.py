"""Two real testmon processes can share one ``.testmondata`` (issues #6198, #6406).

Issue #6477 moved the overlapping pre-push lanes onto separate databases, because
a shared one let a lane change what another lane's workers read. This test
still guards the write path: testmon 2.2.0 writes each run in transactions on a
WAL database with a 60s busy wait, so two processes on one database neither fail
nor corrupt it. This test runs two real pytest processes with the hook's flags
against one database, repeatedly, after a change that makes both re-run and
re-record their tests. The first build is not tested here because it is not
safe (bare ``CREATE TABLE``); the hook runs it in sequence.

Without help a shared database does not keep both histories. testmon reads which
tests changed when it starts, and once collection ends it deletes each changed
test it did not collect (``sync_db_fs_tests``). A process that starts before the
other records and ends collection after it deletes the records the other just
wrote. The hook's flags load ``scripts.validation.testmon_scoped_sync`` to stop
that, so both partitions keep their records. The ordered replay of the loss is
in ``test_testmon_scoped_sync.py``.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.validation import git_hook_policy

REPO_ROOT = Path(__file__).resolve().parents[2]
TESTS_PER_PARTITION = 30
ROUNDS = 3


def _env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("PYTEST_")}
    env.pop("TESTMON_DATAFILE", None)
    env["COVERAGE_CORE"] = "ctrace"
    # The hook's flags load `scripts.validation.testmon_scoped_sync` from the repo root.
    env["PYTHONPATH"] = str(REPO_ROOT)
    return env


def _pytest(project: Path, *targets: str) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "pytest",
            *git_hook_policy._TESTMON_FLAGS,
            "-m",
            "not integration",
            "-q",
            "-o",
            "addopts=",
            *targets,
        ],
        cwd=project,
        env=_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
    )


def _build_project(project: Path) -> None:
    (project / "conftest.py").write_text("", encoding="utf-8")
    (project / "pkg.py").write_text("def value():\n    return 1\n", encoding="utf-8")
    body = "from pkg import value\n\n" + "".join(
        f"def test_case_{index}():\n    assert value() == 1\n"
        for index in range(TESTS_PER_PARTITION)
    )
    for name in ("part_a", "part_b"):
        (project / name).mkdir()
        (project / name / f"test_{name}.py").write_text(body, encoding="utf-8")


def _finish(process: subprocess.Popen[str]) -> tuple[int, str]:
    try:
        output, _ = process.communicate(timeout=120)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        raise
    return process.returncode, output


def test_concurrent_partitions_record_into_one_database(tmp_path: Path) -> None:
    pytest.importorskip("testmon")
    _build_project(tmp_path)
    code, output = _finish(_pytest(tmp_path, "part_a", "part_b"))
    assert code == 0, output

    for round_number in range(ROUNDS):
        # Same value, different code, so testmon re-selects every dependent test.
        (tmp_path / "pkg.py").write_text(
            f"def value():\n    extra = {round_number}\n    return 1 + extra - extra\n",
            encoding="utf-8",
        )
        first = _pytest(tmp_path, "part_a")
        second = _pytest(tmp_path, "part_b")
        results = [_finish(first), _finish(second)]
        assert [code for code, _ in results] == [0, 0], [output for _, output in results]

    with sqlite3.connect(tmp_path / ".testmondata") as database:
        assert database.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        recorded = database.execute("SELECT count(*) FROM test_execution").fetchone()[0]
    # The scoped sync keeps both partitions' records (issue #6406).
    assert recorded == 2 * TESTS_PER_PARTITION

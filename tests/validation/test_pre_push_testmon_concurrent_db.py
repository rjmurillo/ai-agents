"""Two real testmon processes can share one ``.testmondata`` (issue #6198).

Issue #6477 moved the overlapping pre-push lanes onto separate databases, because
a shared one let a lane change what another lane's workers read. This test
still guards the write path: testmon 2.2.0 writes each
run in transactions on a WAL database with a 60s busy wait, and the partitions
cover disjoint test names. This test runs two real ``--testmon`` pytest
processes against one database, repeatedly, after a change that makes both
re-run and re-record their tests. The first build is not tested here because it
is not safe (bare ``CREATE TABLE``); the hook runs it in sequence.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

TESTS_PER_PARTITION = 30
ROUNDS = 3


def _env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("PYTEST_")}
    env.pop("TESTMON_DATAFILE", None)
    env["COVERAGE_CORE"] = "ctrace"
    return env


def _pytest(project: Path, *targets: str) -> subprocess.Popen[str]:
    return subprocess.Popen(
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
    (project / "conftest.py").write_text("")
    (project / "pkg.py").write_text("def value():\n    return 1\n")
    body = "from pkg import value\n\n" + "".join(
        f"def test_case_{index}():\n    assert value() == 1\n"
        for index in range(TESTS_PER_PARTITION)
    )
    for name in ("part_a", "part_b"):
        (project / name).mkdir()
        (project / name / f"test_{name}.py").write_text(body)


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
            f"def value():\n    extra = {round_number}\n    return 1 + extra - extra\n"
        )
        first = _pytest(tmp_path, "part_a")
        second = _pytest(tmp_path, "part_b")
        results = [_finish(first), _finish(second)]
        assert [code for code, _ in results] == [0, 0], [output for _, output in results]

    with sqlite3.connect(tmp_path / ".testmondata") as database:
        assert database.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        recorded = database.execute("SELECT count(*) FROM test_execution").fetchone()[0]
    assert recorded == 2 * TESTS_PER_PARTITION

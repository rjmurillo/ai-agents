"""A testmon run must not delete another partition's records (issue #6406).

testmon 2.2.0 runs ``sync_db_fs_tests`` while it collects. That step deletes every
recorded test that this run did not collect and did not find stable. With one
shared ``.testmondata`` and overlapping pre-push partitions, a partition that
reaches collection after a sibling has saved deletes the sibling's fresh rows.
CI saw 30 recorded tests where 60 were expected.

``scripts.validation.testmon_scoped_sync`` limits that delete to tests whose file
this run collected, plus tests whose file no longer exists. These tests cover the
pure rule, then replay the losing order with two real testmon processes: the
control without the plugin loses the rows, the run with it keeps them.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path

import pytest

from scripts.validation import testmon_scoped_sync

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_FLAG = f"-p{testmon_scoped_sync.__name__}"
TESTS_PER_PARTITION = 30
GATE_SECONDS = 60


def test_a_test_in_a_collected_file_is_deleted() -> None:
    names = ["part_a/test_x.py::test_gone"]
    assert testmon_scoped_sync.scoped_deletions(
        names, {"part_a/test_x.py"}, lambda _file: True
    ) == ["part_a/test_x.py::test_gone"]


def test_a_test_in_an_uncollected_existing_file_is_kept() -> None:
    names = ["part_b/test_y.py::test_other_partition"]
    assert (
        testmon_scoped_sync.scoped_deletions(names, {"part_a/test_x.py"}, lambda _file: True) == []
    )


def test_a_test_in_a_missing_file_is_deleted() -> None:
    names = ["part_b/test_deleted.py::test_old"]
    assert testmon_scoped_sync.scoped_deletions(
        names, {"part_a/test_x.py"}, lambda _file: False
    ) == ["part_b/test_deleted.py::test_old"]


def test_mixed_names_keep_only_the_other_partitions_tests() -> None:
    names = [
        "part_a/test_x.py::test_gone",
        "part_b/test_y.py::test_other_partition",
        "part_c/test_z.py::TestClass::test_deleted_file",
    ]
    existing = {"part_a/test_x.py", "part_b/test_y.py"}
    assert testmon_scoped_sync.scoped_deletions(
        names, {"part_a/test_x.py"}, lambda file: file in existing
    ) == ["part_a/test_x.py::test_gone", "part_c/test_z.py::TestClass::test_deleted_file"]


def test_no_names_means_no_deletions() -> None:
    assert testmon_scoped_sync.scoped_deletions([], {"a.py"}, lambda _file: True) == []


def test_a_name_without_a_separator_is_its_own_file() -> None:
    assert testmon_scoped_sync.scoped_deletions(
        ["test_top.py"], {"test_top.py"}, lambda _file: True
    ) == ["test_top.py"]


def test_install_wraps_sync_once() -> None:
    pytest.importorskip("testmon")
    from testmon import testmon_core

    original = testmon_core.TestmonData.sync_db_fs_tests
    try:
        assert testmon_scoped_sync.install() is True
        first = testmon_core.TestmonData.sync_db_fs_tests
        assert testmon_scoped_sync.install() is True
        assert testmon_core.TestmonData.sync_db_fs_tests is first
    finally:
        testmon_core.TestmonData.sync_db_fs_tests = original


def test_install_reports_false_when_testmon_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "testmon.testmon_core", None)
    assert testmon_scoped_sync.install() is False


def test_install_reports_false_when_the_hook_moved(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("testmon")
    from testmon import testmon_core

    monkeypatch.delattr(testmon_core.TestmonData, "sync_db_fs_tests")
    assert testmon_scoped_sync.install() is False


def _env(gate: Path | None) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("PYTEST_")}
    env.pop("TESTMON_DATAFILE", None)
    env["COVERAGE_CORE"] = "ctrace"
    env["PYTHONPATH"] = str(REPO_ROOT)
    if gate is None:
        env.pop("TESTMON_TEST_GATE", None)
    else:
        env["TESTMON_TEST_GATE"] = str(gate)
    return env


def _pytest(
    project: Path, target: str, *, plugin: bool, gate: Path | None = None
) -> subprocess.Popen[str]:
    flags = ["--testmon", "--testmon-forceselect"] + ([PLUGIN_FLAG] if plugin else [])
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "pytest",
            *flags,
            "-m",
            "not integration",
            "-q",
            "-o",
            "addopts=",
            target,
        ],
        cwd=project,
        env=_env(gate),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
    )


# The gate holds one run between "testmon has chosen which tests are stable" and
# "testmon deletes what it did not collect", so the sibling can save in between.
# A tryfirst hook wrapper runs before every plain hook, testmon's tryfirst one included.
_GATING_CONFTEST = """
import os
import time
from pathlib import Path

import pytest


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_collection_modifyitems(config, items):
    gate = os.environ.get("TESTMON_TEST_GATE")
    if gate:
        Path(gate + ".ready").write_text("ready", encoding="utf-8")
        deadline = time.monotonic() + GATE_SECONDS
        while not Path(gate).exists() and time.monotonic() < deadline:
            time.sleep(0.05)
    yield
""".replace("GATE_SECONDS", str(GATE_SECONDS))


def _build_project(project: Path) -> None:
    (project / "conftest.py").write_text(_GATING_CONFTEST, encoding="utf-8")
    (project / "pkg.py").write_text("def value():\n    return 1\n", encoding="utf-8")
    body = "from pkg import value\n\n" + "".join(
        f"def test_case_{index}():\n    assert value() == 1\n"
        for index in range(TESTS_PER_PARTITION)
    )
    for name in ("part_a", "part_b"):
        (project / name).mkdir()
        (project / name / f"test_{name}.py").write_text(body, encoding="utf-8")


def _finish(process: subprocess.Popen[str]) -> str:
    output, _ = process.communicate(timeout=120)
    assert process.returncode == 0, output
    return output


def _wait_for(path: Path) -> None:
    deadline = time.monotonic() + GATE_SECONDS
    while not path.exists():
        assert time.monotonic() < deadline, f"{path} never appeared"
        time.sleep(0.05)


def _replay_losing_order(project: Path, *, plugin: bool) -> int:
    """Run b to completion while a waits between selection and the delete."""
    pytest.importorskip("testmon")
    _build_project(project)
    _finish(_pytest(project, "part_a", plugin=plugin))
    _finish(_pytest(project, "part_b", plugin=plugin))
    (project / "pkg.py").write_text(
        "def value():\n    extra = 1\n    return 1 + extra - extra\n", encoding="utf-8"
    )

    gate = project / "gate"
    first = _pytest(project, "part_a", plugin=plugin, gate=gate)
    _wait_for(Path(f"{gate}.ready"))
    _finish(_pytest(project, "part_b", plugin=plugin))
    gate.write_text("go", encoding="utf-8")
    _finish(first)

    with closing(sqlite3.connect(project / ".testmondata")) as database:
        return database.execute("SELECT count(*) FROM test_execution").fetchone()[0]


def test_control_without_the_plugin_loses_the_sibling_rows(tmp_path: Path) -> None:
    """Pins the testmon 2.2.0 behavior the plugin works around (issue #6406).

    If an upgrade makes this pass at 60, testmon fixed the delete and the plugin
    can be removed.
    """
    assert _replay_losing_order(tmp_path, plugin=False) == TESTS_PER_PARTITION


def test_the_plugin_keeps_the_sibling_rows(tmp_path: Path) -> None:
    assert _replay_losing_order(tmp_path, plugin=True) == 2 * TESTS_PER_PARTITION


def test_the_plugin_still_prunes_a_deleted_test_file(tmp_path: Path) -> None:
    """Scoping must not turn into never deleting: a removed file's rows go."""
    pytest.importorskip("testmon")
    _build_project(tmp_path)
    _finish(_pytest(tmp_path, "part_a", plugin=True))
    _finish(_pytest(tmp_path, "part_b", plugin=True))
    shutil.rmtree(tmp_path / "part_b")
    _finish(_pytest(tmp_path, "part_a", plugin=True))
    with closing(sqlite3.connect(tmp_path / ".testmondata")) as database:
        names = {row[0] for row in database.execute("SELECT test_name FROM test_execution")}
    assert names and all(name.startswith("part_a/") for name in names)


class _FakeDatabase:
    def __init__(self) -> None:
        self.deleted: list[tuple[list[str], int]] = []

    def delete_test_executions(self, test_names: list[str], exec_id: int) -> None:
        self.deleted.append((list(test_names), exec_id))


class _FakeData:
    def __init__(self, rootdir: Path) -> None:
        self.rootdir = str(rootdir)
        self.db = _FakeDatabase()
        self.fail = False

    def sync_db_fs_tests(self, retain: set[str]) -> None:
        del retain
        self.db.delete_test_executions(["a/t.py::gone", "b/t.py::kept", "c/t.py::missing"], 7)
        if self.fail:
            raise RuntimeError("sync failed")


def test_wrapped_sync_filters_the_delete_and_restores_the_database(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "t.py").write_text("", encoding="utf-8")
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "t.py").write_text("", encoding="utf-8")
    data = _FakeData(tmp_path)
    database = data.db
    testmon_scoped_sync._scoped(_FakeData.sync_db_fs_tests)(data, {"a/t.py::alive"})
    assert database.deleted == [(["a/t.py::gone", "c/t.py::missing"], 7)]
    assert "delete_test_executions" not in vars(database)


def test_wrapped_sync_restores_the_database_when_the_sync_fails(tmp_path: Path) -> None:
    data = _FakeData(tmp_path)
    data.fail = True
    with pytest.raises(RuntimeError, match="sync failed"):
        testmon_scoped_sync._scoped(_FakeData.sync_db_fs_tests)(data, set())
    assert "delete_test_executions" not in vars(data.db)


def test_pytest_configure_installs_the_wrapper() -> None:
    pytest.importorskip("testmon")
    from testmon import testmon_core

    original = testmon_core.TestmonData.sync_db_fs_tests
    try:
        testmon_scoped_sync.pytest_configure(object())
        assert getattr(testmon_core.TestmonData.sync_db_fs_tests, "_ai_agents_scoped_sync", False)
    finally:
        testmon_core.TestmonData.sync_db_fs_tests = original

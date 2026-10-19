"""Overlapping pre-push lanes read and write separate testmon databases (issue #6477).

The logged failure: xdist stopped with "Different tests were collected" because
lanes that shared one ``.testmondata`` changed what another lane's workers read
while they collected ("changed files: 25" on most workers, 35 on one).
"""

from __future__ import annotations

import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path

import pytest

from scripts.validation import git_hook_policy, pytest_lanes
from tests.validation.pre_push_testmon_helpers import (
    default_environment,  # noqa: F401  (fixture, applied by usefixtures below)
)

pytestmark = pytest.mark.usefixtures("default_environment")

BASE = ".testmondata"


def _finished(path: Path, marker: str) -> None:
    with closing(sqlite3.connect(path)) as database:
        database.execute("CREATE TABLE marker (name TEXT)")
        database.execute("INSERT INTO marker VALUES (?)", (marker,))
        database.execute("PRAGMA user_version = 1")
        database.commit()


def _marker(path: Path) -> str:
    with closing(sqlite3.connect(path)) as database:
        return database.execute("SELECT name FROM marker").fetchone()[0]


@pytest.fixture(autouse=True)
def _overlap_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TESTMON_DATAFILE", raising=False)
    monkeypatch.setenv(git_hook_policy.PYTEST_WORKERS_ENV, "8")
    monkeypatch.setattr(git_hook_policy, "_visible_cpu_count", lambda: 48)
    monkeypatch.setattr(git_hook_policy, "_container_clamped", lambda seconds: seconds)


def _record_environments(
    monkeypatch: pytest.MonkeyPatch, root: Path
) -> dict[str, dict[str, str | None]]:
    """Map each partition label to the TESTMON_DATAFILE its child receives."""
    seen: dict[str, dict[str, str | None]] = {}

    def fake(
        command: list[str],
        _root: object,
        *,
        process_env: dict[str, str] | None = None,
        **_k: object,
    ) -> subprocess.CompletedProcess[str]:
        env = process_env or {}
        label = pytest_lanes.partition_label(command, root)
        datafile = env.get("TESTMON_DATAFILE")
        seen[label] = {"datafile": datafile, "seed": _marker(root / datafile) if datafile else None}
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(git_hook_policy, "_run_command", fake)
    monkeypatch.setattr(git_hook_policy, "_print_process_output", lambda _r: None)
    return seen


def test_each_overlapping_lane_gets_its_own_database_seeded_from_the_base(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _finished(tmp_path / BASE, "base")
    seen = _record_environments(monkeypatch, tmp_path)

    assert git_hook_policy.run_pytest(tmp_path) == 0

    assert len(seen) == 4
    files = {entry["datafile"] for entry in seen.values()}
    assert None not in files
    assert BASE not in files
    assert len(files) == 3  # bulk, mutation, and the one serial lane
    assert {entry["seed"] for entry in seen.values()} == {"base"}


def test_the_two_xdist_lanes_never_share_a_database(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _finished(tmp_path / BASE, "base")
    seen = _record_environments(monkeypatch, tmp_path)

    git_hook_policy.run_pytest(tmp_path)

    assert seen["tests"]["datafile"] != seen["tests/mutation"]["datafile"]


def test_the_serial_commands_share_one_database_because_they_run_in_order(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _finished(tmp_path / BASE, "base")
    seen = _record_environments(monkeypatch, tmp_path)

    git_hook_policy.run_pytest(tmp_path)

    serial = [label for label in seen if label not in ("tests", "tests/mutation")]
    assert len(serial) == 2
    assert seen[serial[0]]["datafile"] == seen[serial[1]]["datafile"]
    assert seen[serial[0]]["datafile"] not in (
        seen["tests"]["datafile"],
        seen["tests/mutation"]["datafile"],
    )


def test_a_lane_database_from_an_earlier_push_is_kept(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _finished(tmp_path / BASE, "base")
    _finished(tmp_path / f"{BASE}-lane0", "earlier-push")
    seen = _record_environments(monkeypatch, tmp_path)

    git_hook_policy.run_pytest(tmp_path)

    assert seen["tests"]["datafile"] == f"{BASE}-lane0"
    assert seen["tests"]["seed"] == "earlier-push"
    assert seen["tests/mutation"]["seed"] == "base"


def test_the_base_database_is_left_untouched(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _finished(tmp_path / BASE, "base")
    before = (tmp_path / BASE).read_bytes()
    _record_environments(monkeypatch, tmp_path)

    git_hook_policy.run_pytest(tmp_path)

    assert (tmp_path / BASE).read_bytes() == before


def test_a_relocated_base_database_names_the_lane_files_beside_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TESTMON_DATAFILE", "elsewhere.db")
    _finished(tmp_path / "elsewhere.db", "relocated")
    seen = _record_environments(monkeypatch, tmp_path)

    git_hook_policy.run_pytest(tmp_path)

    files = {entry["datafile"] for entry in seen.values()}
    assert files == {"elsewhere.db-lane0", "elsewhere.db-lane1", "elsewhere.db-lane2"}
    assert {entry["seed"] for entry in seen.values()} == {"relocated"}


def test_without_a_database_the_sequential_build_uses_the_shared_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen = _record_environments(monkeypatch, tmp_path)

    git_hook_policy.run_pytest(tmp_path)

    assert {entry["datafile"] for entry in seen.values()} == {None}
    assert not list(tmp_path.glob(f"{BASE}-lane*"))


def test_the_full_suite_opt_in_has_no_testmon_database_to_split(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, "1")
    _finished(tmp_path / BASE, "base")
    seen = _record_environments(monkeypatch, tmp_path)

    assert git_hook_policy.run_pytest(tmp_path) == 0

    assert {entry["datafile"] for entry in seen.values()} == {None}
    assert not list(tmp_path.glob(f"{BASE}-lane*"))


def test_the_parent_environment_is_not_changed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _finished(tmp_path / BASE, "base")
    _record_environments(monkeypatch, tmp_path)

    git_hook_policy.run_pytest(tmp_path)

    import os

    assert "TESTMON_DATAFILE" not in os.environ


def test_a_seed_that_cannot_be_copied_leaves_testmon_to_build_the_lane(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _finished(tmp_path / BASE, "base")
    monkeypatch.setattr(
        git_hook_policy.testmon_lane_db,
        "_copy_database",
        lambda _s, _t: (_ for _ in ()).throw(OSError("read-only filesystem")),
    )
    seen: dict[str, str | None] = {}

    def fake(
        command: list[str],
        _root: object,
        *,
        process_env: dict[str, str] | None = None,
        **_k: object,
    ) -> subprocess.CompletedProcess[str]:
        label = pytest_lanes.partition_label(command, tmp_path)
        seen[label] = (process_env or {}).get("TESTMON_DATAFILE")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(git_hook_policy, "_run_command", fake)
    monkeypatch.setattr(git_hook_policy, "_print_process_output", lambda _r: None)

    assert git_hook_policy.run_pytest(tmp_path) == 0

    assert seen["tests"] == f"{BASE}-lane0"
    assert not (tmp_path / f"{BASE}-lane0").exists()

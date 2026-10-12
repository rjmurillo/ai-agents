"""The pre-push pytest partitions overlap instead of running in sequence (issue #6198).

Acceptance criteria covered here:

* a failure or timeout in one partition fails the step and names the partition;
* on deadline expiry every running partition is stopped and the report says so;
* safe-push and pr-autofix stay serial, in one lane, and never get a worker pool;
* the xdist workers across partitions never exceed the configured budget;
* all pass, one fails, one times out, and a single-command subset.

The wall-time criterion (within 20% of the slowest partition) is a measurement
on a real push, recorded in the pull request; the barrier test below proves the
partitions run at the same time.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import threading
import time
from contextlib import closing
from pathlib import Path

import pytest

from scripts.validation import git_hook_policy
from tests.validation.pre_push_testmon_helpers import (
    default_environment,  # noqa: F401  (fixture, applied by usefixtures below)
)

pytestmark = pytest.mark.usefixtures("default_environment")

BULK = "tests"
MUTATION = "tests/mutation"
SAFE_PUSH = "tests/test_safe_push_pr_branch.py (+1 more)"
PR_AUTOFIX = "tests/test_pr_autofix_late_live_state_gate.py"


@pytest.fixture
def overlap(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Run the full-suite partitions with an 8 worker budget on a 48 CPU host."""
    monkeypatch.setenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, "1")
    monkeypatch.setenv(git_hook_policy.PYTEST_WORKERS_ENV, "8")
    monkeypatch.setattr(git_hook_policy, "_visible_cpu_count", lambda: 48)
    monkeypatch.setattr(git_hook_policy, "_container_clamped", lambda seconds: seconds)
    return tmp_path


def _label(root: Path, command: list[str]) -> str:
    from scripts.validation import pytest_lanes

    return pytest_lanes.partition_label(command, root)


def _stub(
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
    codes: dict[str, int] | None = None,
    barrier: threading.Barrier | None = None,
) -> list[list[str]]:
    """Replace the subprocess boundary; return each argv in the order it started."""
    seen: list[list[str]] = []
    lock = threading.Lock()
    codes = codes or {}

    def fake(command: list[str], _root: object, **_k: object) -> subprocess.CompletedProcess[str]:
        label = _label(root, command)
        with lock:
            seen.append(list(command))
        if barrier is not None and "-n" in command:
            barrier.wait()  # BrokenBarrierError unless both pools run at once
        return subprocess.CompletedProcess(command, codes.get(label, 0), f"out {label}\n", "")

    monkeypatch.setattr(git_hook_policy, "_run_command", fake)
    monkeypatch.setattr(git_hook_policy, "_print_process_output", lambda _r: None)
    return seen


def test_all_partitions_pass_and_the_two_pools_run_at_the_same_time(
    monkeypatch: pytest.MonkeyPatch, overlap: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seen = _stub(monkeypatch, overlap, barrier=threading.Barrier(2, timeout=10))

    assert git_hook_policy.run_pytest(overlap) == 0

    assert len(seen) == 4
    err = capsys.readouterr().err
    for label in (BULK, MUTATION, SAFE_PUSH, PR_AUTOFIX):
        assert f"pytest partition {label}: exit 0 in " in err
    assert "partitions failed" not in err


def test_the_pools_split_the_worker_budget_and_the_serial_lane_has_none(
    monkeypatch: pytest.MonkeyPatch, overlap: Path
) -> None:
    seen = _stub(monkeypatch, overlap)

    git_hook_policy.run_pytest(overlap)

    workers = [int(c[c.index("-n") + 1]) for c in seen if "-n" in c]
    assert sorted(workers) == [4, 4]
    assert sum(workers) <= 8
    serial = [c for c in seen if "-n" not in c]
    assert [_label(overlap, c) for c in serial] == [SAFE_PUSH, PR_AUTOFIX]


def test_safe_push_and_pr_autofix_run_one_after_the_other(
    monkeypatch: pytest.MonkeyPatch, overlap: Path
) -> None:
    seen = _stub(monkeypatch, overlap)

    git_hook_policy.run_pytest(overlap)

    serial = [_label(overlap, c) for c in seen if "-n" not in c]
    assert serial == [SAFE_PUSH, PR_AUTOFIX]


@pytest.mark.parametrize("failing", [BULK, MUTATION, SAFE_PUSH, PR_AUTOFIX])
def test_one_failing_partition_fails_the_step_and_is_named(
    monkeypatch: pytest.MonkeyPatch,
    overlap: Path,
    capsys: pytest.CaptureFixture[str],
    failing: str,
) -> None:
    seen = _stub(monkeypatch, overlap, codes={failing: 1})

    assert git_hook_policy.run_pytest(overlap) == 1

    assert len(seen) == 4  # the others still run, so each records its tests
    err = capsys.readouterr().err
    assert f"pytest partition {failing}: exit 1 in " in err
    assert f"ERROR: pytest partitions failed: {failing}" in err
    assert err.count("exit 1 in") == 1


def test_the_exit_code_is_the_worst_partition_and_a_signal_death_is_a_failure(
    monkeypatch: pytest.MonkeyPatch, overlap: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub(monkeypatch, overlap, codes={BULK: -9, MUTATION: 4, PR_AUTOFIX: 2})

    assert git_hook_policy.run_pytest(overlap) == 4

    err = capsys.readouterr().err
    assert f"ERROR: pytest partitions failed: {BULK}, {MUTATION}, {PR_AUTOFIX}" in err


def test_a_single_command_subset_runs_without_a_second_lane(
    monkeypatch: pytest.MonkeyPatch, overlap: Path
) -> None:
    only = [sys.executable, "-m", "pytest", "-n", "4", str(overlap / "tests")]
    monkeypatch.setattr(git_hook_policy, "_resolve_pytest_commands", lambda _root: [only])
    seen = _stub(monkeypatch, overlap)

    assert git_hook_policy.run_pytest(overlap) == 0

    assert seen == [only]


def test_a_one_worker_budget_runs_the_partitions_in_sequence(
    monkeypatch: pytest.MonkeyPatch, overlap: Path
) -> None:
    monkeypatch.setenv(git_hook_policy.PYTEST_WORKERS_ENV, "1")
    active = 0
    peak = 0
    lock = threading.Lock()

    def fake(command: list[str], _root: object, **_k: object) -> subprocess.CompletedProcess[str]:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.02)
        with lock:
            active -= 1
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(git_hook_policy, "_run_command", fake)
    monkeypatch.setattr(git_hook_policy, "_print_process_output", lambda _r: None)

    assert git_hook_policy.run_pytest(overlap) == 0

    assert peak == 1


def _finished_database(path: Path) -> None:
    """Write the file testmon leaves after it creates every table."""
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("PRAGMA user_version = 1")


def test_testmon_without_a_database_builds_it_in_sequence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(git_hook_policy.PYTEST_WORKERS_ENV, "8")
    monkeypatch.setattr(git_hook_policy, "_container_clamped", lambda seconds: seconds)
    seen = _stub(monkeypatch, tmp_path)

    assert git_hook_policy.run_pytest(tmp_path) == 0

    assert seen == git_hook_policy._testmon_commands(tmp_path)
    assert "no testmon database yet; running the partitions in sequence" in (
        capsys.readouterr().err
    )


def test_testmon_with_a_database_overlaps_the_partitions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _finished_database(tmp_path / ".testmondata")
    monkeypatch.setenv(git_hook_policy.PYTEST_WORKERS_ENV, "8")
    monkeypatch.setattr(git_hook_policy, "_container_clamped", lambda seconds: seconds)
    seen = _stub(monkeypatch, tmp_path, barrier=threading.Barrier(2, timeout=10))

    assert git_hook_policy.run_pytest(tmp_path) == 0

    assert all("--testmon" in command for command in seen)
    assert len(seen) == 4


def test_the_database_location_follows_testmons_own_environment_variable(
    tmp_path: Path,
) -> None:
    assert git_hook_policy._testmon_database_missing(tmp_path, {}) is True
    _finished_database(tmp_path / ".testmondata")
    assert git_hook_policy._testmon_database_missing(tmp_path, {}) is False
    relocated = {"TESTMON_DATAFILE": "elsewhere.db"}
    assert git_hook_policy._testmon_database_missing(tmp_path, relocated) is True
    _finished_database(tmp_path / "elsewhere.db")
    assert git_hook_policy._testmon_database_missing(tmp_path, relocated) is False


def test_an_interrupted_database_build_counts_as_missing(tmp_path: Path) -> None:
    path = tmp_path / ".testmondata"
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE metadata (dataid TEXT PRIMARY KEY, data TEXT)")
    assert git_hook_policy._testmon_database_missing(tmp_path, {}) is True
    path.write_bytes(b"not a sqlite file")
    assert git_hook_policy._testmon_database_missing(tmp_path, {}) is True


def _sleeper(pid_file: Path, seconds: int) -> list[str]:
    """A pool-shaped command (it carries ``-n``) that records its pid then sleeps."""
    script = pid_file.with_suffix(".py")
    script.write_text(
        "import os, time\n"
        f"open({str(pid_file)!r}, 'w').write(str(os.getpid()))\n"
        f"time.sleep({seconds})\n"
    )
    return [sys.executable, str(script), "-n", "2"]


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _read_pid(pid_file: Path) -> int:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        text = pid_file.read_text() if pid_file.exists() else ""
        if text:
            return int(text)
        time.sleep(0.05)
    raise AssertionError(f"{pid_file} was never written")


def test_a_timeout_stops_every_running_partition_and_names_each(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    first, second = tmp_path / "first.pid", tmp_path / "second.pid"
    commands = [_sleeper(first, 60), _sleeper(second, 60)]
    monkeypatch.setattr(git_hook_policy, "_resolve_pytest_commands", lambda _root: commands)
    monkeypatch.setattr(git_hook_policy, "_suite_budget_seconds", lambda: 3)
    monkeypatch.setattr(git_hook_policy, "_container_clamped", lambda seconds: seconds)
    monkeypatch.setattr(git_hook_policy, "_visible_cpu_count", lambda: 4)
    monkeypatch.setattr(git_hook_policy, "_print_process_output", lambda _r: None)

    started = time.monotonic()
    code = git_hook_policy.run_pytest(tmp_path)
    elapsed = time.monotonic() - started

    assert code == 3
    assert elapsed < 30
    assert not _alive(_read_pid(first))
    assert not _alive(_read_pid(second))
    err = capsys.readouterr().err
    assert err.count("stopped at the 3s budget") == 2
    assert "ERROR: pytest partitions failed: first.py, second.py" in err


def test_a_partition_the_budget_never_let_start_is_named(
    monkeypatch: pytest.MonkeyPatch, overlap: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(git_hook_policy, "_suite_budget_seconds", lambda: 0.3)
    started: list[str] = []

    def fake(command: list[str], _root: object, **_k: object) -> subprocess.CompletedProcess[str]:
        started.append(_label(overlap, command))
        if _label(overlap, command) == SAFE_PUSH:
            time.sleep(0.6)  # spends the whole budget before pr-autofix can start
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(git_hook_policy, "_run_command", fake)
    monkeypatch.setattr(git_hook_policy, "_print_process_output", lambda _r: None)

    assert git_hook_policy.run_pytest(overlap) == 1

    assert PR_AUTOFIX not in started
    err = capsys.readouterr().err
    assert f"ERROR: pytest partition {PR_AUTOFIX} did not start; the 0.3s budget was spent" in err
    assert f"ERROR: pytest partitions failed: {PR_AUTOFIX}" in err


def test_an_interrupt_stops_the_children_it_started(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fast, slow = tmp_path / "fast.pid", tmp_path / "slow.pid"
    quick_script = tmp_path / "quick.py"
    quick_script.write_text(f"open({str(fast)!r}, 'w').write('x')\n")
    quick = [sys.executable, str(quick_script), "-n", "2"]
    commands = [quick, _sleeper(slow, 60)]
    monkeypatch.setattr(git_hook_policy, "_resolve_pytest_commands", lambda _root: commands)
    monkeypatch.setattr(git_hook_policy, "_container_clamped", lambda seconds: seconds)
    monkeypatch.setattr(git_hook_policy, "_visible_cpu_count", lambda: 4)
    pids: list[int] = []

    def interrupt_once_the_sleeper_runs(_result: object) -> None:
        pids.append(_read_pid(slow))
        raise KeyboardInterrupt

    monkeypatch.setattr(git_hook_policy, "_print_process_output", interrupt_once_the_sleeper_runs)

    started = time.monotonic()
    with pytest.raises(KeyboardInterrupt):
        git_hook_policy.run_pytest(tmp_path)

    # Without the stop, the run waits out the 60s sleeper before it re-raises.
    assert time.monotonic() - started < 30
    assert pids
    assert not _alive(pids[0])


def _serial_sleeper(pid_file: Path, seconds: int) -> list[str]:
    """A serial-lane command: no ``-n``, records its pid, then sleeps."""
    return _sleeper(pid_file, seconds)[:-2]


def test_an_interrupt_during_the_first_serial_command_starts_no_second_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    quick_script = tmp_path / "quick.py"
    quick_script.write_text("pass\n")
    first, second = tmp_path / "first.pid", tmp_path / "second.pid"
    commands = [
        [sys.executable, str(quick_script), "-n", "2"],
        _serial_sleeper(first, 60),
        _serial_sleeper(second, 60),
    ]
    monkeypatch.setattr(git_hook_policy, "_resolve_pytest_commands", lambda _root: commands)
    monkeypatch.setattr(git_hook_policy, "_container_clamped", lambda seconds: seconds)
    monkeypatch.setattr(git_hook_policy, "_visible_cpu_count", lambda: 4)
    pids: list[int] = []

    def interrupt_once_the_first_serial_command_runs(_result: object) -> None:
        if not pids:
            pids.append(_read_pid(first))
            raise KeyboardInterrupt

    monkeypatch.setattr(
        git_hook_policy, "_print_process_output", interrupt_once_the_first_serial_command_runs
    )

    started = time.monotonic()
    with pytest.raises(KeyboardInterrupt):
        git_hook_policy.run_pytest(tmp_path)

    # Without the cancel, the lane starts the second sleeper and the run waits it out.
    assert time.monotonic() - started < 30
    assert not _alive(pids[0])
    assert not second.exists()


def test_one_timing_out_partition_is_the_only_one_named(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    quick_script = tmp_path / "quick.py"
    quick_script.write_text("pass\n")
    slow = tmp_path / "slow.pid"
    commands = [[sys.executable, str(quick_script), "-n", "2"], _sleeper(slow, 60)]
    monkeypatch.setattr(git_hook_policy, "_resolve_pytest_commands", lambda _root: commands)
    monkeypatch.setattr(git_hook_policy, "_suite_budget_seconds", lambda: 3)
    monkeypatch.setattr(git_hook_policy, "_container_clamped", lambda seconds: seconds)
    monkeypatch.setattr(git_hook_policy, "_visible_cpu_count", lambda: 4)
    monkeypatch.setattr(git_hook_policy, "_print_process_output", lambda _r: None)

    assert git_hook_policy.run_pytest(tmp_path) == 3

    err = capsys.readouterr().err
    assert "pytest partition quick.py: exit 0 in " in err
    assert err.count("stopped at the 3s budget") == 1
    assert "ERROR: pytest partitions failed: slow.py" in err
    assert not _alive(_read_pid(slow))


class _FakeProcess:
    """A started child for the stop logic: it never exits on its own."""

    pid = 424242
    killed = False

    def poll(self) -> None:
        return None

    def kill(self) -> None:
        self.killed = True


def _interrupted_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, pgroup: bool
) -> tuple[_FakeProcess, list[int]]:
    """Interrupt the run, then let a slower lane register its child after the stop."""
    monkeypatch.setenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, "1")
    monkeypatch.setenv(git_hook_policy.PYTEST_WORKERS_ENV, "8")
    monkeypatch.setattr(git_hook_policy, "_visible_cpu_count", lambda: 48)
    monkeypatch.setattr(git_hook_policy, "_container_clamped", lambda seconds: seconds)
    monkeypatch.setattr(git_hook_policy, "_SUPPORTS_PGROUP", pgroup)
    group_kills: list[int] = []
    monkeypatch.setattr(git_hook_policy, "_killpg_safe", group_kills.append)
    interrupted = threading.Event()
    late = _FakeProcess()

    def fake(
        command: list[str],
        _root: object,
        *,
        on_start: object = None,
        **_k: object,
    ) -> subprocess.CompletedProcess[str]:
        if _label(tmp_path, command) == BULK:
            return subprocess.CompletedProcess(command, 0, "", "")
        interrupted.wait(timeout=10)
        time.sleep(0.3)  # the stop has run by now
        if callable(on_start):
            on_start(late)
        return subprocess.CompletedProcess(command, 0, "", "")

    def interrupt(_result: object) -> None:
        interrupted.set()
        raise KeyboardInterrupt

    monkeypatch.setattr(git_hook_policy, "_run_command", fake)
    monkeypatch.setattr(git_hook_policy, "_print_process_output", interrupt)
    with pytest.raises(KeyboardInterrupt):
        git_hook_policy.run_pytest(tmp_path)
    return late, group_kills


def test_a_child_that_starts_after_the_interrupt_is_stopped_too(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    late, group_kills = _interrupted_run(monkeypatch, tmp_path, pgroup=True)

    assert group_kills.count(late.pid) >= 1
    assert late.killed is False


def test_without_process_groups_the_child_itself_is_killed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    late, group_kills = _interrupted_run(monkeypatch, tmp_path, pgroup=False)

    assert late.killed is True
    assert group_kills == []


def test_a_relative_repo_root_still_reads_the_database_version(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _finished_database(tmp_path / ".testmondata")
    monkeypatch.chdir(tmp_path.parent)
    relative = Path(tmp_path.name)
    assert git_hook_policy._testmon_database_missing(relative, {}) is False

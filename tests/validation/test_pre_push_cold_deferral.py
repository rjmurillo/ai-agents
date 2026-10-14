"""With no testmon database the hook collects the suite instead of running it (issue #6200).

The selection is then the whole suite, measured at 462s on a 48-thread
host, past the 180s selection budget. Starting that run cannot succeed, so the
hook checks that every test module imports and leaves execution to CI.
"""

from __future__ import annotations

import sqlite3
import subprocess
import time
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest

from scripts.validation import git_hook_policy
from tests.validation.pre_push_testmon_helpers import (
    default_environment,  # noqa: F401  (fixture, applied by usefixtures below)
)

pytestmark = pytest.mark.usefixtures("default_environment")

PARTITIONS = 4
NO_TESTS_COLLECTED = 5
# Captured at import, before the fixture replaces it with "never defer".
REAL_DEFER = git_hook_policy._should_defer_cold_selection


def _cold(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """No local database, and the seed fetch (stubbed by the fixture) found nothing."""
    assert not (tmp_path / ".testmondata").exists()
    monkeypatch.setattr(git_hook_policy, "_should_defer_cold_selection", REAL_DEFER)
    monkeypatch.setattr(git_hook_policy, "_container_clamped", lambda seconds: seconds)


def _stub(
    monkeypatch: pytest.MonkeyPatch,
    results: list[tuple[int, str]] | None = None,
) -> tuple[list[dict[str, Any]], list[subprocess.CompletedProcess[str]]]:
    """Replace the subprocess boundary; return the child calls and the printed results."""
    calls: list[dict[str, Any]] = []
    printed: list[subprocess.CompletedProcess[str]] = []
    pending = iter(results or [])

    def fake(command: list[str], _root: object, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append({"command": list(command), **kwargs})
        code, stdout = next(pending, (0, ""))
        return subprocess.CompletedProcess(command, code, stdout, "")

    monkeypatch.setattr(git_hook_policy, "_run_command", fake)
    monkeypatch.setattr(git_hook_policy, "_print_process_output", printed.append)
    return calls, printed


def test_a_cold_push_collects_every_partition_and_runs_no_test(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _cold(monkeypatch, tmp_path)
    counts = [(0, f"{n} tests collected in 1s\n") for n in (40000, 9000, 20, 15)]
    calls, printed = _stub(monkeypatch, counts)

    assert git_hook_policy.run_pytest(tmp_path) == 0

    assert len(calls) == PARTITIONS
    for call in calls:
        assert "--collect-only" in call["command"]
        assert "--testmon" not in call["command"]
        assert "--testmon-forceselect" not in call["command"]
    assert printed == []
    err = capsys.readouterr().err
    assert "all 49,035 tests" in err
    assert "CI runs every test" in err


def test_the_cold_notice_says_so_when_a_count_is_unreadable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _cold(monkeypatch, tmp_path)
    _stub(monkeypatch, [(0, "100 tests collected in 1s\n"), (0, "garbled\n")])
    assert git_hook_policy.run_pytest(tmp_path) == 0
    assert "Not run locally: the whole suite" in capsys.readouterr().err


def test_a_broken_import_still_blocks_a_cold_push(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Collection imports every test module, so the push keeps that defect class."""
    _cold(monkeypatch, tmp_path)
    calls, printed = _stub(monkeypatch, [(0, "5 tests collected in 1s\n"), (2, "ImportError\n")])

    assert git_hook_policy.run_pytest(tmp_path) == 2

    assert len(calls) == PARTITIONS
    assert len(printed) == 1
    assert "Not run locally" not in capsys.readouterr().err


def test_a_killed_collection_blocks_a_cold_push(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A negative exit is a signal kill; it must not read as a pass."""
    _cold(monkeypatch, tmp_path)
    _stub(monkeypatch, [(-9, "")])
    assert git_hook_policy.run_pytest(tmp_path) == 1


def test_an_empty_partition_does_not_block_a_cold_push(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _cold(monkeypatch, tmp_path)
    _stub(monkeypatch, [(0, "9 tests collected in 1s\n"), (NO_TESTS_COLLECTED, "no tests\n")])
    assert git_hook_policy.run_pytest(tmp_path) == 0


def test_every_partition_empty_blocks_a_cold_push(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A broken marker or path would pass as "all 0 tests" without this check."""
    _cold(monkeypatch, tmp_path)
    _stub(monkeypatch, [(NO_TESTS_COLLECTED, "output the parser does not know\n")] * PARTITIONS)
    assert git_hook_policy.run_pytest(tmp_path) == 1
    assert "collected no tests in any partition" in capsys.readouterr().err


def test_a_failed_collection_prints_only_the_end_of_a_huge_listing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The error is at the end of tens of thousands of test ids."""
    _cold(monkeypatch, tmp_path)
    listing = "\n".join(f"tests/t.py::test_{n}" for n in range(5000)) + "\nImportError: boom\n"
    _calls, printed = _stub(monkeypatch, [(2, listing)])
    assert git_hook_policy.run_pytest(tmp_path) == 2
    shown = printed[0].stdout
    assert shown.endswith("ImportError: boom")
    assert len(shown.splitlines()) == 80


def test_collection_that_spends_the_budget_blocks_the_push(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _cold(monkeypatch, tmp_path)
    monkeypatch.setattr(git_hook_policy, "PRE_PUSH_SELECTION_TIMEOUT_SECONDS", 0)
    calls, _printed = _stub(monkeypatch)
    assert git_hook_policy.run_pytest(tmp_path) == 1
    assert calls == []
    assert "collection spent the 0s budget" in capsys.readouterr().err


def test_collection_runs_inside_the_selection_budget(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _cold(monkeypatch, tmp_path)
    calls, _printed = _stub(monkeypatch)
    git_hook_policy.run_pytest(tmp_path)
    budget = git_hook_policy.PRE_PUSH_SELECTION_TIMEOUT_SECONDS
    assert budget - 5 < calls[0]["timeout_seconds"] <= budget


@pytest.mark.parametrize("version", [0, None])
def test_an_unfinished_database_is_still_cold(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, version: int | None
) -> None:
    """A file whose build was interrupted (user_version 0) or is not sqlite counts as missing."""
    _cold(monkeypatch, tmp_path)
    database = tmp_path / ".testmondata"
    if version is None:
        database.write_bytes(b"not a sqlite file")
    else:
        with closing(sqlite3.connect(database)) as connection:
            connection.execute("CREATE TABLE metadata (dataid TEXT PRIMARY KEY, data TEXT)")
    calls, _printed = _stub(monkeypatch)
    assert git_hook_policy.run_pytest(tmp_path) == 0
    assert all("--collect-only" in call["command"] for call in calls)


def test_a_finished_database_runs_the_selection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Below the line: a database exists, so testmon selects and the tests run."""
    monkeypatch.setattr(git_hook_policy, "_should_defer_cold_selection", REAL_DEFER)
    with closing(sqlite3.connect(tmp_path / ".testmondata")) as connection:
        connection.execute("PRAGMA user_version = 1")
    calls, _printed = _stub(monkeypatch)
    monkeypatch.setattr(git_hook_policy, "_container_clamped", lambda seconds: seconds)
    assert git_hook_policy.run_pytest(tmp_path) == 0
    assert len(calls) == PARTITIONS
    assert all("--testmon" in call["command"] for call in calls)
    assert not any("--collect-only" in call["command"] for call in calls)


def test_the_opt_in_runs_everything_without_a_database_and_keeps_the_suite_budget(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The opt-in ignores the cold deferral and keeps the 780s whole-suite budget."""
    _cold(monkeypatch, tmp_path)
    monkeypatch.setenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, "1")
    monkeypatch.setenv(git_hook_policy.PYTEST_WORKERS_ENV, "1")
    calls, _printed = _stub(monkeypatch)
    assert git_hook_policy.run_pytest(tmp_path) == 0
    assert [call["command"] for call in calls] == git_hook_policy._pytest_commands(tmp_path)
    assert not any("--collect-only" in call["command"] for call in calls)
    budget = git_hook_policy.TEST_SUITE_TIMEOUT_SECONDS
    assert budget - 5 < calls[0]["timeout_seconds"] <= budget


def test_the_ci_seed_job_still_builds_the_database_from_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The seed job exists to build it. Deferring there would upload nothing."""
    _cold(monkeypatch, tmp_path)
    monkeypatch.setenv(git_hook_policy.TESTMON_NO_SEED_ENV, "1")
    monkeypatch.setenv(git_hook_policy.TESTMON_SEED_BUDGET_ENV, "3300")
    calls, _printed = _stub(monkeypatch)
    assert git_hook_policy.run_pytest(tmp_path) == 0
    assert all("--testmon" in call["command"] for call in calls)
    assert not any("--collect-only" in call["command"] for call in calls)
    assert 3290 < calls[0]["timeout_seconds"] <= 3300


def _timing_out(budget: float) -> Any:
    """A child that spends the whole budget and is killed, as `_run_command` reports it."""

    def fake(command: list[str], _root: object, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        time.sleep(budget + 0.05)
        stderr = f"pytest killed{git_hook_policy.TIMEOUT_MARKER}{budget}s"
        return subprocess.CompletedProcess(command, 3, "", stderr)

    return fake


@pytest.mark.parametrize("overlapping", [False, True])
def test_a_selection_that_spends_the_budget_blocks_the_push_and_says_what_to_do(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    overlapping: bool,
) -> None:
    """Both run paths report it. The sequence path is reached in production only by the seed job.

    The default path with no database collects instead, so the sequence case here
    switches the cold deferral off the way the fixture does.
    """
    if overlapping:
        with closing(sqlite3.connect(tmp_path / ".testmondata")) as connection:
            connection.execute("PRAGMA user_version = 1")
    monkeypatch.setattr(git_hook_policy, "_container_clamped", lambda seconds: seconds)
    monkeypatch.setattr(git_hook_policy, "PRE_PUSH_SELECTION_TIMEOUT_SECONDS", 0.1)
    monkeypatch.setattr(git_hook_policy, "_run_command", _timing_out(0.1))
    monkeypatch.setattr(git_hook_policy, "_print_process_output", lambda _r: None)

    assert git_hook_policy.run_pytest(tmp_path) != 0

    err = capsys.readouterr().err
    assert "did not finish in 0.1s" in err
    assert "CI runs every test" in err
    assert f"{git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV}=1" in err
    assert "uv.lock" in err


def test_a_plain_test_failure_is_not_blamed_on_the_budget(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(git_hook_policy, "_container_clamped", lambda seconds: seconds)
    _stub(monkeypatch, [(1, "")] * PARTITIONS)
    assert git_hook_policy.run_pytest(tmp_path) == 1
    assert "did not finish" not in capsys.readouterr().err


def test_a_failure_that_ends_after_the_deadline_is_not_blamed_on_the_budget(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The message keys on the child having been killed, not on the clock."""
    monkeypatch.setattr(git_hook_policy, "_container_clamped", lambda seconds: seconds)
    monkeypatch.setattr(git_hook_policy, "PRE_PUSH_SELECTION_TIMEOUT_SECONDS", 0.05)
    # One partition, so no later partition is refused for lack of time.
    only = ["python", "-m", "pytest", "--testmon"]
    monkeypatch.setattr(git_hook_policy, "_testmon_commands", lambda _root: [only])

    def slow_failure(
        command: list[str], _root: object, **_kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        time.sleep(0.1)
        return subprocess.CompletedProcess(command, 1, "", "")

    monkeypatch.setattr(git_hook_policy, "_run_command", slow_failure)
    monkeypatch.setattr(git_hook_policy, "_print_process_output", lambda _r: None)
    assert git_hook_policy.run_pytest(tmp_path) == 1
    assert "did not finish" not in capsys.readouterr().err


def test_the_opt_in_overrun_keeps_its_own_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The hint names the opt-in, so it must not print when the opt-in is already set."""
    monkeypatch.setattr(git_hook_policy, "_container_clamped", lambda seconds: seconds)
    monkeypatch.setenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, "1")
    monkeypatch.setattr(git_hook_policy, "TEST_SUITE_TIMEOUT_SECONDS", 0.1)
    monkeypatch.setattr(git_hook_policy, "_run_command", _timing_out(0.1))
    monkeypatch.setattr(git_hook_policy, "_print_process_output", lambda _r: None)
    assert git_hook_policy.run_pytest(tmp_path) != 0
    assert "did not finish in" not in capsys.readouterr().err

"""The heavy pre-push stages wait for host headroom and name load when it fails (issue #6609).

`host_headroom` owns the slot and the load wait; `test_host_headroom.py` covers
it. These tests cover the wiring in `git_hook_policy`:

- positive: pytest takes a slot before its budget clock starts and holds it for
  the whole run; semgrep takes a slot only when it has something to scan.
- negative: a semgrep-core target failure is exit 3 (infrastructure) with a
  load note, not a scan result; an ordinary semgrep error keeps its code.
- edge: the wait budget fits inside each lefthook cap, is zero in a container
  and in CI, and a pytest timeout or testmon lock prints the host load.
"""

from __future__ import annotations

import io
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.validation import git_hook_policy as policy
from scripts.validation import host_headroom, pytest_lanes
from tests.validation.pre_push_testmon_helpers import (
    default_environment,  # noqa: F401  (fixture, applied by usefixtures below)
    record_runs,
)

pytestmark = pytest.mark.usefixtures("default_environment")

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _recording_slot(events: list[Any]) -> Any:
    @contextmanager
    def fake(stage: str, wait_budget: float, **_kwargs: Any) -> Iterator[host_headroom.Grant]:
        events.append(("enter", stage, wait_budget))
        try:
            yield host_headroom.Grant(slot=0, headroom=True, waited=0.0)
        finally:
            events.append(("exit", stage))

    return fake


def _lefthook_job_timeout(name: str) -> str:
    config = yaml.safe_load((_REPO_ROOT / "lefthook.yml").read_text(encoding="utf-8"))

    def walk(jobs: list[dict[str, Any]]) -> str | None:
        for job in jobs:
            if job.get("name") == name:
                return str(job["timeout"])
            nested = job.get("group", {}).get("jobs")
            if nested:
                found = walk(nested)
                if found is not None:
                    return found
        return None

    found = walk(config["pre-push"]["jobs"])
    assert found is not None, f"lefthook.yml pre-push has no job named {name}"
    return found


def _seconds(duration: str) -> int:
    assert duration.endswith("m"), duration
    return int(duration[:-1]) * 60


# --- pytest ---------------------------------------------------------------


def test_python_tests_job_cap_matches_lefthook() -> None:
    """The wait budget is carved from this cap, so it must be the real one."""
    cap = _seconds(_lefthook_job_timeout("python-tests"))
    assert cap == policy.PYTHON_TESTS_JOB_CAP_SECONDS


def test_pytest_takes_a_slot_before_its_budget_starts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[Any] = []
    monkeypatch.setattr(policy, "_heavy_stage_slot", _recording_slot(events))
    monkeypatch.setattr(policy, "_container_clamped", lambda seconds: seconds)
    real_start = policy._start_deadline

    def spy_start(budget: float) -> float:
        events.append(("deadline", budget))
        return real_start(budget)

    monkeypatch.setattr(policy, "_start_deadline", spy_start)

    def fake_run(command: list[str], *_a: object, **_k: object) -> subprocess.CompletedProcess[str]:
        events.append(("run",))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(policy, "_run_command", fake_run)
    monkeypatch.setattr(policy, "_print_process_output", lambda _r: None)
    assert policy.run_pytest(tmp_path) == 0
    kinds = [event[0] for event in events]
    assert kinds[0] == "enter"
    assert kinds[1] == "deadline"
    assert "run" in kinds
    assert kinds[-1] == "exit"
    assert events[0][1] == "pytest"


def test_pytest_wait_budget_fits_the_job_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CI", raising=False)
    selection = policy.PRE_PUSH_SELECTION_TIMEOUT_SECONDS
    wait = policy._pytest_headroom_wait_seconds(selection, selection)
    assert wait == (
        policy.PYTHON_TESTS_JOB_CAP_SECONDS - selection - policy.HEADROOM_MARGIN_SECONDS
    )
    assert wait + selection < policy.PYTHON_TESTS_JOB_CAP_SECONDS
    full = policy.TEST_SUITE_TIMEOUT_SECONDS
    assert policy._pytest_headroom_wait_seconds(full, full) == (
        policy.PYTHON_TESTS_JOB_CAP_SECONDS - full - policy.HEADROOM_MARGIN_SECONDS
    )


def test_pytest_wait_budget_is_never_negative(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CI", raising=False)
    assert policy._pytest_headroom_wait_seconds(5000, 5000) == 0


def test_pytest_does_not_wait_in_a_container(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CI", raising=False)
    assert policy._pytest_headroom_wait_seconds(180, 150) == 0


def test_pytest_does_not_wait_in_ci(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CI", "true")
    assert policy._pytest_headroom_wait_seconds(180, 180) == 0


def test_bad_headroom_setting_is_a_config_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    record_runs(monkeypatch)
    monkeypatch.setenv(host_headroom.SLOTS_ENV, "many")
    assert policy.run_pytest(tmp_path) == 2
    assert host_headroom.SLOTS_ENV in capsys.readouterr().err


def test_a_pytest_timeout_names_host_load(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    record_runs(monkeypatch, returncode=3, stderr=f"ERROR: pytest{policy.TIMEOUT_MARKER}180 s")
    monkeypatch.setattr(policy.host_headroom, "load_average", lambda: 12.0)
    monkeypatch.setenv(host_headroom.MAX_LOAD_ENV, "8")
    assert policy.run_pytest(tmp_path) == 3
    err = capsys.readouterr().err
    assert "NOTE: pytest: host load average is 12.0" in err
    assert "likely load" in err


def test_a_passing_run_prints_no_load_note(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    record_runs(monkeypatch)
    assert policy.run_pytest(tmp_path) == 0
    assert "host load average" not in capsys.readouterr().err


def test_a_testmon_lock_names_host_load(capsys: pytest.CaptureFixture[str]) -> None:
    result = subprocess.CompletedProcess(
        ["pytest"],
        3,
        "INTERNALERROR> sqlite3.OperationalError: database is locked\n",
        "",
    )
    report = pytest_lanes.PartitionReport("tests", result, 12.0)
    assert policy._report_partition(report, 180) == 3
    err = capsys.readouterr().err
    assert "database is locked" in err
    assert "host load average" in err


def test_an_ordinary_partition_failure_prints_no_load_note(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = subprocess.CompletedProcess(["pytest"], 1, "1 failed\n", "")
    report = pytest_lanes.PartitionReport("tests", result, 12.0)
    assert policy._report_partition(report, 180) == 1
    assert "host load average" not in capsys.readouterr().err


# --- semgrep --------------------------------------------------------------


def test_semgrep_wait_leaves_most_of_its_budget_for_the_scan() -> None:
    assert 0 < policy.SEMGREP_HEADROOM_WAIT_SECONDS <= policy.SEMGREP_TIMEOUT_SECONDS / 2
    assert policy.SEMGREP_TIMEOUT_SECONDS < _seconds(_lefthook_job_timeout("security-scan"))


def test_semgrep_does_not_wait_in_a_container_or_ci(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CI", raising=False)
    assert policy._semgrep_headroom_wait_seconds(policy.SEMGREP_TIMEOUT_SECONDS) == (
        policy.SEMGREP_HEADROOM_WAIT_SECONDS
    )
    assert policy._semgrep_headroom_wait_seconds(150) == 0
    monkeypatch.setenv("CI", "true")
    assert policy._semgrep_headroom_wait_seconds(policy.SEMGREP_TIMEOUT_SECONDS) == 0


def _update(head: str) -> policy.PushUpdate:
    source = policy.PushRef("refs/heads/a", "1" * 40, "refs/heads/a", "2" * 40)
    return policy.PushUpdate(source, "base", head, f"base..{head}", "a")


def _arrange_scan(monkeypatch: pytest.MonkeyPatch, paths: list[str], events: list[Any]) -> None:
    monkeypatch.setattr(policy, "_push_updates", lambda *_a: [_update("h1"), _update("h2")])
    monkeypatch.setattr(policy, "_changed_commit_paths", lambda *_a: paths)
    monkeypatch.setattr(policy, "_commit_paths", lambda *_a: paths)
    monkeypatch.setattr(policy, "_pushed_root_moves", lambda *_a: set())
    monkeypatch.setattr(policy, "_container_clamped", lambda seconds: seconds)
    monkeypatch.setattr(policy, "_heavy_stage_slot", _recording_slot(events))

    def fake_scan(head: str, *_a: object, **_k: object) -> int:
        events.append(("scan", head))
        return 0

    monkeypatch.setattr(policy, "_scan_pushed_head", fake_scan)


def test_semgrep_holds_one_slot_across_every_scanned_head(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("CI", raising=False)
    events: list[Any] = []
    _arrange_scan(monkeypatch, ["source.py"], events)
    assert policy.scan_pushed_heads(io.StringIO(""), tmp_path) == 0
    assert events == [
        ("enter", "semgrep", policy.SEMGREP_HEADROOM_WAIT_SECONDS),
        ("scan", "h1"),
        ("scan", "h2"),
        ("exit", "semgrep"),
    ]


def test_semgrep_takes_no_slot_when_nothing_is_scannable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[Any] = []
    _arrange_scan(monkeypatch, ["README.txt"], events)
    assert policy.scan_pushed_heads(io.StringIO(""), tmp_path) == 0
    assert events == []


def test_bad_headroom_setting_fails_the_scan_as_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    events: list[Any] = []
    _arrange_scan(monkeypatch, ["source.py"], events)
    monkeypatch.setattr(policy, "_heavy_stage_slot", host_headroom.heavy_stage_slot)
    monkeypatch.setenv(host_headroom.MAX_LOAD_ENV, "loud")
    assert policy.scan_pushed_heads(io.StringIO(""), tmp_path) == 2
    assert host_headroom.MAX_LOAD_ENV in capsys.readouterr().err


_CORE_FAILURE_STDOUT = (
    '{"errors":[{"code":2,"level":"error","type":"SemgrepError",'
    '"message":"Failed to obtain target files from semgrep-core"}],'
    '"paths":{"scanned":[]}}'
)


def _semgrep_returns(
    monkeypatch: pytest.MonkeyPatch, result: subprocess.CompletedProcess[str]
) -> None:
    monkeypatch.setattr(policy, "_semgrep_command", lambda _c, targets, *_a: ["semgrep", *targets])
    monkeypatch.setattr(policy, "_semgrep_target_batches", lambda targets, *_a: [list(targets)])
    monkeypatch.setattr(policy, "_run_command", lambda *_a, **_k: result)


def test_semgrep_core_target_failure_is_infrastructure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _semgrep_returns(
        monkeypatch,
        subprocess.CompletedProcess(
            ["semgrep"],
            2,
            _CORE_FAILURE_STDOUT,
            "RPC subprocess failed: semgrep-core exited with code 1.\n",
        ),
    )
    monkeypatch.setattr(policy.host_headroom, "load_average", lambda: 11.0)
    monkeypatch.setenv(host_headroom.MAX_LOAD_ENV, "8")
    result = policy._run_semgrep_tree(tmp_path, ["source.py"], tmp_path)
    assert result.returncode == 3
    assert "infrastructure failure, not a scan result" in result.stderr
    assert "NOTE: semgrep: host load average is 11.0" in result.stderr


def test_an_ordinary_semgrep_error_keeps_its_exit_code(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _semgrep_returns(
        monkeypatch,
        subprocess.CompletedProcess(["semgrep"], 2, "", "invalid configuration file\n"),
    )
    result = policy._run_semgrep_tree(tmp_path, ["source.py"], tmp_path)
    assert result.returncode == 2
    assert "infrastructure" not in result.stderr


# --- review round 1 -------------------------------------------------------


def test_a_test_failure_that_mentions_a_locked_database_prints_no_load_note(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Only testmon's own INTERNALERROR is a concurrent-writer lock, not a test's assertion."""
    result = subprocess.CompletedProcess(
        ["pytest"],
        1,
        "E   sqlite3.OperationalError: database is locked\n"
        "FAILED tests/test_store.py::test_write - sqlite3.OperationalError\n",
        "",
    )
    report = pytest_lanes.PartitionReport("tests", result, 12.0)
    assert policy._report_partition(report, 180) == 1
    err = capsys.readouterr().err
    assert "concurrent writer" not in err
    assert "host load average" not in err


def test_ci_turns_the_headroom_gate_off(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(host_headroom.SLOTS_ENV, "3")
    monkeypatch.setenv(host_headroom.MAX_LOAD_ENV, "8")
    monkeypatch.setenv(host_headroom.SLOT_DIR_ENV, str(tmp_path / "slots"))
    monkeypatch.setenv("CI", "true")
    settings = policy._headroom_settings()
    assert settings.slots == 0
    assert settings.max_load == 0
    monkeypatch.delenv("CI")
    assert policy._headroom_settings().slots == 3


def test_ci_pytest_prints_no_headroom_warning_under_high_load(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    record_runs(monkeypatch)
    monkeypatch.setenv(host_headroom.SLOTS_ENV, "3")
    monkeypatch.setenv(host_headroom.MAX_LOAD_ENV, "8")
    monkeypatch.setenv(host_headroom.SLOT_DIR_ENV, str(tmp_path / "slots"))
    monkeypatch.setenv("CI", "true")
    # The slot binds its load reader at definition, so inject a busy host here.
    monkeypatch.setattr(
        policy, "_heavy_stage_slot", partial(host_headroom.heavy_stage_slot, load=lambda: 40.0)
    )
    assert policy.run_pytest(tmp_path) == 0
    err = capsys.readouterr().err
    assert "no host headroom" not in err
    assert "waiting" not in err


def test_semgrep_budget_message_names_the_headroom_wait(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The headroom wait spends the scan's deadline, so the overrun message must say so."""
    events: list[Any] = []
    _arrange_scan(monkeypatch, ["source.py"], events)
    monkeypatch.setattr(policy, "_container_clamped", lambda _seconds: 0)
    assert policy.scan_pushed_heads(io.StringIO(""), tmp_path) == 1
    err = capsys.readouterr().err
    assert "exceeded its 0s budget" in err
    assert "wait for host headroom" in err

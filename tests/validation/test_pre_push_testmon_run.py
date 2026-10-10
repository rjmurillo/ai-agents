"""Running the testmon selection: environment, exit codes, and budget (issue #6239)."""

from __future__ import annotations

import inspect
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.validation import git_hook_policy
from tests.validation.pre_push_testmon_helpers import (
    default_environment,  # noqa: F401  (fixture, applied by usefixtures below)
    record_runs,
    testmon,
)

pytestmark = pytest.mark.usefixtures("default_environment")

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_default_pre_push_forces_the_ctrace_coverage_core(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """On Python 3.14 coverage defaults to sysmon, which under-records for testmon."""
    monkeypatch.setenv("COVERAGE_CORE", "sysmon")
    cores: list[str | None] = []

    def fake(
        command: list[str], _root: object, **kwargs: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        cores.append(kwargs["process_env"].get("COVERAGE_CORE"))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(git_hook_policy, "_run_command", fake)
    monkeypatch.setattr(git_hook_policy, "_print_process_output", lambda _r: None)
    assert git_hook_policy.run_pytest(tmp_path) == 0
    assert cores == ["ctrace"] * len(testmon(tmp_path))


def test_default_pre_push_asks_git_nothing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    record_runs(monkeypatch)
    monkeypatch.setattr(
        git_hook_policy,
        "_run_git",
        lambda *_a, **_k: pytest.fail("pre-push pytest must not ask git for a diff"),
    )
    assert git_hook_policy.run_pytest(tmp_path) == 0


@pytest.mark.parametrize("exit_code", [1, 2, 4])
def test_a_failing_testmon_run_blocks_the_push(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, exit_code: int
) -> None:
    record_runs(monkeypatch, returncode=exit_code)
    assert git_hook_policy.run_pytest(tmp_path) == exit_code


def test_the_full_suite_opt_in_does_not_use_testmon_or_force_a_coverage_core(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, "1")
    monkeypatch.setenv("COVERAGE_CORE", "sysmon")
    envs: list[dict[str, str]] = []

    def fake(
        command: list[str], _root: object, **kwargs: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        assert "--testmon" not in command
        envs.append(kwargs["process_env"])
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(git_hook_policy, "_run_command", fake)
    monkeypatch.setattr(git_hook_policy, "_print_process_output", lambda _r: None)
    assert git_hook_policy.run_pytest(tmp_path) == 0
    assert all(env.get("COVERAGE_CORE") == "sysmon" for env in envs)


def test_the_testmon_budget_is_the_suite_budget(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The first run builds the database over the whole suite, so it needs the full budget."""
    monkeypatch.setattr(git_hook_policy, "_container_clamped", lambda seconds: seconds)
    timeouts: list[float] = []

    def fake(args: object, _root: object, **kwargs: float) -> subprocess.CompletedProcess[str]:
        timeouts.append(kwargs["timeout_seconds"])
        return subprocess.CompletedProcess([], 0, "", "")

    monkeypatch.setattr(git_hook_policy, "_run_command", fake)
    monkeypatch.setattr(git_hook_policy, "_print_process_output", lambda _r: None)
    assert git_hook_policy.run_pytest(tmp_path) == 0
    assert git_hook_policy.TEST_SUITE_TIMEOUT_SECONDS - 5 < timeouts[0]
    assert timeouts[0] <= git_hook_policy.TEST_SUITE_TIMEOUT_SECONDS


def test_the_pytest_subcommand_rejects_a_path_argument() -> None:
    """argparse exits 2, so no caller can hand the hook a subset to run."""
    result = subprocess.run(
        [sys.executable, inspect.getfile(git_hook_policy), "pytest", "somefile.py"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 2
    assert "unrecognized arguments: somefile.py" in result.stderr

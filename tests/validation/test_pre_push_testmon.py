"""Pre-push runs the tests pytest-testmon selects, best effort.

Issue #6239, owner decision of 2026-10-09: the default pre-push pytest step
runs ``pytest --testmon`` over ``tests/`` so impacted tests execute locally.
Selection is best effort and CI still runs every leg in full. Nothing in the
hook module imports the repository's own import-graph selector.
"""

from __future__ import annotations

import ast
import inspect
import subprocess
import sys
from pathlib import Path

import pytest
import tomllib

from scripts.validation import git_hook_policy
from tests.validation.pre_push_testmon_helpers import (
    default_environment,  # noqa: F401  (fixture, applied by usefixtures below)
    record_runs,
    testmon,
)

pytestmark = pytest.mark.usefixtures("default_environment")

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_the_hook_module_does_not_import_the_selector() -> None:
    """Neither an import statement nor a module attribute names the old selector."""
    source = Path(inspect.getfile(git_hook_policy)).read_text(encoding="utf-8")
    imported = [
        name
        for node in ast.walk(ast.parse(source))
        for name in (
            [alias.name for alias in node.names]
            if isinstance(node, ast.Import)
            else [node.module or "", *(alias.name for alias in node.names)]
            if isinstance(node, ast.ImportFrom)
            else []
        )
    ]
    assert not [name for name in imported if "test_selection" in name or "select_tests" in name]
    assert not hasattr(git_hook_policy, "select_tests")


def test_run_pytest_takes_no_changed_files_parameter() -> None:
    """The hook never receives a diff: testmon, not the hook, decides what runs."""
    assert list(inspect.signature(git_hook_policy.run_pytest).parameters) == ["repo_root"]
    assert list(inspect.signature(git_hook_policy._resolve_pytest_commands).parameters) == [
        "repo_root"
    ]


def test_default_pre_push_resolves_to_the_testmon_commands(tmp_path: Path) -> None:
    assert git_hook_policy._resolve_pytest_commands(tmp_path) == testmon(tmp_path)


def test_every_testmon_command_selects_with_testmon_and_skips_integration(
    tmp_path: Path,
) -> None:
    for command in testmon(tmp_path):
        assert command[:3] == [sys.executable, "-m", "pytest"]
        assert "--testmon" in command
        assert any(arg.startswith("not integration") for arg in command)
        assert "--collect-only" not in command


def test_the_testmon_commands_are_the_full_suite_partitions_plus_the_flag(
    tmp_path: Path,
) -> None:
    """The serial safe-push and pr-autofix handling is kept, partition for partition."""
    full = git_hook_policy._pytest_commands(tmp_path)
    selected = testmon(tmp_path)
    assert len(selected) == len(full)
    for with_testmon, without in zip(selected, full, strict=True):
        flags = {"--testmon", "--testmon-forceselect"}
        assert [arg for arg in with_testmon if arg not in flags] == without


def test_testmon_selection_survives_the_marker_filter(tmp_path: Path) -> None:
    """testmon 2.2.0 turns selection off under ``-m`` unless forceselect is passed.

    Without the flag the run reports "selection automatically deactivated
    because -m was used" and executes the whole suite on every push.
    """
    for command in testmon(tmp_path):
        assert any(arg.startswith("not integration") for arg in command)
        assert "--testmon-forceselect" in command


def test_the_bulk_testmon_command_uses_worksteal_over_tests(tmp_path: Path) -> None:
    bulk = testmon(tmp_path)[0]
    assert bulk[bulk.index("--dist") + 1] == "worksteal"
    assert "-n" in bulk
    assert str(tmp_path / "tests") in bulk


def test_the_serial_testmon_partitions_take_no_worker_pool(tmp_path: Path) -> None:
    _bulk, _mutation, safe_push, pr_autofix = testmon(tmp_path)
    for serial in (safe_push, pr_autofix):
        assert "-n" not in serial
        assert "--dist" not in serial


def test_testmon_never_runs_with_the_cacheprovider_disabled(tmp_path: Path) -> None:
    """``-p no:cacheprovider`` crashes testmon with KeyError 'lf'."""
    for command in testmon(tmp_path):
        assert "no:cacheprovider" not in " ".join(command)


def test_default_pre_push_forces_the_ctrace_coverage_core(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """On Python 3.14 coverage defaults to sysmon, which under-records for testmon."""
    monkeypatch.setenv("COVERAGE_CORE", "sysmon")
    seen = record_runs(monkeypatch)
    assert git_hook_policy.run_pytest(tmp_path) == 0
    assert seen.commands == testmon(tmp_path)
    assert {env.get("COVERAGE_CORE") for env in seen.envs} == {"ctrace"}


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


def test_a_failing_first_partition_skips_the_rest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen = record_runs(monkeypatch, returncode=1)
    assert git_hook_policy.run_pytest(tmp_path) == 1
    assert len(seen.commands) == 1


def test_the_full_suite_opt_in_does_not_use_testmon_or_force_a_coverage_core(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, "1")
    seen = record_runs(monkeypatch)
    assert git_hook_policy.run_pytest(tmp_path) == 0
    assert seen.commands == git_hook_policy._pytest_commands(tmp_path)
    assert not any("--testmon" in command for command in seen.commands)
    assert all("COVERAGE_CORE" not in env for env in seen.envs)


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


def test_testmon_is_declared_in_both_dev_dependency_lists() -> None:
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    extra = data["project"]["optional-dependencies"]["dev"]
    group = data["dependency-groups"]["dev"]
    for name, entries in (("extra", extra), ("group", group)):
        assert any(entry.startswith("pytest-testmon") for entry in entries), name


def test_the_testmon_database_is_git_ignored() -> None:
    """``.testmondata`` is local state; its SQLite sidecars must not be committed either."""
    for name in (".testmondata", ".testmondata-shm", ".testmondata-wal"):
        result = subprocess.run(
            ["git", "check-ignore", "-q", name],
            cwd=REPO_ROOT,
            capture_output=True,
            check=False,
            timeout=30,
        )
        assert result.returncode == 0, f"{name} is not ignored"

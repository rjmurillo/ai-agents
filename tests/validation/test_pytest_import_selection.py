"""Import-graph test selection wired into the pre-push pytest runner."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.test_selection.select_tests import Selection
from scripts.validation import git_hook_policy


def _has_parallel_flag(command: list[str]) -> bool:
    return "-n" in command


def test_subset_splits_serial_and_parallel_partitions(tmp_path: Path) -> None:
    commands = git_hook_policy._pytest_commands_for_subset(
        tmp_path,
        [
            "tests/test_leaf.py",
            "tests/mutation/test_thing.py",
            "tests/test_safe_push_pr_branch.py",
            "tests/test_pr_autofix_late_live_state_gate.py",
        ],
    )
    assert len(commands) == 4
    bulk, mutation, safe_push, pr_autofix = commands
    assert _has_parallel_flag(bulk)
    assert _has_parallel_flag(mutation)
    assert not _has_parallel_flag(safe_push)
    assert not _has_parallel_flag(pr_autofix)
    assert str(tmp_path / "tests/test_leaf.py") in bulk
    assert "not integration and not safe_push_transport" in safe_push


def test_subset_emits_only_needed_partitions(tmp_path: Path) -> None:
    commands = git_hook_policy._pytest_commands_for_subset(tmp_path, ["tests/test_leaf.py"])
    assert len(commands) == 1
    assert str(tmp_path / "tests/test_leaf.py") in commands[0]


def _collection(tmp_path: Path) -> list[list[str]]:
    return [git_hook_policy._pytest_collection_command(tmp_path)]


def test_resolve_collects_when_diff_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, raising=False)
    monkeypatch.setattr(git_hook_policy.select_tests, "changed_from_git", lambda *_: None)
    commands = git_hook_policy._resolve_pytest_commands(tmp_path, None)
    assert commands == _collection(tmp_path)


def test_resolve_collects_on_full_verdict(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, raising=False)
    monkeypatch.setattr(
        git_hook_policy.select_tests,
        "select",
        lambda *_a, **_k: Selection(full=True, reason="non-Python change"),
    )
    commands = git_hook_policy._resolve_pytest_commands(tmp_path, ["README.md"])
    assert commands == _collection(tmp_path)


def test_collection_command_runs_no_test_bodies(tmp_path: Path) -> None:
    command = git_hook_policy._pytest_collection_command(tmp_path)
    assert "--collect-only" in command
    assert "not integration" in command
    assert str(tmp_path / "tests") in command
    # A parallel flag would start workers for a run that never executes a test.
    assert not _has_parallel_flag(command)


def test_opt_in_env_restores_local_full_suite_execution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The escape hatch has to actually reach the executing partitions.

    Without this, the default could quietly become the only behavior and the
    documented override in `lefthook.yml` and ADR-103 would be a dead string.
    """
    monkeypatch.setenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, "1")
    monkeypatch.setattr(
        git_hook_policy.select_tests,
        "select",
        lambda *_a, **_k: Selection(full=True, reason="non-Python change"),
    )
    commands = git_hook_policy._resolve_pytest_commands(tmp_path, ["README.md"])
    assert commands == git_hook_policy._pytest_commands(tmp_path)


def test_opt_in_env_ignores_values_other_than_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, "0")
    monkeypatch.setattr(
        git_hook_policy.select_tests,
        "select",
        lambda *_a, **_k: Selection(full=True, reason="non-Python change"),
    )
    commands = git_hook_policy._resolve_pytest_commands(tmp_path, ["README.md"])
    assert commands == _collection(tmp_path)


def test_collection_gets_the_collection_budget_not_the_suite_budget(tmp_path: Path) -> None:
    """A collection hang must not be able to block a push for 29 minutes."""
    collection = _collection(tmp_path)
    assert (
        git_hook_policy._pytest_budget_seconds(collection)
        == git_hook_policy.TEST_COLLECTION_TIMEOUT_SECONDS
    )
    assert (
        git_hook_policy.TEST_COLLECTION_TIMEOUT_SECONDS
        < git_hook_policy.TEST_SUITE_TIMEOUT_SECONDS
    )


def test_executing_commands_keep_the_suite_budget(tmp_path: Path) -> None:
    executing = git_hook_policy._pytest_commands(tmp_path)
    assert (
        git_hook_policy._pytest_budget_seconds(executing)
        == git_hook_policy.TEST_SUITE_TIMEOUT_SECONDS
    )


def test_subset_of_one_file_is_not_mistaken_for_a_collection_run(tmp_path: Path) -> None:
    """The budget switch keys on `--collect-only`, not on the command count."""
    subset = git_hook_policy._pytest_commands_for_subset(tmp_path, ["tests/test_leaf.py"])
    assert len(subset) == 1
    assert (
        git_hook_policy._pytest_budget_seconds(subset)
        == git_hook_policy.TEST_SUITE_TIMEOUT_SECONDS
    )


def test_resolve_uses_subset_on_narrowed_verdict(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        git_hook_policy.select_tests,
        "select",
        lambda *_a, **_k: Selection(
            full=False, reason="import-graph subset", tests=("tests/test_leaf.py",)
        ),
    )
    commands = git_hook_policy._resolve_pytest_commands(tmp_path, ["pkg/leaf.py"])
    assert commands == git_hook_policy._pytest_commands_for_subset(
        tmp_path, ("tests/test_leaf.py",)
    )
    assert "import graph" in capsys.readouterr().err


def test_resolve_explains_why_it_collected_instead_of_executing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The narrowed path announced itself and the fallback stayed silent.

    That was fine while the fallback ran everything, because silence meant the
    strongest behavior. It now means the weaker one, so a reader who sees a
    fast pre-push has to be told the suite was collected rather than run, and
    where the execution went.
    """
    monkeypatch.delenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, raising=False)
    monkeypatch.setattr(git_hook_policy.select_tests, "changed_from_git", lambda *_: None)
    git_hook_policy._resolve_pytest_commands(tmp_path, None)
    err = capsys.readouterr().err
    assert "Collecting every test" in err
    assert "pytest.yml" in err
    assert git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV in err

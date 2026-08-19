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


def test_resolve_falls_back_to_full_when_diff_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(git_hook_policy.select_tests, "changed_from_git", lambda *_: None)
    commands = git_hook_policy._resolve_pytest_commands(tmp_path, None)
    assert commands == git_hook_policy._pytest_commands(tmp_path)


def test_resolve_falls_back_to_full_on_full_verdict(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        git_hook_policy.select_tests,
        "select",
        lambda *_a, **_k: Selection(full=True, reason="non-Python change"),
    )
    commands = git_hook_policy._resolve_pytest_commands(tmp_path, ["README.md"])
    assert commands == git_hook_policy._pytest_commands(tmp_path)


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


def test_resolve_is_silent_on_full_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(git_hook_policy.select_tests, "changed_from_git", lambda *_: None)
    git_hook_policy._resolve_pytest_commands(tmp_path, None)
    assert capsys.readouterr().err == ""

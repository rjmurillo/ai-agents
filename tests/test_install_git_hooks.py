"""Tests for scripts/install_git_hooks.py."""

from __future__ import annotations

import stat
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts import install_git_hooks as igh  # noqa: E402


def _make_hook(path: Path, *, executable: bool = True) -> None:
    path.write_text("#!/bin/bash\nexit 0\n")
    if executable:
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)


def _init_repo(root: Path, *, with_hooks: bool = True) -> Path:
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    if with_hooks:
        hooks = root / ".githooks"
        hooks.mkdir()
        for name in igh.REQUIRED_HOOKS:
            _make_hook(hooks / name)
    return root


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return _init_repo(tmp_path / "repo")


def _hooks_path(root: Path) -> str:
    result = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip()


# --- happy path -----------------------------------------------------------


def test_sets_hooks_path(repo: Path) -> None:
    assert igh.main(["--repo-root", str(repo)]) == igh.EXIT_OK
    assert _hooks_path(repo) == igh.HOOKS_DIR_NAME


def test_idempotent_second_run(repo: Path) -> None:
    assert igh.main(["--repo-root", str(repo)]) == igh.EXIT_OK
    # Second run must not fail and must keep the value.
    assert igh.main(["--repo-root", str(repo)]) == igh.EXIT_OK
    assert _hooks_path(repo) == igh.HOOKS_DIR_NAME


def test_check_passes_after_install(repo: Path) -> None:
    igh.main(["--repo-root", str(repo)])
    assert igh.main(["--repo-root", str(repo), "--check"]) == igh.EXIT_OK


# --- check mode (non-mutating) -------------------------------------------


def test_check_fails_when_unconfigured(repo: Path) -> None:
    # Not installed yet -> logic failure, and config left untouched.
    assert igh.main(["--repo-root", str(repo), "--check"]) == igh.EXIT_LOGIC
    assert _hooks_path(repo) == ""


# --- negative / edge cases -----------------------------------------------


def test_not_a_git_repo(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    assert igh.main(["--repo-root", str(plain)]) == igh.EXIT_CONFIG


def test_missing_githooks_dir(tmp_path: Path) -> None:
    root = _init_repo(tmp_path / "norepo", with_hooks=False)
    assert igh.main(["--repo-root", str(root)]) == igh.EXIT_CONFIG


def test_hook_not_executable_is_logic_error(repo: Path) -> None:
    pre_push = repo / ".githooks" / "pre-push"
    pre_push.chmod(pre_push.stat().st_mode & ~stat.S_IXUSR & ~stat.S_IXGRP)
    assert igh.main(["--repo-root", str(repo)]) == igh.EXIT_LOGIC


def test_legacy_shim_warning(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    legacy = repo / ".git" / "hooks"
    legacy.mkdir(parents=True, exist_ok=True)
    _make_hook(legacy / "pre-push")
    assert igh.main(["--repo-root", str(repo)]) == igh.EXIT_OK
    out = capsys.readouterr().out
    assert "shadowed" in out


def test_quiet_suppresses_success_output(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert igh.main(["--repo-root", str(repo), "--quiet"]) == igh.EXIT_OK
    assert capsys.readouterr().out == ""


# --- unit: canonical path resolution -------------------------------------


def test_points_at_canonical_relative(repo: Path) -> None:
    assert igh.hooks_path_points_at_canonical(repo, ".githooks") is True


def test_points_at_canonical_absolute(repo: Path) -> None:
    abs_path = str((repo / ".githooks").resolve())
    # Absolute paths are drift that breaks worktrees - must be rejected.
    assert igh.hooks_path_points_at_canonical(repo, abs_path) is False


def test_points_at_canonical_rejects_default(repo: Path) -> None:
    assert igh.hooks_path_points_at_canonical(repo, ".git/hooks") is False


def test_points_at_canonical_rejects_none(repo: Path) -> None:
    assert igh.hooks_path_points_at_canonical(repo, None) is False

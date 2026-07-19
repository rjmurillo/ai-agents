#!/usr/bin/env python3
"""Tests for invoke_git_hooks_activation.py SessionStart hook (Issue #3182).

The hook guarantees ``core.hooksPath`` points at ``.githooks`` for every local
agent session by delegating to the idempotent installer
``scripts/install_git_hooks.py``. Coverage follows TESTING-RIGOR (pos + neg +
edge, mocked subprocess for unit paths, real end-to-end wiring for the
integration paths):

- REQ-1 (positive): a fresh repo with ``.githooks`` gets ``core.hooksPath`` set,
  proven end-to-end by running the real hook against a real installer.
- REQ-2 (negative): a repo without ``.githooks`` is a no-op, no config write.
- REQ-3 (edge): the installer is invoked with ``--quiet`` so an already
  configured clone stays silent.
- REQ-4 (edge): installer failure or a missing/unrunnable installer produces a
  one-line warning naming the manual fix and never raises.
- Fail-open: an internal error still exits 0.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = str(_REPO_ROOT / ".claude" / "hooks" / "SessionStart")
sys.path.insert(0, HOOKS_DIR)

import invoke_git_hooks_activation as hook  # noqa: E402

HOOK_PATH = _REPO_ROOT / ".claude" / "hooks" / "SessionStart" / "invoke_git_hooks_activation.py"
REAL_INSTALLER = _REPO_ROOT / "scripts" / "install_git_hooks.py"


# --------------------------------------------------------------------------- #
# Unit tests: activate() with a mocked installer subprocess                    #
# --------------------------------------------------------------------------- #


def _stub_installer(root: Path) -> Path:
    """Create an empty stand-in installer so activate() reaches subprocess."""
    scripts = root / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    installer = scripts / "install_git_hooks.py"
    installer.write_text("# stub\n", encoding="utf-8")
    return installer


def test_no_githooks_dir_is_noop(tmp_path: Path, monkeypatch, capsys) -> None:
    """REQ-2: no .githooks -> return without invoking the installer or warning."""
    run = MagicMock(side_effect=AssertionError("subprocess must not run"))
    monkeypatch.setattr(hook.subprocess, "run", run)

    hook.activate(str(tmp_path))

    run.assert_not_called()
    assert capsys.readouterr().err == ""


def test_missing_installer_warns(tmp_path: Path, monkeypatch, capsys) -> None:
    """Edge: .githooks present but installer absent -> warn, no subprocess."""
    (tmp_path / ".githooks").mkdir()
    run = MagicMock(side_effect=AssertionError("subprocess must not run"))
    monkeypatch.setattr(hook.subprocess, "run", run)

    hook.activate(str(tmp_path))

    run.assert_not_called()
    err = capsys.readouterr().err
    assert hook.MANUAL_FIX in err
    assert "installer not found" in err


def test_installer_invoked_quiet_when_present(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """REQ-1/REQ-3: installer runs with --quiet --repo-root; success is silent."""
    (tmp_path / ".githooks").mkdir()
    installer = _stub_installer(tmp_path)
    run = MagicMock(
        return_value=SimpleNamespace(returncode=0, stdout="", stderr="")
    )
    monkeypatch.setattr(hook.subprocess, "run", run)

    hook.activate(str(tmp_path))

    run.assert_called_once()
    argv = run.call_args.args[0]
    assert argv == [
        sys.executable,
        str(installer),
        "--quiet",
        "--repo-root",
        str(tmp_path),
    ]
    assert run.call_args.kwargs["timeout"] == hook.INSTALLER_TIMEOUT_SECONDS
    assert capsys.readouterr().err == ""


def test_installer_nonzero_exit_warns(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """REQ-4: a non-zero installer exit surfaces one warning, no raise."""
    (tmp_path / ".githooks").mkdir()
    _stub_installer(tmp_path)
    run = MagicMock(
        return_value=SimpleNamespace(
            returncode=3,
            stdout="",
            stderr="error: failed to set core.hooksPath",
        )
    )
    monkeypatch.setattr(hook.subprocess, "run", run)

    hook.activate(str(tmp_path))

    err = capsys.readouterr().err
    assert hook.MANUAL_FIX in err
    assert "failed to set core.hooksPath" in err


def test_installer_nonzero_exit_no_detail_warns(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """REQ-4: non-zero exit with empty output still names the exit code."""
    (tmp_path / ".githooks").mkdir()
    _stub_installer(tmp_path)
    run = MagicMock(
        return_value=SimpleNamespace(returncode=2, stdout="", stderr="")
    )
    monkeypatch.setattr(hook.subprocess, "run", run)

    hook.activate(str(tmp_path))

    err = capsys.readouterr().err
    assert "installer exited 2" in err
    assert hook.MANUAL_FIX in err


def test_subprocess_oserror_warns(tmp_path: Path, monkeypatch, capsys) -> None:
    """Edge: an OSError launching the installer warns and does not raise."""
    (tmp_path / ".githooks").mkdir()
    _stub_installer(tmp_path)
    run = MagicMock(side_effect=OSError("no python"))
    monkeypatch.setattr(hook.subprocess, "run", run)

    hook.activate(str(tmp_path))

    err = capsys.readouterr().err
    assert hook.MANUAL_FIX in err


def test_subprocess_timeout_warns(tmp_path: Path, monkeypatch, capsys) -> None:
    """Edge: a hung installer (timeout) warns and does not raise."""
    (tmp_path / ".githooks").mkdir()
    _stub_installer(tmp_path)
    run = MagicMock(side_effect=subprocess.TimeoutExpired(cmd="x", timeout=10))
    monkeypatch.setattr(hook.subprocess, "run", run)

    hook.activate(str(tmp_path))

    assert hook.MANUAL_FIX in capsys.readouterr().err


def test_project_directory_prefers_env(tmp_path: Path, monkeypatch) -> None:
    """project_directory honors CLAUDE_PROJECT_DIR over cwd."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    assert hook.project_directory() == str(tmp_path.resolve())


# --------------------------------------------------------------------------- #
# Integration tests: run the real hook against a real installer + temp repo    #
# --------------------------------------------------------------------------- #


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("GIT_DIR", "GIT_WORK_TREE")
    }
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def _make_repo(tmp_path: Path, *, with_githooks: bool) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    assert _git(repo, "init", "-q").returncode == 0
    if with_githooks:
        githooks = repo / ".githooks"
        githooks.mkdir()
        for name in ("pre-commit", "pre-push"):
            path = githooks / name
            path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            path.chmod(0o755)
        scripts = repo / "scripts"
        scripts.mkdir()
        shutil.copy(REAL_INSTALLER, scripts / "install_git_hooks.py")
    return repo


def _run_hook(repo: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(repo)
    return subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        cwd=str(repo),
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
def test_end_to_end_sets_hookspath(tmp_path: Path) -> None:
    """REQ-1: real hook + real installer set core.hooksPath in a fresh repo."""
    repo = _make_repo(tmp_path, with_githooks=True)
    assert _git(repo, "config", "--get", "core.hooksPath").returncode != 0

    result = _run_hook(repo)

    assert result.returncode == 0, result.stderr
    got = _git(repo, "config", "--get", "core.hooksPath")
    assert got.returncode == 0
    assert got.stdout.strip() == ".githooks"


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
def test_end_to_end_idempotent_second_run_silent(tmp_path: Path) -> None:
    """REQ-3: a second run on an already-configured repo writes nothing new."""
    repo = _make_repo(tmp_path, with_githooks=True)
    assert _run_hook(repo).returncode == 0

    result = _run_hook(repo)

    assert result.returncode == 0
    assert result.stdout.strip() == ""
    assert _git(repo, "config", "--get", "core.hooksPath").stdout.strip() == (
        ".githooks"
    )


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
def test_end_to_end_no_githooks_leaves_config_unset(tmp_path: Path) -> None:
    """REQ-2: a consumer repo without .githooks is untouched and exits 0."""
    repo = _make_repo(tmp_path, with_githooks=False)

    result = _run_hook(repo)

    assert result.returncode == 0
    assert _git(repo, "config", "--get", "core.hooksPath").returncode != 0

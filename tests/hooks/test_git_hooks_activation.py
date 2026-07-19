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


@pytest.fixture(autouse=True)
def _isolate_git_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralize inherited git config so the activation assertions are hermetic.

    ``tests/conftest.py`` injects ``GIT_CONFIG_COUNT``/``GIT_CONFIG_KEY_0`` for
    commit signing, and an earlier test can leak a higher count carrying a
    relative ``core.hooksPath``. Both ``_git`` and ``_run_hook`` snapshot
    ``os.environ`` at call time, so cleaning it here makes every
    ``git config --get core.hooksPath`` read only the temp repo. Without this,
    ``test_end_to_end_no_githooks_leaves_config_unset`` is order-dependent: a
    leaked relative hooksPath makes an unconfigured repo look configured. These
    tests never commit, so dropping the whole ``GIT_CONFIG_*`` family is safe.
    Mirrors ``tests/test_install_git_hooks.py::_isolate_git_global_config``.
    """
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    monkeypatch.delenv("GIT_CONFIG_PARAMETERS", raising=False)
    for name in [k for k in os.environ if k.startswith("GIT_CONFIG_")]:
        if name in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM"):
            continue
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def trusted_self(monkeypatch):
    """Treat activate()'s target as the self-repository (bypass the trust gate).

    ``_is_self_repository`` is exercised by dedicated tests; the installer-path
    unit tests below assume the self case so they can focus on installer
    invocation and error handling.
    """
    monkeypatch.setattr(hook, "_is_self_repository", lambda root: True)


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


def test_missing_installer_warns(tmp_path: Path, monkeypatch, capsys, trusted_self) -> None:
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
    tmp_path: Path, monkeypatch, capsys, trusted_self
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
    tmp_path: Path, monkeypatch, capsys, trusted_self
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
    tmp_path: Path, monkeypatch, capsys, trusted_self
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


def test_subprocess_oserror_warns(tmp_path: Path, monkeypatch, capsys, trusted_self) -> None:
    """Edge: an OSError launching the installer warns and does not raise."""
    (tmp_path / ".githooks").mkdir()
    _stub_installer(tmp_path)
    run = MagicMock(side_effect=OSError("no python"))
    monkeypatch.setattr(hook.subprocess, "run", run)

    hook.activate(str(tmp_path))

    err = capsys.readouterr().err
    assert hook.MANUAL_FIX in err


def test_subprocess_timeout_warns(tmp_path: Path, monkeypatch, capsys, trusted_self) -> None:
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
    monkeypatch.setattr(
        hook.subprocess, "run", MagicMock(side_effect=OSError("no git"))
    )
    assert hook.project_directory() == str(tmp_path.resolve())


def test_is_self_repository_true_when_hook_inside_root() -> None:
    """The real hook lives under the repo root -> trusted self case."""
    assert hook._is_self_repository(_REPO_ROOT) is True


def test_is_self_repository_false_for_foreign_root(tmp_path: Path) -> None:
    """A root that does not contain this hook file -> untrusted (consumer)."""
    assert hook._is_self_repository(tmp_path) is False


def test_foreign_repo_with_installer_is_noop(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """RCE mitigation: .githooks and an installer are present but the running
    hook is not tracked inside root -> no subprocess, no warning, no write."""
    (tmp_path / ".githooks").mkdir()
    _stub_installer(tmp_path)
    run = MagicMock(
        side_effect=AssertionError("installer must not run in a foreign repo")
    )
    monkeypatch.setattr(hook.subprocess, "run", run)

    hook.activate(str(tmp_path))

    run.assert_not_called()
    assert capsys.readouterr().err == ""


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
        timeout=30,
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


def _install_hook_copy(repo: Path) -> Path:
    """Copy the hook into ``repo`` so ``__file__`` resolves to a path under root.

    The self-repository trust gate only runs the installer when the hook lives
    inside the repo it activates. Positive end-to-end tests therefore run a copy
    placed inside the temp repo, matching how a real ai-agents clone keeps the
    hook file under its own root.
    """
    dest_dir = repo / ".claude" / "hooks" / "SessionStart"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "invoke_git_hooks_activation.py"
    shutil.copy(HOOK_PATH, dest)
    return dest


def _run_hook(
    repo: Path, *, hook_path: Path | None = None
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(repo)
    return subprocess.run(
        [sys.executable, str(hook_path or HOOK_PATH)],
        cwd=str(repo),
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
def test_end_to_end_sets_hookspath(tmp_path: Path) -> None:
    """REQ-1: real hook + real installer set core.hooksPath in a fresh repo.

    Runs a copy of the hook placed inside the repo so the self-repository trust
    gate treats it as the dogfooding (self) case.
    """
    repo = _make_repo(tmp_path, with_githooks=True)
    hook_copy = _install_hook_copy(repo)
    assert _git(repo, "config", "--get", "core.hooksPath").returncode != 0

    result = _run_hook(repo, hook_path=hook_copy)

    assert result.returncode == 0, result.stderr
    assert "[WARNING]" not in result.stderr, result.stderr
    got = _git(repo, "config", "--get", "core.hooksPath")
    assert got.returncode == 0
    assert got.stdout.strip() == ".githooks"


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
def test_end_to_end_idempotent_second_run_silent(tmp_path: Path) -> None:
    """REQ-3: a second run on an already-configured repo writes nothing new."""
    repo = _make_repo(tmp_path, with_githooks=True)
    hook_copy = _install_hook_copy(repo)
    first = _run_hook(repo, hook_path=hook_copy)
    assert first.returncode == 0
    assert "[WARNING]" not in first.stderr, first.stderr

    result = _run_hook(repo, hook_path=hook_copy)

    assert result.returncode == 0
    assert result.stdout.strip() == ""
    assert "[WARNING]" not in result.stderr, result.stderr
    assert _git(repo, "config", "--get", "core.hooksPath").stdout.strip() == (
        ".githooks"
    )


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
def test_end_to_end_no_githooks_leaves_config_unset(tmp_path: Path) -> None:
    """REQ-2: a consumer repo without .githooks is untouched and exits 0."""
    repo = _make_repo(tmp_path, with_githooks=False)
    hook_copy = _install_hook_copy(repo)

    result = _run_hook(repo, hook_path=hook_copy)

    assert result.returncode == 0
    assert _git(repo, "config", "--get", "core.hooksPath").returncode != 0


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
def test_project_directory_walks_up_to_repo_root(tmp_path: Path, monkeypatch) -> None:
    """project_directory resolves the git top level from a nested subdirectory."""
    repo = _make_repo(tmp_path, with_githooks=False)
    nested = repo / "a" / "b"
    nested.mkdir(parents=True)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.chdir(nested)

    assert hook.project_directory() == str(repo.resolve())


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
def test_end_to_end_foreign_repo_does_not_execute_installer(tmp_path: Path) -> None:
    """RCE regression: the shipped hook (outside the target repo) must not run a
    hostile repo's scripts/install_git_hooks.py.

    Runs the real HOOK_PATH (which lives in the ai-agents checkout, outside the
    temp repo) against a temp repo whose installer writes a sentinel. The trust
    gate must refuse to run it, leaving core.hooksPath unset and no sentinel.
    """
    repo = _make_repo(tmp_path, with_githooks=True)
    sentinel = repo / "PWNED"
    (repo / "scripts" / "install_git_hooks.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(sentinel)!r}).write_text('x')\n",
        encoding="utf-8",
    )

    result = _run_hook(repo)

    assert result.returncode == 0
    assert not sentinel.exists()
    assert _git(repo, "config", "--get", "core.hooksPath").returncode != 0

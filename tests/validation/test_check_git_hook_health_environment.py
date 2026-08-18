"""Environment contracts for the local git-hook health gate (PR #5122 review)."""

from __future__ import annotations

import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import check_git_hook_health


@pytest.mark.parametrize(("variable", "value"), [("GITHUB_ACTIONS", "true"), ("CI", "1")])
def test_ci_skips_the_local_clone_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    variable: str,
    value: str,
) -> None:
    # Copilot review on aef6e3a: CI does not install local pre-push hooks.
    (tmp_path / "lefthook.yml").write_text("pre-push: {}\n", encoding="utf-8")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv(variable, value)
    monkeypatch.setattr(
        check_git_hook_health,
        "_hooks_dir",
        lambda _repo_root: pytest.fail("CI must not inspect local hook installation"),
    )

    assert check_git_hook_health.main([str(tmp_path)]) == 0


def test_git_pins_the_diagnostic_locale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Copilot review on aef6e3a: non-repository detection must not depend on locale.
    def fake_run(*_args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        env = kwargs["env"]
        assert isinstance(env, dict)
        assert env["LC_ALL"] == "C"
        return subprocess.CompletedProcess(
            args=["git"],
            returncode=128,
            stdout="",
            stderr="fatal: not a git repository",
        )

    monkeypatch.setattr(check_git_hook_health.shutil, "which", lambda _name: "/git")
    monkeypatch.setattr(check_git_hook_health.subprocess, "run", fake_run)
    monkeypatch.setenv("PATH", os.environ.get("PATH", ""))

    with pytest.raises(check_git_hook_health.NotGitRepositoryError):
        check_git_hook_health._git(tmp_path, "rev-parse", "--git-path", "hooks")


def test_scratch_git_helpers_isolate_host_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helpers = runpy.run_path(str(Path(__file__).with_name("test_check_git_hook_health.py")))
    observed: list[object] = []

    def fake_run(*_args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        observed.append(kwargs.get("env"))
        return subprocess.CompletedProcess(args=["git"], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    helpers["_git"](tmp_path, "status")
    helpers["_run_cli"](tmp_path)

    assert all(
        isinstance(env, dict) and env.get("GIT_CONFIG_NOSYSTEM") == "1"
        for env in observed
    )
    assert all(
        isinstance(env, dict) and env.get("GIT_CONFIG_GLOBAL") == os.devnull
        for env in observed
    )


def test_non_directory_hooks_path_is_reported_accurately(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hooks_path = tmp_path / "hooks-file"
    hooks_path.write_text("disabled\n", encoding="utf-8")
    monkeypatch.setattr(
        check_git_hook_health,
        "_configured_hooks_path",
        lambda _repo_root: (str(hooks_path), "local"),
    )

    reason = check_git_hook_health._failed_condition(tmp_path, hooks_path)

    assert "exists but is not a directory" in reason

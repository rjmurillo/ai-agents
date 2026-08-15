"""Git execution-delegation, remote, and pager tests.

Split from the former single ``tests/hooks/test_push_pr_script_identity_guard.py``
(issue #4764), which had grown to 2,077 lines and carried the whole policy
matrix for both harnesses in one module. Dispatcher runners, the payload shape,
and the temporary repository layout live in
``tests/hooks/push_pr_guard_harness.py`` so no module re-derives them.

Issue #5013 retired the guard from the generated Copilot shim tree
(dispatch_groups.json marks it copilotExclude, so the generator omits it).
Every case here now runs through the Claude dispatcher only, which is where
the guard still runs; invoke_dispatch_claude.py does not read
copilotExclude.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tests.hooks.push_pr_guard_harness import (
    RUNNERS as _RUNNERS,
)
from tests.hooks.push_pr_guard_harness import (
    repository as _repository,
)

IN_SCOPE_ASSIGNMENT = "PUSH_PR_SCRIPT=new_pr.py "


def _in_scope(command: str) -> str:
    """Return ``command`` placed inside the guard's relevance scope."""
    if "new_pr.py" in command:
        return command
    return IN_SCOPE_ASSIGNMENT + command


@pytest.mark.parametrize("runner", _RUNNERS)
def test_dispatchers_fail_closed_on_unknown_git_global_options(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)

    result = runner(_in_scope("git --unknown-global status --short"), repository)

    assert result.returncode == 2
    assert "unsupported Git global options are not allowed" in result.stderr


@pytest.mark.parametrize("runner", _RUNNERS)
def test_dispatchers_allow_git_commands_with_active_hooks(
    tmp_path: Path,
    runner,
) -> None:
    """Git commands in a repository with active hooks are out of scope.

    A Git hook can execute repository-controlled code, but a Git command that
    never names new_pr.py is not a push-pr identity question. Denying it made
    the plugin block ordinary Git work (issue #4825 review 4894113215). The
    in-scope counterpart below keeps the delegation policy under test.
    """
    repository, _ = _repository(tmp_path)
    subprocess.run(
        ["git", "init", "--quiet"],
        cwd=repository,
        check=True,
    )
    hook = repository / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    hook.chmod(0o755)

    allowed_commands = (
        "git commit --allow-empty -m test",
        "env -- X=1 git commit --allow-empty -m test",
        "env -- a-b=1 git commit --allow-empty -m test",
        "git grep pattern -- pyproject.toml",
        "git pull . HEAD",
        "git update-ref refs/heads/guard-probe HEAD",
        "git worktree add --detach ../guard-probe HEAD",
    )

    for command in allowed_commands:
        allowed = runner(command, repository)
        assert allowed.returncode == 0, f"{command}: {allowed.stderr}"


@pytest.mark.parametrize("runner", _RUNNERS)
def test_dispatchers_deny_in_scope_git_commands_with_active_hooks(
    tmp_path: Path,
    runner,
) -> None:
    """Active Git hooks remain an execution channel for in-scope commands."""
    repository, _ = _repository(tmp_path)
    subprocess.run(
        ["git", "init", "--quiet"],
        cwd=repository,
        check=True,
    )
    hook = repository / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    hook.chmod(0o755)

    denied_commands = (
        "git commit --allow-empty -m test",
        "git pull . HEAD",
        "git update-ref refs/heads/guard-probe HEAD",
        "git worktree add --detach ../guard-probe HEAD",
    )

    for command in denied_commands:
        denied = runner(_in_scope(command), repository)
        assert denied.returncode == 2, command
        assert "dynamic evaluator wrappers are not allowed" in denied.stderr


@pytest.mark.parametrize("runner", _RUNNERS)
@pytest.mark.parametrize(
    "remote",
    [
        ".",
        "./attacker.git",
        "../attacker.git",
        "/attacker.git",
        "file:///attacker.git",
        "C:/attacker.git",
        r"C:\attacker.git",
        "//server/share/attacker.git",
        r"\\server\share\attacker.git",
    ],
)
def test_dispatchers_deny_local_git_push_destinations(
    tmp_path: Path,
    runner,
    remote: str,
) -> None:
    repository, _ = _repository(tmp_path)

    result = runner(_in_scope(f"env git push {remote} HEAD"), repository)

    assert result.returncode == 2
    assert "dynamic evaluator wrappers are not allowed" in result.stderr


@pytest.mark.parametrize("runner", _RUNNERS)
def test_dispatchers_allow_named_https_push_remote(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)
    shutil.rmtree(repository / ".git")
    subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
    subprocess.run(
        [
            "git",
            "remote",
            "add",
            "origin",
            "https://example.com/repository.git",
        ],
        cwd=repository,
        check=True,
    )

    result = runner("env git push origin HEAD", repository)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("runner", _RUNNERS)
def test_dispatchers_deny_named_local_push_remote(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)
    shutil.rmtree(repository / ".git")
    subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "./attacker.git"],
        cwd=repository,
        check=True,
    )

    result = runner(_in_scope("env git push origin HEAD"), repository)

    assert result.returncode == 2
    assert "dynamic evaluator wrappers are not allowed" in result.stderr


@pytest.mark.parametrize("runner", _RUNNERS)
def test_dispatchers_deny_renamed_git_executable(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)
    git = shutil.which("git")
    if git is None:
        pytest.skip("git unavailable")
    renamed_git = repository / "mygit"
    shutil.copy2(git, renamed_git)
    renamed_git.chmod(0o755)

    result = runner(_in_scope("./mygit fetch ext::./p"), repository)

    assert result.returncode == 2
    assert "dynamic evaluator wrappers are not allowed" in result.stderr



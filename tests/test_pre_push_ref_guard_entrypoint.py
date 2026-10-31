"""Replay the pre-push destination-ref guard through the real CLI entrypoint.

Issue #6815 asks for behavior-preservation evidence on existing entrypoints.
``tests/test_lefthook_integration.py`` pins the #6671 fix by calling
``policy.check_push_refs`` in-process with the review-marker, plugin-version and
infrastructure policies stubbed. It also drives the real ``push-ref-policy``
lefthook job, but only for an update from a feature checkout. Nothing runs the
documented command ``git_hook_policy.py pre-push`` as a child process with the
ref lines on stdin for the case #6671 broke: deleting a feature branch while the
checked-out branch is ``main``.

These tests close that gap. Each case runs the script as the hook runs it:

* a fresh interpreter, so no sibling test module has mutated ``sys.path``;
* a working directory that is neither the repository nor the fixture repo;
* a fixture repository whose path contains a space;
* a hermetic environment with no git config, no ``GIT_*`` leakage and no
  credentials;
* a before/after check that the run changed no ref, no tracked status and no
  file in the repository or the foreign working directory.

The legitimate-work control (a feature delete from a ``main`` checkout) pairs
with the refusals (``main`` and ``master`` deletes, a ``main`` update from a
feature checkout, and mixed pushes in both ref orders). Updates of a feature ref
from a ``main`` checkout stay with the in-process tests and the lefthook job
test, because an update runs the fetch and review-marker policies that need a
remote. Reinstating the ``check_branch`` early return that
#6671 removed turns the controls red, and removing the destination guard turns
the refusals red.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
POLICY_SCRIPT = PROJECT_ROOT / "scripts" / "validation" / "git_hook_policy.py"
ZERO_SHA = "0" * 40

EXIT_OK = 0
EXIT_BLOCKED = 1
EXIT_CONFIG = 2


def _hermetic_env(home: Path) -> dict[str, str]:
    """Build an environment that holds no ambient git config or credentials."""
    env = {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "PATHEXT", "COMSPEC", "SYSTEMROOT", "TEMP", "TMP", "TMPDIR"}
    }
    env.update(
        {
            "HOME": str(home),
            "USERPROFILE": str(home),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_EDITOR": "true",
            "LC_ALL": "C",
        }
    )
    return env


def _git(repo: Path, env: dict[str, str], *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def _make_repo(tmp_path: Path, branch: str) -> tuple[Path, dict[str, str], str, str]:
    """Create a repo with two commits on ``branch``; return (repo, env, remote, head)."""
    home = tmp_path / "home dir"
    home.mkdir()
    env = _hermetic_env(home)
    repo = tmp_path / "repo with space"
    repo.mkdir()
    _git(repo, env, "init", "-q", "-b", branch)
    _git(repo, env, "config", "user.name", "Test User")
    _git(repo, env, "config", "user.email", "user@example.com")
    _git(repo, env, "config", "commit.gpgsign", "false")
    shas = []
    for content in ("base\n", "head\n"):
        (repo / "tracked.txt").write_bytes(content.encode("utf-8"))
        _git(repo, env, "add", "--", "tracked.txt")
        _git(repo, env, "commit", "-qm", f"test: write {content.strip()}")
        shas.append(_git(repo, env, "rev-parse", "HEAD"))
    return repo, env, shas[0], shas[1]


def _effects(repo: Path, env: dict[str, str]) -> tuple[str, str, dict[str, bytes]]:
    """Capture refs, tracked status and the name and bytes of each non-git file."""
    refs = _git(repo, env, "for-each-ref", "--format=%(refname) %(objectname)")
    status = _git(repo, env, "status", "--porcelain")
    files = {
        path.relative_to(repo).as_posix(): path.read_bytes()
        for path in repo.rglob("*")
        if ".git" not in path.relative_to(repo).parts and path.is_file()
    }
    return refs, status, files


def _run_pre_push(
    tmp_path: Path,
    repo: Path,
    env: dict[str, str],
    stdin: str,
) -> subprocess.CompletedProcess[str]:
    """Run ``git_hook_policy.py pre-push`` from a foreign working directory.

    The hook only inspects. Assert it left refs, status and files in the repo
    and the foreign working directory exactly as it found them.
    """
    foreign_cwd = tmp_path / "foreign cwd"
    foreign_cwd.mkdir()
    before = _effects(repo, env)
    result = subprocess.run(
        [sys.executable, "-I", str(POLICY_SCRIPT), "--repo-root", str(repo), "pre-push"],
        cwd=foreign_cwd,
        env=env,
        input=stdin,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        timeout=120,
    )
    assert _effects(repo, env) == before
    assert list(foreign_cwd.iterdir()) == []
    return result


def test_main_checkout_may_delete_a_feature_branch_on_the_remote(tmp_path: Path) -> None:
    repo, env, remote, _head = _make_repo(tmp_path, "main")

    result = _run_pre_push(
        tmp_path, repo, env, f"(delete) {ZERO_SHA} refs/heads/feature/old {remote}\n"
    )

    assert _git(repo, env, "symbolic-ref", "--short", "HEAD") == "main"
    assert result.returncode == EXIT_OK, result.stdout + result.stderr
    assert "protected branch" not in result.stderr
    assert "cannot commit or push directly" not in result.stderr


@pytest.mark.parametrize("protected", ["main", "master"])
def test_main_checkout_cannot_delete_a_protected_branch_on_the_remote(
    tmp_path: Path,
    protected: str,
) -> None:
    repo, env, remote, _head = _make_repo(tmp_path, "main")

    result = _run_pre_push(
        tmp_path, repo, env, f"(delete) {ZERO_SHA} refs/heads/{protected} {remote}\n"
    )

    assert result.returncode == EXIT_BLOCKED, result.stdout + result.stderr
    assert f"cannot delete or update protected branch '{protected}'" in result.stderr


def test_feature_checkout_cannot_update_main_on_the_remote(tmp_path: Path) -> None:
    repo, env, remote, head = _make_repo(tmp_path, "feature/work")

    result = _run_pre_push(
        tmp_path, repo, env, f"refs/heads/feature/work {head} refs/heads/main {remote}\n"
    )

    assert result.returncode == EXIT_BLOCKED, result.stdout + result.stderr
    assert "cannot delete or update protected branch 'main'" in result.stderr


@pytest.mark.parametrize("protected_first", [True, False])
def test_one_protected_ref_blocks_a_push_that_also_deletes_a_feature_ref(
    tmp_path: Path,
    protected_first: bool,
) -> None:
    repo, env, remote, _head = _make_repo(tmp_path, "main")
    feature = f"(delete) {ZERO_SHA} refs/heads/feature/old {remote}\n"
    protected = f"(delete) {ZERO_SHA} refs/heads/main {remote}\n"

    result = _run_pre_push(
        tmp_path, repo, env, protected + feature if protected_first else feature + protected
    )

    assert result.returncode == EXIT_BLOCKED, result.stdout + result.stderr
    assert "protected branch 'main'" in result.stderr


def test_malformed_ref_line_exits_with_the_config_error_code(tmp_path: Path) -> None:
    repo, env, _remote, _head = _make_repo(tmp_path, "main")

    result = _run_pre_push(tmp_path, repo, env, "bad input\n")

    assert result.returncode == EXIT_CONFIG, result.stdout + result.stderr
    assert "malformed pre-push input" in result.stderr

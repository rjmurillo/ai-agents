"""Pre-push commit-limit-bypass lookup uses the destination branch (#3110).

Repairing an over-limit PR from an isolated local branch pushes with
``git push origin HEAD:<pr-head>``, so the local and remote branch names differ.
The ``commit-limit-bypass`` label lives on the PR whose head is the REMOTE
branch, not the local one. Before the fix the hook derived the branch passed to
``check_pr_bypass_label.py`` from the local ref, queried a branch with no PR, and
blocked the repair push, forcing ``SKIP_SCOPE_CHECK=1``.

These tests run the real ``.githooks/pre-push`` against a throwaway repo whose
commit count exceeds the limit, with ``check_pr_bypass_label.py`` stubbed to echo
the ``--branch`` value it received (mock at the process boundary). The assertion
is which branch the hook actually queries.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

PRE_PUSH = Path(__file__).resolve().parents[1] / ".githooks" / "pre-push"

_BYPASS_STUB = """#!/usr/bin/env python3
import sys

argv = sys.argv[1:]
branch = ""
for index, arg in enumerate(argv):
    if arg == "--branch" and index + 1 < len(argv):
        branch = argv[index + 1]
print(f"QUERIED_BRANCH={branch}")
raise SystemExit(1)
"""


def _run_git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        check=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip()


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _make_over_limit_repo(tmp_path: Path) -> tuple[Path, str, str, dict[str, str]]:
    """Build a repo whose feature branch is 21 commits past origin/main."""
    repo = tmp_path / "hook-repo"
    repo.mkdir()
    _run_git(repo, "init")
    _run_git(repo, "checkout", "-b", "main")
    _run_git(repo, "config", "user.name", "Pre Push Test")
    _run_git(repo, "config", "user.email", "pre-push-test@example.invalid")

    (repo / ".githooks").mkdir()
    _write_executable(repo / ".githooks" / "pre-push", PRE_PUSH.read_text(encoding="utf-8"))

    # Stub the bypass-label helper to echo the branch the hook queries.
    validation_dir = repo / "scripts" / "validation"
    validation_dir.mkdir(parents=True)
    (validation_dir / "check_pr_bypass_label.py").write_text(_BYPASS_STUB, encoding="utf-8")

    (repo / "README.md").write_text("# fixture\n", encoding="utf-8")
    _run_git(repo, "add", ".")
    _run_git(repo, "commit", "-m", "test: base")
    base_sha = _run_git(repo, "rev-parse", "HEAD")
    _run_git(repo, "update-ref", "refs/remotes/origin/main", base_sha)

    # Isolated local repair branch, 21 commits past base (over the limit of 20).
    # Non-.py files keep ruff/mypy/pytest phases empty so only the commit-count
    # bypass path matters.
    _run_git(repo, "checkout", "-b", "fix/local")
    for index in range(21):
        (repo / f"data_{index}.txt").write_text(f"{index}\n", encoding="utf-8")
        _run_git(repo, "add", f"data_{index}.txt")
        _run_git(repo, "commit", "-m", f"test: change {index}")
    head_sha = _run_git(repo, "rev-parse", "HEAD")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for stub in ("ruff", "mypy"):
        _write_executable(bin_dir / stub, "#!/usr/bin/env bash\nexit 0\n")

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    env["TMPDIR"] = str(scratch)
    return repo, base_sha, head_sha, env


def _run_pre_push(repo: Path, stdin: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(repo / ".githooks" / "pre-push")],
        cwd=repo,
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        timeout=90,
    )


def test_bypass_lookup_uses_remote_branch_when_names_differ(tmp_path: Path) -> None:
    """A HEAD:other repair push queries the destination branch, not the local one."""
    repo, base_sha, head_sha, env = _make_over_limit_repo(tmp_path)

    result = _run_pre_push(
        repo,
        f"refs/heads/fix/local {head_sha} refs/heads/perf/dest {base_sha}\n",
        env,
    )

    output = result.stdout + result.stderr
    assert "QUERIED_BRANCH=perf/dest" in output, output
    assert "QUERIED_BRANCH=fix/local" not in output, output


def test_bypass_lookup_uses_branch_for_same_name_push(tmp_path: Path) -> None:
    """A normal same-name push still queries that branch (no regression)."""
    repo, base_sha, head_sha, env = _make_over_limit_repo(tmp_path)

    result = _run_pre_push(
        repo,
        f"refs/heads/fix/local {head_sha} refs/heads/fix/local {base_sha}\n",
        env,
    )

    output = result.stdout + result.stderr
    assert "QUERIED_BRANCH=fix/local" in output, output

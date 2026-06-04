"""Regression tests for #2376: pre-commit MERGE_HEAD detection in worktrees.

`.githooks/pre-commit` set IS_MERGE by testing a hardcoded
`$REPO_ROOT/.git/MERGE_HEAD` path. In a linked worktree, `.git` is a FILE that
points at the worktree-specific git dir (`<common>/worktrees/<name>`), so the
literal `.git/MERGE_HEAD` path never exists and merge state is missed. With
IS_MERGE=0 the hook skips the branch-specific staged-file filter and counts the
whole staged upstream merge, producing a false scope explosion (the reported
`86/50 files`).

The fix resolves MERGE_HEAD with `git rev-parse --git-path MERGE_HEAD`, which
returns the correct path under the active worktree whether `.git` is a directory
or a file. These tests:

1. Prove the buggy hardcoded path misses MERGE_HEAD in a linked worktree
   (negative control) while the fixed `--git-path` resolution finds it.
2. Pin the fix shape so no future edit reintroduces the hardcoded path.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PRE_COMMIT = REPO_ROOT / ".githooks" / "pre-commit"


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=30,
    )


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return _run(["git", *args], cwd)


def _init_repo(path: Path) -> None:
    """Initialize a git repo with one commit and deterministic identity."""
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test")
    (path / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(path, "add", "seed.txt")
    _git(path, "commit", "-q", "-m", "seed")


# The detection snippet under audit, extracted from .githooks/pre-commit. It
# computes IS_MERGE the way the fixed hook does, then echoes the result so the
# test can assert on it without invoking the whole hook.
_DETECT_FIXED = (
    "MERGE_HEAD_PATH=$(git rev-parse --git-path MERGE_HEAD 2>/dev/null || echo '')\n"
    'if [ -n "$MERGE_HEAD_PATH" ] && [ -f "$MERGE_HEAD_PATH" ]; then\n'
    "  IS_MERGE=1\n"
    "else\n"
    "  IS_MERGE=0\n"
    "fi\n"
    'echo "IS_MERGE=$IS_MERGE"\n'
)

# The buggy snippet the fix replaces. Kept as a negative control to prove the
# old shape misses merge state in a linked worktree.
_DETECT_BUGGY = (
    "REPO_ROOT=$(git rev-parse --show-toplevel)\n"
    'if [ -f "$REPO_ROOT/.git/MERGE_HEAD" ]; then\n'
    "  IS_MERGE=1\n"
    "else\n"
    "  IS_MERGE=0\n"
    "fi\n"
    'echo "IS_MERGE=$IS_MERGE"\n'
)


def _write_merge_head(work_dir: Path) -> None:
    """Write a MERGE_HEAD into the active worktree's git dir via git's own path."""
    head = _git(work_dir, "rev-parse", "HEAD").stdout.strip()
    merge_head_path = _git(
        work_dir, "rev-parse", "--git-path", "MERGE_HEAD"
    ).stdout.strip()
    # --git-path yields a path relative to the worktree cwd; resolve against it.
    abs_path = (work_dir / merge_head_path).resolve()
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(head + "\n", encoding="utf-8")


def _detect(work_dir: Path, snippet: str) -> str:
    result = _run(["bash", "-c", snippet], work_dir)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


class TestMergeHeadDetectionInMainCheckout:
    """In a normal (non-worktree) checkout, both shapes detect merge state."""

    def test_fixed_detects_merge_head(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        _init_repo(repo)
        _write_merge_head(repo)
        assert _detect(repo, _DETECT_FIXED) == "IS_MERGE=1"

    def test_fixed_no_merge_head_is_not_merge(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        _init_repo(repo)
        assert _detect(repo, _DETECT_FIXED) == "IS_MERGE=0"


class TestMergeHeadDetectionInLinkedWorktree:
    """The bug only surfaces in a linked worktree where `.git` is a file."""

    def _make_worktree(self, tmp_path: Path) -> Path:
        repo = tmp_path / "repo"
        _init_repo(repo)
        worktree = tmp_path / "wt"
        # A linked worktree on its own branch; `.git` here is a file pointer.
        _git(repo, "worktree", "add", "-q", "-b", "feature", str(worktree))
        assert (worktree / ".git").is_file(), "expected linked worktree (.git is a file)"
        return worktree

    def test_fixed_detects_merge_head_in_worktree(self, tmp_path: Path) -> None:
        worktree = self._make_worktree(tmp_path)
        _write_merge_head(worktree)
        assert _detect(worktree, _DETECT_FIXED) == "IS_MERGE=1"

    def test_buggy_misses_merge_head_in_worktree(self, tmp_path: Path) -> None:
        """Negative control: the hardcoded `.git/MERGE_HEAD` path is missed."""
        worktree = self._make_worktree(tmp_path)
        _write_merge_head(worktree)
        # The buggy shape looks at "$REPO_ROOT/.git/MERGE_HEAD"; in a worktree
        # `.git` is a file, so that path does not exist and merge is missed.
        assert _detect(worktree, _DETECT_BUGGY) == "IS_MERGE=0"

    def test_fixed_no_merge_head_in_worktree_is_not_merge(self, tmp_path: Path) -> None:
        worktree = self._make_worktree(tmp_path)
        assert _detect(worktree, _DETECT_FIXED) == "IS_MERGE=0"


class TestHookPinsFixedShape:
    """Pin the committed hook so the fix is not regressed."""

    @pytest.fixture(scope="class")
    def hook_text(self) -> str:
        return PRE_COMMIT.read_text(encoding="utf-8")

    def test_hook_uses_git_path_merge_head(self, hook_text: str) -> None:
        assert "git rev-parse --git-path MERGE_HEAD" in hook_text

    def test_hook_does_not_hardcode_git_merge_head(self, hook_text: str) -> None:
        # The hook must not test or read the literal `.git/MERGE_HEAD` path. A
        # prose mention in a comment is fine; an `[ -f ... ]` test or a `cat` of
        # the hardcoded path is the bug. Assert no non-comment line references it.
        code_lines = [
            line
            for line in hook_text.splitlines()
            if not line.lstrip().startswith("#")
        ]
        offenders = [
            line for line in code_lines if "$REPO_ROOT/.git/MERGE_HEAD" in line
        ]
        assert offenders == [], offenders

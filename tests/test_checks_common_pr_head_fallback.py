"""Base-ref resolution when the local branch name differs from the PR head.

Issue #4382: an isolated worktree checked out as ``pr-4294`` tracking
``origin/fix/gc-report-time-budget`` made ``gh pr view`` resolve no PR, so
``_gh_base_ref`` returned None and the caller fell back to the stale head
upstream instead of the PR base.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.validation.checks_common import (
    _gh_base_ref,
    _run_subprocess,
    _upstream_head_ref_name,
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    ).stdout.strip()


def _worktree_tracking_other_head(tmp_path: Path) -> Path:
    """Build a local branch ``pr-4294`` tracking ``origin/fix/gc-report-time-budget``."""
    remote = tmp_path / "remote"
    remote.mkdir()
    _git(remote, "init", "--bare", "--initial-branch=main")

    seed = tmp_path / "seed"
    _git(tmp_path, "clone", str(remote), str(seed))
    _git(seed, "config", "user.email", "test@example.com")
    _git(seed, "config", "user.name", "Test User")
    (seed / "README.md").write_text("seed\n", encoding="utf-8")
    _git(seed, "add", "README.md")
    _git(seed, "commit", "-m", "chore: seed")
    _git(seed, "push", "origin", "main")
    _git(seed, "checkout", "-b", "fix/gc-report-time-budget")
    (seed / "work.txt").write_text("work\n", encoding="utf-8")
    _git(seed, "add", "work.txt")
    _git(seed, "commit", "-m", "feat: work")
    _git(seed, "push", "-u", "origin", "fix/gc-report-time-budget")

    local = tmp_path / "pr-4294"
    _git(tmp_path, "clone", str(remote), str(local))
    _git(local, "checkout", "-b", "pr-4294", "origin/fix/gc-report-time-budget")
    return local


_GH_VIEW_PREFIX = ("gh", "pr", "view")
_GH_KNOWN_FLAGS = {"-c", "--comments", "-q", "--jq", "--json", "-t", "--template", "-w", "--web"}


class _FakeGh:
    """Stand-in for ``gh pr view`` that rejects flags real gh does not accept.

    ``gh pr view --help`` (gh 2.97.0) documents
    ``gh pr view [<number> | <url> | <branch>] [flags]`` with exactly five
    flags: ``-c/--comments``, ``-q/--jq``, ``--json``, ``-t/--template``,
    ``-w/--web``. Anything else exits 1 with ``unknown flag``. A fake that
    answers success for an invented flag turns this suite into a closed loop
    and lets an inert retry ship green, which is what happened on the first
    attempt at issue #4382. ``test_real_gh_pr_view_has_no_head_flag`` below
    grounds this table against the installed binary.
    """

    def __init__(self, bare: str, by_branch: str) -> None:
        self.bare = bare
        self.by_branch = by_branch
        self.calls: list[list[str]] = []

    def __call__(self, args, timeout=300, cwd=None, env=None):  # noqa: ANN001, ANN204
        if tuple(args[:3]) != _GH_VIEW_PREFIX:
            return _run_subprocess(args, timeout=timeout, cwd=cwd, env=env)
        self.calls.append(list(args))
        selector = self._selector(args)
        if selector is None:
            return (1, "", "unknown flag: --head")
        answer = self.by_branch if selector else self.bare
        return (0, answer, "") if answer else (1, "", "no pull requests found")

    def _selector(self, args) -> str | None:  # noqa: ANN001
        """Return the positional selector, or None when gh would reject the argv."""
        rest = list(args[3:])
        selector = ""
        while rest:
            token = rest.pop(0)
            if not token.startswith("-"):
                selector = token
                continue
            if token not in _GH_KNOWN_FLAGS:
                return None
            if token not in {"-c", "--comments", "-w", "--web"} and rest:
                rest.pop(0)
        return selector


@pytest.mark.skipif(shutil.which("gh") is None, reason="gh CLI not installed")
def test_real_gh_pr_view_has_no_head_flag() -> None:
    """Ground the fake against the installed gh binary, not against our own model."""
    help_text = subprocess.run(
        ["gh", "pr", "view", "--help"],
        check=True,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    ).stdout

    assert "--head" not in help_text
    assert "gh pr view [<number> | <url> | <branch>] [flags]" in help_text


def test_upstream_head_ref_name_reads_the_tracked_head(tmp_path: Path) -> None:
    local = _worktree_tracking_other_head(tmp_path)

    assert _upstream_head_ref_name(local) == "fix/gc-report-time-budget"


def test_upstream_head_ref_name_returns_none_without_an_upstream(tmp_path: Path) -> None:
    repo = tmp_path / "solo"
    repo.mkdir()
    _git(repo, "init", "--initial-branch=main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-m", "chore: seed")

    assert _upstream_head_ref_name(repo) is None


def test_upstream_head_ref_name_returns_none_on_detached_head(tmp_path: Path) -> None:
    local = _worktree_tracking_other_head(tmp_path)
    _git(local, "checkout", "--detach", "HEAD")

    assert _upstream_head_ref_name(local) is None


def test_gh_base_ref_uses_the_bare_lookup_when_it_resolves(tmp_path: Path) -> None:
    local = _worktree_tracking_other_head(tmp_path)
    fake = _FakeGh(bare="main", by_branch="never-used")

    with patch("scripts.validation.checks_common.shutil.which", return_value="/usr/bin/gh"):
        with patch("scripts.validation.checks_common._run_subprocess", side_effect=fake):
            assert _gh_base_ref(local) == "origin/main"

    assert len(fake.calls) == 1
    assert fake.calls[0] == [
        "gh",
        "pr",
        "view",
        "--json",
        "baseRefName",
        "-q",
        ".baseRefName",
    ]


def test_gh_base_ref_retries_with_the_upstream_head(tmp_path: Path) -> None:
    local = _worktree_tracking_other_head(tmp_path)
    fake = _FakeGh(bare="", by_branch="main")

    with patch("scripts.validation.checks_common.shutil.which", return_value="/usr/bin/gh"):
        with patch("scripts.validation.checks_common._run_subprocess", side_effect=fake):
            base = _gh_base_ref(local)

    assert base == "origin/main"
    assert len(fake.calls) == 2
    assert fake.calls[1] == [
        "gh",
        "pr",
        "view",
        "fix/gc-report-time-budget",
        "--json",
        "baseRefName",
        "-q",
        ".baseRefName",
    ]


def test_gh_base_ref_reports_why_the_head_fallback_won(tmp_path: Path, capsys) -> None:
    local = _worktree_tracking_other_head(tmp_path)
    fake = _FakeGh(bare="", by_branch="main")

    with patch("scripts.validation.checks_common.shutil.which", return_value="/usr/bin/gh"):
        with patch("scripts.validation.checks_common._run_subprocess", side_effect=fake):
            _gh_base_ref(local)

    stderr = capsys.readouterr().err
    assert "origin/main" in stderr
    assert "fix/gc-report-time-budget" in stderr


def test_gh_base_ref_returns_none_when_neither_lookup_finds_a_pr(tmp_path: Path) -> None:
    local = _worktree_tracking_other_head(tmp_path)
    fake = _FakeGh(bare="", by_branch="")

    with patch("scripts.validation.checks_common.shutil.which", return_value="/usr/bin/gh"):
        with patch("scripts.validation.checks_common._run_subprocess", side_effect=fake):
            assert _gh_base_ref(local) is None

    assert len(fake.calls) == 2


def test_gh_base_ref_skips_the_retry_when_no_upstream_is_configured(tmp_path: Path) -> None:
    repo = tmp_path / "solo"
    repo.mkdir()
    _git(repo, "init", "--initial-branch=main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-m", "chore: seed")
    fake = _FakeGh(bare="", by_branch="main")

    with patch("scripts.validation.checks_common.shutil.which", return_value="/usr/bin/gh"):
        with patch("scripts.validation.checks_common._run_subprocess", side_effect=fake):
            assert _gh_base_ref(repo) is None

    assert len(fake.calls) == 1

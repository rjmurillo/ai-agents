"""The pr-autofix dispatch block and scan against a real rewritten remote (#7032).

A force-pushed PR leaves its worktree diverged and without the live head. The
dispatch block must still select that worktree, and the scan must fetch the live
head by SHA and list the commits. These tests run the shipped block, then the
scan, as the unattended loop does.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from test_pr_worktree_select import BASH, BRANCH, _dispatch, _git, make_repos

from scripts.github_core import orphaned_commits as oc

pytestmark = pytest.mark.skipif(BASH is None, reason="bash is required")


@pytest.fixture
def repos(tmp_path: Path) -> dict[str, object]:
    return make_repos(tmp_path)


def _has_commit(worktree: Path, sha: str) -> bool:
    probe = subprocess.run(
        ["git", "-C", str(worktree), "cat-file", "-e", f"{sha}^{{commit}}"],
        capture_output=True,
        check=False,
    )
    return probe.returncode == 0


def _publish(repos: dict[str, object], tmp_path: Path) -> Path:
    """Point origin at a bare repo holding the branch, and return a second clone of it.

    The bare path ends in ``owner/repo.git``, so the selector's origin check matches it.
    """
    wt = Path(str(repos["wt"]))
    bare = tmp_path / "remote" / "owner" / "repo.git"
    bare.parent.mkdir(parents=True)
    _git(tmp_path, "init", "-q", "--bare", str(bare))
    _git(wt, "remote", "set-url", "origin", str(bare))
    _git(wt, "push", "-q", "origin", f"{BRANCH}:{BRANCH}")
    _git(wt, "fetch", "-q", "origin")
    other = tmp_path / "other"
    _git(tmp_path, "clone", "-q", "-b", BRANCH, str(bare), str(other))
    return other


def _commit_file(checkout: Path, name: str, subject: str) -> str:
    (checkout / name).write_text(subject, encoding="utf-8")
    _git(checkout, "add", ".")
    _git(checkout, "commit", "-q", "-m", subject)
    return _git(checkout, "rev-parse", "HEAD")


def _force_pushed(repos: dict[str, object], tmp_path: Path) -> str:
    """Amend a pushed commit from another clone and force-push it over the branch."""
    wt = Path(str(repos["wt"]))
    _commit_file(wt, "pushed.txt", "pushed")
    other = _publish(repos, tmp_path)
    _commit_file(wt, "local.txt", "local only")
    _git(other, "commit", "-q", "--amend", "-m", "rewritten")
    _git(other, "push", "-q", "--force", "origin", f"{BRANCH}:{BRANCH}")
    return _git(other, "rev-parse", "HEAD")


def _advanced(repos: dict[str, object], tmp_path: Path) -> str:
    """Add a commit on the remote from another clone; the worktree is only behind."""
    other = _publish(repos, tmp_path)
    live = _commit_file(other, "newer.txt", "newer")
    _git(other, "push", "-q", "origin", f"{BRANCH}:{BRANCH}")
    return live


def _scan(live: str, selected: str, *, escalated: bool = True) -> dict[str, object]:
    return oc.scan_if_escalated(escalated, live, oc.worktree_runner(selected), pr_checkout=True)


class TestSelection:
    def test_origin_matched_head_that_lacks_the_live_sha_is_selected(
        self, repos: dict[str, object]
    ) -> None:
        assert _dispatch(repos, EXPECTED_HEAD_SHA="1" * 40) == str(repos["wt"])

    def test_the_selector_itself_never_fetches(
        self, repos: dict[str, object], tmp_path: Path
    ) -> None:
        forced = _force_pushed(repos, tmp_path)
        wt = Path(str(repos["wt"]))
        assert _dispatch(repos, EXPECTED_HEAD_SHA=forced) == str(wt)
        assert not _has_commit(wt, forced)


class TestForcePushedHeadFromTheLoop:
    """The dispatch block plus the scan, as the unattended loop runs them (#7032)."""

    def test_diverged_worktree_reports_commits_and_force_push(
        self, repos: dict[str, object], tmp_path: Path
    ) -> None:
        forced = _force_pushed(repos, tmp_path)
        wt = Path(str(repos["wt"]))
        assert not _has_commit(wt, forced)

        selected = _dispatch(repos, EXPECTED_HEAD_SHA=forced)
        report = _scan(forced, selected)

        assert selected == str(wt)
        assert report["status"] == "unverified"
        assert report["force_push_suspected"] is True
        commits = report["commits"]
        assert isinstance(commits, list)
        assert [c["subject"] for c in commits] == ["pushed", "local only"]

    def test_fetch_leaves_the_remote_tracking_ref_alone(
        self, repos: dict[str, object], tmp_path: Path
    ) -> None:
        # A bare --force-with-lease reads this ref, so the scan must not advance it.
        forced = _force_pushed(repos, tmp_path)
        wt = Path(str(repos["wt"]))
        ref = f"refs/remotes/origin/{BRANCH}"
        before = _git(wt, "rev-parse", ref)

        _scan(forced, _dispatch(repos, EXPECTED_HEAD_SHA=forced))

        assert _has_commit(wt, forced)
        assert _git(wt, "rev-parse", ref) == before

    def test_fetch_runs_no_repository_hook(self, repos: dict[str, object], tmp_path: Path) -> None:
        forced = _force_pushed(repos, tmp_path)
        wt = Path(str(repos["wt"]))
        marker = tmp_path / "hook-ran"
        hooks = tmp_path / "hooks"
        hooks.mkdir()
        hook = hooks / "reference-transaction"
        hook.write_text(f"#!/bin/sh\ntouch '{marker}'\n", encoding="utf-8")
        hook.chmod(0o755)
        _git(wt, "config", "core.hooksPath", str(hooks))

        _scan(forced, str(wt))

        assert _has_commit(wt, forced)
        assert not marker.exists()

    def test_a_record_that_is_not_escalated_fetches_nothing(
        self, repos: dict[str, object], tmp_path: Path
    ) -> None:
        forced = _force_pushed(repos, tmp_path)
        wt = Path(str(repos["wt"]))

        report = _scan(forced, str(wt), escalated=False)

        assert report["status"] == "not_checked"
        assert not _has_commit(wt, forced)

    def test_worktree_behind_the_live_head_is_not_called_a_force_push(
        self, repos: dict[str, object], tmp_path: Path
    ) -> None:
        live = _advanced(repos, tmp_path)
        selected = _dispatch(repos, EXPECTED_HEAD_SHA=live)
        report = _scan(live, selected)

        assert selected == str(repos["wt"])
        assert report["status"] == "unverified"
        assert "behind the live head" in str(report["reason"])
        assert "force_push_suspected" not in report

    def test_failed_fetch_names_the_fetch_and_lists_no_commits(
        self, repos: dict[str, object], tmp_path: Path
    ) -> None:
        _publish(repos, tmp_path)
        missing = "1" * 40
        report = _scan(missing, _dispatch(repos, EXPECTED_HEAD_SHA=missing))

        assert report["status"] == "unverified"
        assert "could not fetch the live head" in str(report["reason"])
        assert report["commits"] == []

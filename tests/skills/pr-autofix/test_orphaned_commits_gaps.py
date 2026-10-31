"""Detection-gap tests for orphaned_commits.py (issue #6506).

Covers an unreadable ``git show`` (unverified, not clean), a removed test that an
added one offsets, and a live head that ``HEAD`` lacks (force-pushed or diverged:
commits listed, ``force_push_suspected`` set, status still ``unverified``). The
base behavior has its tests in test_orphaned_commits.py.
"""

from __future__ import annotations

import subprocess

from test_orphaned_commits import LIVE, FakeGit, _record

from scripts.github_core import orphaned_commits as oc


def _commit(*files: tuple[str, str]) -> oc.Commit:
    return oc.Commit(sha="b" * 40, subject="s", files=files)


class TestDetectionGaps:
    def test_added_definitions_alone_are_not_flagged(self):
        git = FakeGit(show=(0, "+def test_new():\n+def test_other():\n"))
        result = oc.classify(_commit(("M", "tests/test_wiring.py")), git)
        assert result.risks == ()

    def test_failed_show_makes_the_report_unverified_with_a_reason(self):
        log = _record("b" * 40, "edit tests", ("M", "tests/test_wiring.py"))
        report = oc.scan_unpushed_commits(LIVE, FakeGit(log=(0, log), show=(128, "")))
        assert report["status"] == "unverified"
        assert "git show failed for 1 commit(s): bbbbbbbbb" in str(report["reason"])
        assert [c["sha"] for c in report["commits"]] == ["b" * 40]
        assert report["commits"][0]["risks"] == [oc.RISK_DIFF_UNREADABLE]
        assert "bbbbbbbbb edit tests" in str(report["warning"])

    def test_readable_show_keeps_the_ahead_status(self):
        log = _record("b" * 40, "edit tests", ("M", "tests/test_wiring.py"))
        report = oc.scan_unpushed_commits(LIVE, FakeGit(log=(0, log), show=(0, "+def test_a():\n")))
        assert report["status"] == "ahead"

    def test_diverged_branch_lists_commits_and_flags_force_push(self):
        log = _record("b" * 40, "local work", ("M", "src/a.py")) + _record(
            "c" * 40, "weaken gate", ("M", "lefthook.yml")
        )
        git = FakeGit(ancestor=1, log=(0, log))
        report = oc.scan_unpushed_commits(LIVE, git)
        assert report["status"] == "unverified"
        assert report["force_push_suspected"] is True
        assert [c["sha"] for c in report["commits"]] == ["b" * 40, "c" * 40]
        assert report["commits"][1]["risks"] == [oc.RISK_WIRING]
        assert "force-pushed" in str(report["warning"])
        assert "cccccccc" in str(report["warning"])
        log_args = next(c for c in git.calls if c[0] == "log")
        assert log_args[-1] == "d" * 40 + "..HEAD"
        assert ["merge-base", LIVE, "HEAD"] in git.calls

    def test_diverged_without_common_ancestor_lists_head_history(self):
        log = _record("b" * 40, "root", ("A", "README.md"))
        git = FakeGit(ancestor=1, log=(0, log), base=(1, ""))
        report = oc.scan_unpushed_commits(LIVE, git)
        assert report["status"] == "unverified"
        assert report["force_push_suspected"] is True
        assert "no common ancestor" in str(report["reason"])
        assert next(c for c in git.calls if c[0] == "log")[-1] == "HEAD"

    def test_diverged_merge_base_failure_stays_unverified_and_flagged(self):
        report = oc.scan_unpushed_commits(LIVE, FakeGit(ancestor=1, base=(128, "")))
        assert report["status"] == "unverified"
        assert report["force_push_suspected"] is True
        assert "merge-base exited 128" in str(report["reason"])
        assert report["commits"] == []

    def test_diverged_log_failure_stays_unverified_and_flagged(self):
        report = oc.scan_unpushed_commits(LIVE, FakeGit(ancestor=1, log=(128, "")))
        assert report["status"] == "unverified"
        assert report["force_push_suspected"] is True
        assert "git log exited 128" in str(report["reason"])

    def test_diverged_merge_base_garbage_output_is_not_used_as_a_range(self):
        git = FakeGit(ancestor=1, base=(0, "--output=/tmp/x\n"))
        report = oc.scan_unpushed_commits(LIVE, git)
        assert report["status"] == "unverified"
        assert not any(c[0] == "log" for c in git.calls)

    def test_diverged_without_a_named_worktree_lists_nothing_and_raises_no_alarm(self):
        log = _record("b" * 40, "someone else's work", ("M", "src/a.py"))
        git = FakeGit(ancestor=1, log=(0, log))
        report = oc.scan_unpushed_commits(LIVE, git, pr_checkout=False)
        assert report["status"] == "unverified"
        assert "force_push_suspected" not in report
        assert not report.get("commits")
        assert not any(c[0] == "log" for c in git.calls)

    def test_scan_if_escalated_forwards_pr_checkout(self):
        git = FakeGit(ancestor=1, log=(0, _record("b" * 40, "x", ("M", "a.py"))))
        report = oc.scan_if_escalated(True, LIVE, git, pr_checkout=False)
        assert "force_push_suspected" not in report

    def test_head_behind_the_live_head_is_not_a_force_push(self):
        report = oc.scan_unpushed_commits(LIVE, FakeGit(ancestor=1, log=(0, "")))
        assert report["status"] == "unverified"
        assert "force_push_suspected" not in report
        assert "behind the live head" in str(report["reason"])

    def test_ancestor_scan_has_no_force_push_flag(self):
        report = oc.scan_unpushed_commits(LIVE, FakeGit(log=(0, "")))
        assert "force_push_suspected" not in report

    def test_real_git_force_pushed_head_lists_divergent_commits(self, tmp_path, monkeypatch):
        def git(*args):
            return subprocess.run(
                ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                cwd=tmp_path,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

        git("init", "-q", "-b", "main")
        (tmp_path / "a.txt").write_text("a")
        git("add", ".")
        git("commit", "-q", "-m", "base")
        (tmp_path / "b.txt").write_text("remote-only")
        git("add", ".")
        git("commit", "-q", "-m", "old remote tip")
        live = git("rev-parse", "HEAD")
        git("reset", "-q", "--hard", "HEAD~1")
        (tmp_path / "lefthook.yml").write_text("pre-push: {}")
        git("add", ".")
        git("commit", "-q", "-m", "rewritten tip")
        monkeypatch.chdir(tmp_path)
        report = oc.scan_unpushed_commits(live)
        assert report["status"] == "unverified"
        assert report["force_push_suspected"] is True
        (commit,) = report["commits"]
        assert commit["subject"] == "rewritten tip"
        assert commit["risks"] == [oc.RISK_WIRING]

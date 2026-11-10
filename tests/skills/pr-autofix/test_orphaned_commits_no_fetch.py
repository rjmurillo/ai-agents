"""fetch_missing_head=False: the worktree comparison runs and no fetch does."""

from __future__ import annotations

from scripts.github_core import orphaned_commits as oc

LIVE = "a" * 40


class FakeGit:
    """Scripted git runner keyed on the subcommand."""

    def __init__(self, ancestor=0, base=(0, "d" * 40)):
        self.ancestor, self.base = ancestor, base
        self.calls: list[list[str]] = []

    def __call__(self, args):
        self.calls.append(args)
        if args[0] == "merge-base":
            return (self.ancestor, "") if "--is-ancestor" in args else self.base
        if args[0] == "log":
            return (0, "")
        return (0, "")


class TestScanWithoutFetch:
    """fetch_missing_head=False keeps the worktree comparison and runs no fetch."""

    @staticmethod
    def _fetches(git):
        return [call for call in git.calls if call[0] == "fetch" or "fetch" in call]

    def test_diverged_head_still_lists_orphaned_commits(self):
        git = FakeGit(ancestor=1)
        report = oc.scan_unpushed_commits(LIVE, git, pr_checkout=True, fetch_missing_head=False)
        assert "no PR worktree was named" not in str(report.get("reason", ""))
        assert self._fetches(git) == []

    def test_absent_head_is_unverified_not_fetched(self):
        git = FakeGit(ancestor=128)
        report = oc.scan_unpushed_commits(LIVE, git, pr_checkout=True, fetch_missing_head=False)
        assert report["status"] == "unverified"
        assert self._fetches(git) == []
        assert not any(call[0] == "cat-file" for call in git.calls)

    def test_default_still_probes_for_the_head_before_comparing(self):
        git = FakeGit()
        oc.scan_unpushed_commits(LIVE, git, pr_checkout=True)
        assert any(call[0] == "cat-file" for call in git.calls)

    def test_scan_if_escalated_forwards_the_flag(self):
        git = FakeGit(ancestor=128)
        oc.scan_if_escalated(True, LIVE, git, pr_checkout=True, fetch_missing_head=False)
        assert not any(call[0] == "cat-file" for call in git.calls)

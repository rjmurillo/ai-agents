"""Format-report tests for worktree GC disposition output."""

from __future__ import annotations

from scripts.maintenance.gc_worktrees import (
    KEEP_UNPUSHED,
    Decision,
    GcReport,
    format_report,
)

_MAIN = "/repo"
_BASE = "origin/main"


def test_unpushed_kept_branch_gets_disposition_section() -> None:
    report = GcReport(
        timestamp="t",
        base_ref=_BASE,
        apply=False,
        main_worktree=_MAIN,
        total_worktrees=1,
        decisions=[
            Decision("/repo/wt", "fix/4193-stale", remove=False, reason=KEEP_UNPUSHED),
        ],
    )
    text = format_report(report)
    assert "Needs disposition:" in text
    assert "Review branch and issue state" in text
    assert "/repo/wt [fix/4193-stale] unpushed and unmerged" in text

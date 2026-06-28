"""Tests for gc_worktrees module.

Verifies the worktree garbage-collection safety contract: dry-run removes
nothing, only clean+merged-or-pushed worktrees are candidates, and locked,
dirty, or unpushed worktrees are kept. Mocks at the subprocess boundary.
Related: Issue #2761 (worktree accumulation starves the markdown LSP).
"""

from __future__ import annotations

import subprocess
from unittest.mock import patch

from scripts.maintenance.gc_worktrees import (
    KEEP_DETACHED,
    KEEP_DIRTY,
    KEEP_GIT_ERROR,
    KEEP_LOCKED,
    KEEP_MAIN,
    KEEP_UNPUSHED,
    Decision,
    GcReport,
    Worktree,
    _run_git,
    apply_removals,
    build_report,
    decide,
    format_report,
    is_merged_to_base,
    list_worktrees,
    main,
    parse_args,
)

_MAIN = "/repo"
_BASE = "origin/main"

_PORCELAIN = """\
worktree /repo
HEAD aaaa
branch refs/heads/main

worktree /repo/wt-clean
HEAD bbbb
branch refs/heads/feat/done

worktree /repo/wt-locked
HEAD cccc
branch refs/heads/feat/locked
locked

worktree /repo/wt-bare
HEAD dddd
bare

worktree /repo/wt-detached
HEAD eeee
detached
"""


class TestListWorktrees:
    """Parsing of git worktree list --porcelain."""

    def test_parses_each_worktree_block(self):
        with patch("scripts.maintenance.gc_worktrees._run_git", return_value=_PORCELAIN.strip()):
            result = list_worktrees()
        assert [w.path for w in result] == [
            "/repo",
            "/repo/wt-clean",
            "/repo/wt-locked",
            "/repo/wt-bare",
            "/repo/wt-detached",
        ]

    def test_strips_refs_heads_prefix_from_branch(self):
        with patch("scripts.maintenance.gc_worktrees._run_git", return_value=_PORCELAIN.strip()):
            result = list_worktrees()
        assert result[1].branch == "feat/done"

    def test_flags_locked_bare_and_detached(self):
        with patch("scripts.maintenance.gc_worktrees._run_git", return_value=_PORCELAIN.strip()):
            result = list_worktrees()
        by_path = {w.path: w for w in result}
        assert by_path["/repo/wt-locked"].locked is True
        assert by_path["/repo/wt-bare"].bare is True
        assert by_path["/repo/wt-detached"].detached is True

    def test_empty_output_yields_no_worktrees(self):
        with patch("scripts.maintenance.gc_worktrees._run_git", return_value=""):
            assert list_worktrees() == []


class TestGitSubprocesses:
    """Git subprocess wrapper behavior."""

    def test_run_git_uses_utf8_timeout_and_replacement_errors(self):
        completed = subprocess.CompletedProcess(
            ["git", "status"], 0, stdout="ok\n", stderr=""
        )
        with patch(
            "scripts.maintenance.gc_worktrees.subprocess.run",
            return_value=completed,
        ) as run:
            assert _run_git(["status"], cwd="/repo") == "ok"

        kwargs = run.call_args.kwargs
        assert kwargs["encoding"] == "utf-8"
        assert kwargs["errors"] == "replace"
        assert kwargs["timeout"] > 0
        assert kwargs["cwd"] == "/repo"

    def test_run_git_wraps_timeout_as_runtime_error(self):
        with patch(
            "scripts.maintenance.gc_worktrees.subprocess.run",
            side_effect=subprocess.TimeoutExpired(["git", "status"], 30),
        ):
            try:
                _run_git(["status"], cwd="/repo")
            except RuntimeError as exc:
                assert "git status in /repo failed" in str(exc)
            else:  # pragma: no cover - assertion branch
                raise AssertionError("expected RuntimeError")

    def test_is_merged_to_base_uses_utf8_timeout_and_replacement_errors(self):
        completed = subprocess.CompletedProcess(
            ["git", "merge-base"], 0, stdout="", stderr=""
        )
        with patch(
            "scripts.maintenance.gc_worktrees.subprocess.run",
            return_value=completed,
        ) as run:
            assert is_merged_to_base("/repo/wt", _BASE) is True

        kwargs = run.call_args.kwargs
        assert kwargs["encoding"] == "utf-8"
        assert kwargs["errors"] == "replace"
        assert kwargs["timeout"] > 0
        assert kwargs["cwd"] == "/repo/wt"


class TestDecide:
    """The per-worktree safety decision. KEEP on any doubt."""

    def test_keeps_main_worktree(self):
        wt = Worktree(path=_MAIN, branch="main")
        decision = decide(wt, _MAIN, _BASE)
        assert decision.remove is False
        assert decision.reason == KEEP_MAIN

    def test_keeps_locked_worktree(self):
        wt = Worktree(path="/repo/wt", branch="feat/x", locked=True)
        decision = decide(wt, _MAIN, _BASE)
        assert decision.remove is False
        assert decision.reason == KEEP_LOCKED

    def test_keeps_detached_worktree(self):
        wt = Worktree(path="/repo/wt", branch=None, detached=True)
        decision = decide(wt, _MAIN, _BASE)
        assert decision.remove is False
        assert decision.reason == KEEP_DETACHED

    def test_keeps_dirty_worktree(self):
        wt = Worktree(path="/repo/wt", branch="feat/x")
        with patch(
            "scripts.maintenance.gc_worktrees.has_uncommitted_changes",
            return_value=True,
        ):
            decision = decide(wt, _MAIN, _BASE)
        assert decision.remove is False
        assert decision.reason == KEEP_DIRTY

    def test_keeps_unpushed_and_unmerged_worktree(self):
        wt = Worktree(path="/repo/wt", branch="feat/x")
        with (
            patch(
                "scripts.maintenance.gc_worktrees.has_uncommitted_changes",
                return_value=False,
            ),
            patch(
                "scripts.maintenance.gc_worktrees.is_merged_to_base",
                return_value=False,
            ),
            patch(
                "scripts.maintenance.gc_worktrees.has_unpushed_commits",
                return_value=True,
            ),
        ):
            decision = decide(wt, _MAIN, _BASE)
        assert decision.remove is False
        assert decision.reason == KEEP_UNPUSHED

    def test_removes_clean_merged_worktree(self):
        wt = Worktree(path="/repo/wt", branch="feat/x")
        with (
            patch(
                "scripts.maintenance.gc_worktrees.has_uncommitted_changes",
                return_value=False,
            ),
            patch(
                "scripts.maintenance.gc_worktrees.is_merged_to_base",
                return_value=True,
            ),
        ):
            decision = decide(wt, _MAIN, _BASE)
        assert decision.remove is True
        assert decision.reason == "merged to base"

    def test_removes_clean_fully_pushed_worktree(self):
        wt = Worktree(path="/repo/wt", branch="feat/x")
        with (
            patch(
                "scripts.maintenance.gc_worktrees.has_uncommitted_changes",
                return_value=False,
            ),
            patch(
                "scripts.maintenance.gc_worktrees.is_merged_to_base",
                return_value=False,
            ),
            patch(
                "scripts.maintenance.gc_worktrees.has_unpushed_commits",
                return_value=False,
            ),
        ):
            decision = decide(wt, _MAIN, _BASE)
        assert decision.remove is True
        assert decision.reason == "fully pushed"

    def test_keeps_worktree_when_git_inspection_fails(self):
        wt = Worktree(path="/repo/wt", branch="feat/x")
        with patch(
            "scripts.maintenance.gc_worktrees.has_uncommitted_changes",
            side_effect=RuntimeError("git boom"),
        ):
            decision = decide(wt, _MAIN, _BASE)
        assert decision.remove is False
        assert decision.reason == KEEP_GIT_ERROR


class TestBuildReport:
    """End-to-end plan construction with mocked git state."""

    def test_dry_run_marks_apply_false_and_keeps_main(self):
        with (
            patch(
                "scripts.maintenance.gc_worktrees.list_worktrees",
                return_value=[
                    Worktree(path=_MAIN, branch="main"),
                    Worktree(path="/repo/wt", branch="feat/x"),
                ],
            ),
            patch("scripts.maintenance.gc_worktrees._run_git", return_value=_MAIN),
            patch(
                "scripts.maintenance.gc_worktrees.has_uncommitted_changes",
                return_value=False,
            ),
            patch(
                "scripts.maintenance.gc_worktrees.is_merged_to_base",
                return_value=True,
            ),
        ):
            report = build_report(base_ref=_BASE, apply=False)
        assert report.apply is False
        assert report.main_worktree == _MAIN
        assert report.total_worktrees == 2
        candidate_paths = [d.path for d in report.candidates]
        assert candidate_paths == ["/repo/wt"]

    def test_main_worktree_is_always_kept(self):
        with patch(
            "scripts.maintenance.gc_worktrees.list_worktrees",
            return_value=[Worktree(path=_MAIN, branch="main")],
        ), patch("scripts.maintenance.gc_worktrees._run_git", return_value=_MAIN):
            report = build_report(base_ref=_BASE, apply=False)
        assert report.candidates == []
        assert len(report.kept) == 1

    def test_current_linked_worktree_is_always_kept(self):
        with (
            patch(
                "scripts.maintenance.gc_worktrees.list_worktrees",
                return_value=[
                    Worktree(path=_MAIN, branch="main"),
                    Worktree(path="/repo/active", branch="feat/active"),
                    Worktree(path="/repo/wt", branch="feat/done"),
                ],
            ),
            patch(
                "scripts.maintenance.gc_worktrees._run_git",
                return_value="/repo/active",
            ),
            patch(
                "scripts.maintenance.gc_worktrees.has_uncommitted_changes",
                return_value=False,
            ),
            patch(
                "scripts.maintenance.gc_worktrees.is_merged_to_base",
                return_value=True,
            ),
        ):
            report = build_report(base_ref=_BASE, apply=False)

        candidate_paths = [d.path for d in report.candidates]
        kept = {d.path: d.reason for d in report.kept}
        assert candidate_paths == ["/repo/wt"]
        assert kept["/repo/active"] == KEEP_MAIN


class TestApplyRemovals:
    """Removal execution. Only runs on candidates; never in dry-run."""

    def test_apply_removes_each_candidate_and_prunes(self):
        report = GcReport(
            timestamp="t",
            base_ref=_BASE,
            apply=True,
            main_worktree=_MAIN,
            decisions=[
                Decision("/repo/a", "feat/a", remove=True, reason="merged to base"),
                Decision("/repo/b", "feat/b", remove=True, reason="fully pushed"),
                Decision("/repo/c", "feat/c", remove=False, reason=KEEP_LOCKED),
            ],
        )
        with (
            patch("scripts.maintenance.gc_worktrees.remove_worktree") as remove,
            patch("scripts.maintenance.gc_worktrees.prune_worktrees") as prune,
        ):
            apply_removals(report)
        assert [c.args[0] for c in remove.call_args_list] == ["/repo/a", "/repo/b"]
        prune.assert_called_once()
        assert report.removed == ["/repo/a", "/repo/b"]

    def test_apply_records_removal_errors_without_aborting(self):
        report = GcReport(
            timestamp="t",
            base_ref=_BASE,
            apply=True,
            main_worktree=_MAIN,
            decisions=[
                Decision("/repo/a", "feat/a", remove=True, reason="merged to base"),
                Decision("/repo/b", "feat/b", remove=True, reason="fully pushed"),
            ],
        )

        def fail_on_a(path: str) -> None:
            if path == "/repo/a":
                raise RuntimeError("locked by index")

        with (
            patch(
                "scripts.maintenance.gc_worktrees.remove_worktree",
                side_effect=fail_on_a,
            ),
            patch("scripts.maintenance.gc_worktrees.prune_worktrees"),
        ):
            apply_removals(report)
        assert report.removed == ["/repo/b"]
        assert len(report.remove_errors) == 1
        assert "/repo/a" in report.remove_errors[0]


class TestFormatReport:
    """Human-readable summary content."""

    def test_dry_run_summary_states_nothing_removed(self):
        report = GcReport(
            timestamp="t",
            base_ref=_BASE,
            apply=False,
            main_worktree=_MAIN,
            total_worktrees=2,
            decisions=[
                Decision("/repo/wt", "feat/x", remove=True, reason="merged to base"),
                Decision(_MAIN, "main", remove=False, reason=KEEP_MAIN),
            ],
        )
        text = format_report(report)
        assert "DRY-RUN" in text
        assert "removed nothing" in text
        assert "/repo/wt" in text

    def test_apply_summary_lists_removed(self):
        report = GcReport(
            timestamp="t",
            base_ref=_BASE,
            apply=True,
            main_worktree=_MAIN,
            total_worktrees=2,
            decisions=[
                Decision("/repo/wt", "feat/x", remove=True, reason="merged to base"),
            ],
            removed=["/repo/wt"],
        )
        text = format_report(report)
        assert "APPLY" in text
        assert "removed /repo/wt" in text


class TestCli:
    """Argument parsing and the main() exit-code contract."""

    def test_apply_defaults_to_false(self):
        args = parse_args([])
        assert args.apply is False
        assert args.base == _BASE

    def test_apply_flag_sets_true(self):
        args = parse_args(["--apply"])
        assert args.apply is True

    def test_main_dry_run_does_not_call_apply_removals(self, capsys):
        plan = GcReport(
            timestamp="t",
            base_ref=_BASE,
            apply=False,
            main_worktree=_MAIN,
            total_worktrees=2,
            decisions=[
                Decision("/repo/wt", "feat/x", remove=True, reason="merged to base"),
            ],
        )
        with (
            patch("scripts.maintenance.gc_worktrees.build_report", return_value=plan),
            patch("scripts.maintenance.gc_worktrees.apply_removals") as apply_mock,
        ):
            code = main([])
        apply_mock.assert_not_called()
        assert code == 0
        assert "DRY-RUN" in capsys.readouterr().out

    def test_main_apply_calls_apply_removals(self):
        plan = GcReport(
            timestamp="t",
            base_ref=_BASE,
            apply=True,
            main_worktree=_MAIN,
            total_worktrees=1,
            decisions=[],
        )
        with (
            patch("scripts.maintenance.gc_worktrees.build_report", return_value=plan),
            patch("scripts.maintenance.gc_worktrees.apply_removals") as apply_mock,
        ):
            code = main(["--apply"])
        apply_mock.assert_called_once_with(plan)
        assert code == 0

    def test_main_apply_returns_2_when_removal_errors_recorded(self):
        plan = GcReport(
            timestamp="t",
            base_ref=_BASE,
            apply=True,
            main_worktree=_MAIN,
            total_worktrees=1,
            decisions=[
                Decision("/repo/wt", "feat/x", remove=True, reason="merged to base"),
            ],
        )

        def record_error(report: GcReport) -> None:
            report.remove_errors.append("/repo/wt: locked by index")

        with (
            patch("scripts.maintenance.gc_worktrees.build_report", return_value=plan),
            patch(
                "scripts.maintenance.gc_worktrees.apply_removals",
                side_effect=record_error,
            ),
        ):
            code = main(["--apply"])

        assert code == 2

    def test_main_returns_2_on_git_error(self, capsys):
        with patch(
            "scripts.maintenance.gc_worktrees.build_report",
            side_effect=RuntimeError("git worktree list failed"),
        ):
            code = main([])
        assert code == 2
        assert "error:" in capsys.readouterr().err

    def test_main_json_output(self, capsys):
        plan = GcReport(
            timestamp="t",
            base_ref=_BASE,
            apply=False,
            main_worktree=_MAIN,
            total_worktrees=1,
            decisions=[],
        )
        with patch("scripts.maintenance.gc_worktrees.build_report", return_value=plan):
            code = main(["--json"])
        assert code == 0
        out = capsys.readouterr().out
        assert '"base_ref": "origin/main"' in out

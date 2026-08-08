"""Argument parsing and process exit codes for gc_worktrees.

The default must be dry-run: a flag that silently defaults to mutating is the
one parsing bug that costs work rather than a rerun. Exit codes follow
ADR-035, so a caller can tell a clean report from a git failure.

The safety decisions themselves are tested in ``test_gc_worktrees.py``.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from scripts.maintenance.gc_worktrees import (
    Decision,
    GcReport,
    main,
    parse_args,
)

_MODULE = "scripts.maintenance.gc_worktrees"


_STUB_HEAD = "f" * 40


@pytest.fixture(autouse=True)
def _stub_pre_removal_head():
    """Unit tests name paths that do not exist, so the pre-removal HEAD read is stubbed.

    ``apply_removals`` reads each candidate's HEAD twice, once with the recheck
    and once immediately before removing it, and refuses when the two differ.
    Against a fabricated path both reads fail and every removal is withheld,
    which would hide what these tests are actually about. Tests that care about
    the comparison patch it again with their own values.
    """
    with patch(f"{_MODULE}._gc_apply._head_of", return_value=_STUB_HEAD):
        yield


_MAIN = "/repo"
_BASE = "origin/main"


def _agrees(report: GcReport):
    """A recheck that reproduces the plan, i.e. nothing changed underneath it.

    ``apply_removals`` only reads the fresh report, so handing back the same
    object is the honest way to say the second look found the same repository.
    """
    return lambda: report


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
            patch("scripts.maintenance.gc_worktrees._gc_apply.apply_removals") as apply_mock,
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
            patch("scripts.maintenance.gc_worktrees._gc_apply.apply_removals") as apply_mock,
        ):
            code = main(["--apply"])
        assert [c.args[0] for c in apply_mock.call_args_list] == [plan]
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

        def record_error(report: GcReport, *_rest: object) -> None:
            report.remove_errors.append("/repo/wt: locked by index")

        with (
            patch("scripts.maintenance.gc_worktrees.build_report", return_value=plan),
            patch(
                "scripts.maintenance.gc_worktrees._gc_apply.apply_removals",
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

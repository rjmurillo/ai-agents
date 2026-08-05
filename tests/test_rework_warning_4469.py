"""Tests for rework_warning merge-commit exclusion and evidence cap (issue #4469).

A branch with merged origin/main commits must not count merge-integrated files
as session rework. The evidence output must be bounded even when hundreds of
paths exceed the threshold.
"""

from __future__ import annotations

from pathlib import Path

# Load the module under test directly without full package resolution.
_REWORK_PATH = (
    Path(__file__).resolve().parents[1]
    / ".claude/skills/session-end/scripts/rework_warning.py"
)


def _load_rework():
    import importlib.util

    spec = importlib.util.spec_from_file_location("rework_warning", _REWORK_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


RW = _load_rework()


class TestMergeCommitExclusion:
    """--no-merges in the git log argv so merge-integrated edits are not counted."""

    def test_git_log_argv_contains_no_merges(self) -> None:
        """The canonical git argv must exclude merge commits (issue #4469)."""
        assert "--no-merges" in RW._GIT_LOG_ARGV, (
            "_GIT_LOG_ARGV must contain '--no-merges' so merge-integrated "
            "file edits are not counted as branch rework"
        )

    def test_count_paths_ignores_lines_from_merge_commits(self) -> None:
        """_count_paths only sees --no-merges output; it should count correctly."""
        # Simulate output from non-merge commits only.
        stdout = "M\tscripts/foo.py\n" * 7
        counts = RW._count_paths(stdout)
        assert counts["scripts/foo.py"] == 7

    def test_merge_only_branch_produces_no_rework(self) -> None:
        """A branch whose only commits are merges produces zero rework warnings."""
        # With --no-merges, git emits nothing.
        from unittest import mock

        with mock.patch.object(RW, "_run_git_log", return_value=""):
            result = RW.compute_rework_warning()
        assert result == []

    def test_six_real_edits_still_warns(self) -> None:
        """Merge exclusion must not suppress genuine rework signals."""
        from unittest import mock

        stdout = "M\tscripts/real.py\n" * 6
        with mock.patch.object(RW, "_run_git_log", return_value=stdout):
            result = RW.compute_rework_warning()
        assert len(result) == 1
        assert result[0][0] == "scripts/real.py"
        assert result[0][1] == 6

    def test_five_edits_below_threshold_produce_no_warning(self) -> None:
        from unittest import mock

        stdout = "M\tscripts/below.py\n" * 5
        with mock.patch.object(RW, "_run_git_log", return_value=stdout):
            result = RW.compute_rework_warning()
        assert result == []


class TestEvidenceCap:
    """emit_rework_warning_lines caps output at _EVIDENCE_CAP paths."""

    def test_empty_items_returns_none_line(self) -> None:
        lines = RW.emit_rework_warning_lines([])
        assert lines == ["rework-warning: none"]

    def test_below_cap_returns_all_items(self) -> None:
        items = [(f"path/{i}.py", 6) for i in range(RW._EVIDENCE_CAP)]
        lines = RW.emit_rework_warning_lines(items)
        assert len(lines) == RW._EVIDENCE_CAP
        assert "omitted" not in " ".join(lines)

    def test_above_cap_truncates_and_appends_summary(self) -> None:
        total = RW._EVIDENCE_CAP + 10
        items = [(f"path/{i}.py", 6 + i) for i in range(total)]
        lines = RW.emit_rework_warning_lines(items)
        assert len(lines) == RW._EVIDENCE_CAP + 1
        assert "10 more" in lines[-1]
        assert "omitted" in lines[-1]

    def test_at_cap_exactly_no_summary_line(self) -> None:
        items = [(f"path/{i}.py", 6) for i in range(RW._EVIDENCE_CAP)]
        lines = RW.emit_rework_warning_lines(items)
        assert len(lines) == RW._EVIDENCE_CAP
        assert all("omitted" not in ln for ln in lines)

    def test_cap_is_defined(self) -> None:
        assert isinstance(RW._EVIDENCE_CAP, int) and RW._EVIDENCE_CAP > 0

    def test_936_items_produce_bounded_output(self) -> None:
        """Regression: the reported 936-path evidence must not persist verbatim."""
        items = [(f"path/{i}.py", 10) for i in range(936)]
        lines = RW.emit_rework_warning_lines(items)
        assert len(lines) <= RW._EVIDENCE_CAP + 1

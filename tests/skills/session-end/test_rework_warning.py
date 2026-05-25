"""Tests for compute_rework_warning and emit_rework_warning_lines (REQ-009-09).

Pins the REQ-009-07/08 contract for the rework-warning function inside
`.claude/skills/session-end/scripts/complete_session_log.py`. The
function counts files edited >= 6 times in the current branch's history
against `origin/{base}` and excludes generated-artifact paths.

Tests stub `subprocess.run` so no live git access is required.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = REPO_ROOT / ".claude" / "skills" / "session-end" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import complete_session_log as csl  # noqa: E402
import rework_warning as rw  # noqa: E402


def _stub_completed(stdout: str, returncode: int = 0) -> Any:
    """Return a subprocess.CompletedProcess-like double for one git call."""
    return mock.Mock(stdout=stdout, stderr="", returncode=returncode)


class ComputeReworkWarningTests(unittest.TestCase):
    """Threshold and exclusion contract for compute_rework_warning."""

    def test_threshold_six_separates_signal_from_noise(self) -> None:
        """Files at 6+ edits surface; files at 3 do not. REQ-009-09 AC."""
        # Three files; counts after Counter: a.py=8, b.py=3, c.py=6.
        # `git log --name-status` outputs `<status>\t<path>` per line.
        stub_output = "\n".join(
            ["M\ta.py"] * 8 + ["M\tb.py"] * 3 + ["M\tc.py"] * 6,
        )
        with mock.patch.object(
            csl.subprocess, "run", return_value=_stub_completed(stub_output),
        ):
            result = csl.compute_rework_warning(branch_base="main")
        # Expect descending-by-count order; 6+ only.
        self.assertEqual(result, [("a.py", 8), ("c.py", 6)])

    def test_empty_branch_returns_empty_list(self) -> None:
        """No commits ahead of base -> no rework. REQ-009-08 negative case."""
        with mock.patch.object(
            csl.subprocess, "run", return_value=_stub_completed(""),
        ):
            self.assertEqual(csl.compute_rework_warning(branch_base="main"), [])

    def test_rename_collapsed_to_new_path(self) -> None:
        """A file renamed mid-branch counts once, not twice. REQ-009-09 AC.

        `git log --name-status -M` emits a rename line as:
            `R<score>\told_path\tnew_path`
        Edits to the old name before the rename are normalized to the
        new name so total counts are correct.
        """
        # 4 edits to old name, 1 rename, 2 edits to new name = 7 total.
        lines = (
            ["M\tscripts/old_foo.py"] * 4
            + ["R100\tscripts/old_foo.py\tscripts/foo.py"]
            + ["M\tscripts/foo.py"] * 2
        )
        with mock.patch.object(
            csl.subprocess, "run", return_value=_stub_completed("\n".join(lines)),
        ):
            result = csl.compute_rework_warning(branch_base="main")
        self.assertEqual(result, [("scripts/foo.py", 7)])

    def test_dir_rename_form_collapses(self) -> None:
        """Rename from old dir to new dir counts correctly."""
        # 3 edits to old path, 1 rename, 2 edits to new path = 6 total.
        lines = (
            ["M\tpkg/old/util.py"] * 3
            + ["R100\tpkg/old/util.py\tpkg/new/util.py"]
            + ["M\tpkg/new/util.py"] * 2
        )
        with mock.patch.object(
            csl.subprocess, "run", return_value=_stub_completed("\n".join(lines)),
        ):
            result = csl.compute_rework_warning(branch_base="main")
        # 3 + 1 + 2 = 6 edits on the new path; threshold met.
        self.assertEqual(result, [("pkg/new/util.py", 6)])

    def test_generated_pattern_excluded(self) -> None:
        """`*.session.json` files do not count, even at 10 edits.

        The session log itself legitimately turns over many times per
        session. Counting it would drown real signal.
        """
        lines = (
            ["M\t2026-05-10-session-1.session.json"] * 10
            + ["M\tsrc/claude/agents/foo.md"] * 8
            + ["M\tscripts/real.py"] * 7
        )
        with mock.patch.object(
            csl.subprocess, "run", return_value=_stub_completed("\n".join(lines)),
        ):
            result = csl.compute_rework_warning(branch_base="main")
        # Only the real script crosses the threshold and is not excluded.
        self.assertEqual(result, [("scripts/real.py", 7)])

    def test_git_failure_returns_empty_list(self) -> None:
        """Git exit code != 0 -> empty list, never raise."""
        with mock.patch.object(
            csl.subprocess, "run", return_value=_stub_completed("", returncode=128),
        ):
            self.assertEqual(csl.compute_rework_warning(branch_base="main"), [])

    def test_git_missing_returns_empty_list(self) -> None:
        """FileNotFoundError (no git binary) -> empty list, never raise."""
        with mock.patch.object(
            csl.subprocess, "run", side_effect=FileNotFoundError("git"),
        ):
            self.assertEqual(csl.compute_rework_warning(branch_base="main"), [])

    def test_timeout_returns_empty_list(self) -> None:
        """subprocess.TimeoutExpired -> empty list, never raise."""
        from subprocess import TimeoutExpired

        with mock.patch.object(
            csl.subprocess,
            "run",
            side_effect=TimeoutExpired(cmd="git", timeout=30),
        ):
            self.assertEqual(csl.compute_rework_warning(branch_base="main"), [])

    def test_argv_uses_canonical_git_log_form(self) -> None:
        """Canonical-source-mirror: git log argv matches the docstring claim.

        PR #1989 bot reviewers found the initial argv included
        ``--diff-filter=R`` which restricts output to renames only.
        Corrected argv keeps -M (rename detection) but drops the filter
        so all edits (M/A/R) are reported. Uses --name-status for proper
        rename tracking.
        """
        captured: dict[str, Any] = {}

        def _capture(*args: Any, **kwargs: Any) -> Any:
            captured["argv"] = args[0]
            return _stub_completed("")

        with mock.patch.object(csl.subprocess, "run", side_effect=_capture):
            csl.compute_rework_warning(branch_base="main")
        argv = captured["argv"]
        # Canonical: git log --name-status -M origin/main..HEAD --pretty=format:
        self.assertEqual(argv[0], "git")
        self.assertEqual(argv[1], "log")
        self.assertIn("--name-status", argv)
        self.assertNotIn(
            "--diff-filter=R",
            argv,
            "PR #1989: --diff-filter=R restricts to renames only; must be absent",
        )
        self.assertIn("-M", argv)
        self.assertIn("origin/main..HEAD", argv)
        self.assertIn("--pretty=format:", argv)

    def test_count_paths_handles_name_status_format(self) -> None:
        """POSITIVE: --name-status format is parsed correctly."""
        # Various status codes
        stdout = "M\tmodified.py\nA\tadded.py\nD\tdeleted.py\nM\tmodified.py"
        counts = rw._count_paths(stdout)
        self.assertEqual(counts["modified.py"], 2)
        self.assertEqual(counts["added.py"], 1)
        self.assertEqual(counts["deleted.py"], 1)

    def test_count_paths_handles_rename_tracking(self) -> None:
        """Renames are tracked and old names normalized to new names."""
        # 2 edits to old.py, 1 rename, 2 edits to new.py = 5 total under new.py
        stdout = "M\told.py\nM\told.py\nR100\told.py\tnew.py\nM\tnew.py\nM\tnew.py"
        counts = rw._count_paths(stdout)
        self.assertEqual(counts["new.py"], 5)
        self.assertNotIn("old.py", counts)

    def test_count_paths_handles_transitive_renames(self) -> None:
        """Transitive renames (a->b->c) resolve to final name."""
        stdout = "M\ta.py\nR100\ta.py\tb.py\nM\tb.py\nR100\tb.py\tc.py\nM\tc.py"
        counts = rw._count_paths(stdout)
        self.assertEqual(counts["c.py"], 5)
        self.assertNotIn("a.py", counts)
        self.assertNotIn("b.py", counts)

    def test_count_paths_handles_empty_and_whitespace(self) -> None:
        """NEGATIVE: empty lines and whitespace are skipped gracefully."""
        stdout = "\n  \nM\tfoo.py\n\n  \nM\tfoo.py\n"
        counts = rw._count_paths(stdout)
        self.assertEqual(counts["foo.py"], 2)

    def test_count_paths_skips_status_only_line(self) -> None:
        """NEGATIVE: a malformed git output line that has a status token
        but no tab and no path is skipped. Exercises the
        `else: continue` branch in `_count_paths` (rework_warning.py line
        for the malformed-line skip path). Real git never emits this
        shape, but the defensive branch protects the loop against any
        future format drift; the test pins the behavior."""
        stdout = "M\nM\tfoo.py"
        counts = rw._count_paths(stdout)
        self.assertEqual(counts["foo.py"], 1)
        self.assertNotIn("M", counts)

    def test_excluded_paths_positive_and_negative(self) -> None:
        """POSITIVE: known generated patterns excluded.
        NEGATIVE: ordinary paths are NOT excluded."""
        # POSITIVE: excluded patterns
        self.assertTrue(rw._is_excluded_rework_path("foo.session.json"))
        self.assertTrue(rw._is_excluded_rework_path("src/claude/agent.md"))
        self.assertTrue(rw._is_excluded_rework_path(".agents/sessions/log.json"))
        # NEGATIVE: ordinary paths
        self.assertFalse(rw._is_excluded_rework_path("scripts/scan.py"))
        self.assertFalse(rw._is_excluded_rework_path("tests/test_x.py"))
        self.assertFalse(rw._is_excluded_rework_path("a/session.json.bak"))
        # Edge: name CONTAINS session.json but does not END with it
        self.assertFalse(rw._is_excluded_rework_path("foo.session.json.old"))
        # Edge: path STARTS WITH src/claude but is the literal prefix folder
        # (still excluded as documented)
        self.assertTrue(rw._is_excluded_rework_path("src/claude/"))


class EmitReworkWarningLinesTests(unittest.TestCase):
    """REQ-009-08 positive-evidence contract for output rendering."""

    def test_none_case_emits_explicit_marker(self) -> None:
        """Empty input -> single `rework-warning: none` line, never silence."""
        self.assertEqual(csl.emit_rework_warning_lines([]), ["rework-warning: none"])

    def test_positive_case_format(self) -> None:
        """REQ-009-07 AC: per-file format is `rework-warning: {path} edited {n} times`."""
        lines = csl.emit_rework_warning_lines([("a.py", 8), ("c.py", 6)])
        self.assertEqual(
            lines,
            [
                "rework-warning: a.py edited 8 times",
                "rework-warning: c.py edited 6 times",
            ],
        )


class ReworkThresholdConstantTest(unittest.TestCase):
    """Threshold value is pinned so silent calibration drift is caught."""

    def test_threshold_is_six(self) -> None:
        """REQ-009-07: starter calibration is 6, per DESIGN-009."""
        self.assertEqual(csl.REWORK_THRESHOLD, 6)


if __name__ == "__main__":
    unittest.main()

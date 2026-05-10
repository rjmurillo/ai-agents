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
        # `git log --name-only` repeats the path once per commit it touches.
        stub_output = "\n".join(
            ["a.py"] * 8 + ["b.py"] * 3 + ["c.py"] * 6,
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

        `git log --name-only -M` emits a rename line in either of two
        shapes depending on path overlap:
            `old_path => new_path`
            `{old_dir => new_dir}/filename`
        Both must collapse to one logical file under the new name.
        """
        # 6 plain edits to scripts/foo.py + 1 rename event from old name.
        # Total observable edits is 7; threshold 6 keeps it in.
        lines = ["scripts/foo.py"] * 6 + ["scripts/old_foo.py => scripts/foo.py"]
        with mock.patch.object(
            csl.subprocess, "run", return_value=_stub_completed("\n".join(lines)),
        ):
            result = csl.compute_rework_warning(branch_base="main")
        self.assertEqual(result, [("scripts/foo.py", 7)])

    def test_dir_rename_form_collapses(self) -> None:
        """`{old => new}/filename` rename form collapses to new path."""
        lines = ["pkg/new/util.py"] * 5 + [
            "{pkg/old => pkg/new}/util.py",
        ]
        with mock.patch.object(
            csl.subprocess, "run", return_value=_stub_completed("\n".join(lines)),
        ):
            result = csl.compute_rework_warning(branch_base="main")
        # 5 + 1 = 6 edits on the new path; threshold met.
        self.assertEqual(result, [("pkg/new/util.py", 6)])

    def test_generated_pattern_excluded(self) -> None:
        """`*.session.json` files do not count, even at 10 edits.

        The session log itself legitimately turns over many times per
        session. Counting it would drown real signal.
        """
        lines = (
            ["2026-05-10-session-1.session.json"] * 10
            + ["src/claude/agents/foo.md"] * 8
            + ["scripts/real.py"] * 7
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
        so all edits (M/A/R) are reported.
        """
        captured: dict[str, Any] = {}

        def _capture(*args: Any, **kwargs: Any) -> Any:
            captured["argv"] = args[0]
            return _stub_completed("")

        with mock.patch.object(csl.subprocess, "run", side_effect=_capture):
            csl.compute_rework_warning(branch_base="main")
        argv = captured["argv"]
        # Canonical: git log --name-only -M origin/main..HEAD --pretty=format:
        self.assertEqual(argv[0], "git")
        self.assertEqual(argv[1], "log")
        self.assertIn("--name-only", argv)
        self.assertNotIn(
            "--diff-filter=R",
            argv,
            "PR #1989: --diff-filter=R restricts to renames only; must be absent",
        )
        self.assertIn("-M", argv)
        self.assertIn("origin/main..HEAD", argv)
        self.assertIn("--pretty=format:", argv)

    def test_collapse_rename_handles_subdir_brace_form_positive(self) -> None:
        """POSITIVE: every git rename form normalizes to the new path."""
        # PR #1989 gemini finding: path/{old => new} form was mishandled.
        self.assertEqual(
            rw._collapse_rename("path/{old_file => new_file}"),
            "path/new_file",
        )
        self.assertEqual(
            rw._collapse_rename("path/{old_subdir => new_subdir}/filename.py"),
            "path/new_subdir/filename.py",
        )
        self.assertEqual(
            rw._collapse_rename("a/b/{old => new}/c.py"),
            "a/b/new/c.py",
        )
        # Top-level brace form
        self.assertEqual(
            rw._collapse_rename("{old_dir => new_dir}/filename.py"),
            "new_dir/filename.py",
        )
        # Bare form
        self.assertEqual(rw._collapse_rename("old.py => new.py"), "new.py")
        # Non-rename pass-through
        self.assertEqual(rw._collapse_rename("foo.py"), "foo.py")

    def test_collapse_rename_empty_inside_brace_form(self) -> None:
        """Edge: brace form with empty new-side produces collapsed `//`.

        Covers the `while // in new_path:` slash-collapse loop body.
        """
        # `prefix/{old => }/suffix` -> empty new side -> would produce
        # `prefix//suffix` -> collapse to `prefix/suffix`.
        self.assertEqual(rw._collapse_rename("a/{b => }/c.py"), "a/c.py")

    def test_collapse_rename_negative_cases(self) -> None:
        """NEGATIVE: malformed inputs degrade gracefully (no exceptions)."""
        # Empty string
        self.assertEqual(rw._collapse_rename(""), "")
        # Whitespace-only collapses to empty
        self.assertEqual(rw._collapse_rename("   "), "")
        # Brace without close: treat as bare form, take after =>
        self.assertEqual(rw._collapse_rename("{old => new.py"), "new.py")
        # `=>` inside path but no brace and no space-separated form
        self.assertEqual(rw._collapse_rename("a=>b"), "b")
        # Multiple `=>` arrows: takes first split's right side
        # Then collapses inner braces
        result = rw._collapse_rename("path/{a => b => c}")
        self.assertTrue(
            result.startswith("path/"),
            f"multiple-arrow form should still produce a path-like result, got {result!r}",
        )
        # Trailing whitespace stripped
        self.assertEqual(rw._collapse_rename("foo.py   \t"), "foo.py")
        # Leading slash stripped (rare git form)
        self.assertEqual(rw._collapse_rename("/abs.py => /abs_new.py"), "abs_new.py")

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

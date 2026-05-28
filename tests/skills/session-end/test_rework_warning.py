"""Tests for compute_rework_warning and emit_rework_warning_lines (REQ-012-09).

Pins the REQ-012-07/08 contract for the rework-warning function inside
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
        """Files at 6+ edits surface; files at 3 do not. REQ-012-09 AC."""
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
        """No commits ahead of base -> no rework. REQ-012-08 negative case."""
        with mock.patch.object(
            csl.subprocess, "run", return_value=_stub_completed(""),
        ):
            self.assertEqual(csl.compute_rework_warning(branch_base="main"), [])

    def test_rename_collapsed_to_new_path(self) -> None:
        """A file renamed mid-branch counts once, not twice. REQ-012-09 AC.

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
    """REQ-012-08 positive-evidence contract for output rendering."""

    def test_none_case_emits_explicit_marker(self) -> None:
        """Empty input -> single `rework-warning: none` line, never silence."""
        self.assertEqual(csl.emit_rework_warning_lines([]), ["rework-warning: none"])

    def test_positive_case_format(self) -> None:
        """REQ-012-07 AC: per-file format is `rework-warning: {path} edited {n} times`."""
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
        """REQ-012-07: starter calibration is 6, per DESIGN-012."""
        self.assertEqual(csl.REWORK_THRESHOLD, 6)


class RunReworkWarningStepRuntimeFailureTests(unittest.TestCase):
    """REQ-012-08: rework-warning step MUST NOT block session-end.

    Pinned per PR #1989 review (cursor): a runtime exception inside
    compute_rework_warning or emit_rework_warning_lines must degrade to a
    notice line and return a non-crash summary string, never propagate.
    Step 4b runs before validation, so a crash would also prevent the
    validation step from running.
    ADR-060: function now returns (summary, evidence_lines) tuple.
    """

    def test_runtime_exception_in_compute_degrades_to_notice(self) -> None:
        """Exception inside compute_rework_warning returns the skip summary."""
        with mock.patch.object(
            csl, "compute_rework_warning", side_effect=RuntimeError("git boom"),
        ):
            summary, evidence = csl._run_rework_warning_step()
        self.assertEqual(summary, "Rework warning: skipped (runtime error)")
        self.assertEqual(len(evidence), 1)
        self.assertIn("skipped", evidence[0])

    def test_runtime_exception_in_emit_degrades_to_notice(self) -> None:
        """Exception inside emit_rework_warning_lines returns the skip summary."""
        with mock.patch.object(
            csl, "compute_rework_warning", return_value=[("a.py", 9)],
        ), mock.patch.object(
            csl, "emit_rework_warning_lines", side_effect=ValueError("render boom"),
        ):
            summary, evidence = csl._run_rework_warning_step()
        self.assertEqual(summary, "Rework warning: skipped (runtime error)")
        self.assertEqual(len(evidence), 1)
        self.assertIn("skipped", evidence[0])


class RunReworkWarningStepReturnShapeTests(unittest.TestCase):
    """ADR-060: _run_rework_warning_step returns (summary, evidence_lines) tuple.

    Pins the tuple shape and the content of evidence_lines for the
    no-warning case and the warning case.
    """

    def test_no_items_returns_none_summary_and_evidence_list(self) -> None:
        """Empty rework items produce a 'none' summary and a one-item evidence list."""
        with mock.patch.object(csl, "compute_rework_warning", return_value=[]):
            summary, evidence = csl._run_rework_warning_step()
        self.assertEqual(summary, "Rework warning: none")
        self.assertEqual(evidence, ["rework-warning: none"])

    def test_items_present_returns_warn_summary_and_evidence_lines(self) -> None:
        """Files over threshold -> WARN summary and evidence lines per file."""
        with mock.patch.object(
            csl, "compute_rework_warning", return_value=[("a.py", 8), ("b.py", 6)],
        ):
            summary, evidence = csl._run_rework_warning_step()
        self.assertIn("[WARN]", summary)
        self.assertIn("2 file(s)", summary)
        self.assertEqual(len(evidence), 2)
        self.assertEqual(evidence[0], "rework-warning: a.py edited 8 times")
        self.assertEqual(evidence[1], "rework-warning: b.py edited 6 times")

    def test_sibling_unavailable_returns_skipped_tuple(self) -> None:
        """When sibling module is missing, returns skipped summary + evidence list."""
        with (
            mock.patch.object(csl, "compute_rework_warning", None),
            mock.patch.object(csl, "emit_rework_warning_lines", None),
        ):
            summary, evidence = csl._run_rework_warning_step()
        self.assertIn("skipped", summary.lower())
        self.assertEqual(len(evidence), 1)
        self.assertIn("skipped", evidence[0])


class ReworkWarningSessionLogPersistenceTests(unittest.TestCase):
    """ADR-060: reworkWarning.Evidence is persisted in the session log JSON.

    Pins (a) presence of the field on new logs, and (b) tolerance on old
    logs that do not carry the field.
    """

    @staticmethod
    def _make_minimal_session_end() -> dict[str, Any]:
        """Build a minimal sessionEnd dict with all required MUST items."""
        required_items = [
            "handoffPreserved", "serenaMemoryUpdated", "markdownLintRun",
            "changesCommitted", "validationPassed", "checklistComplete",
        ]
        section: dict[str, Any] = {
            name: {"Complete": True, "Evidence": "evidence", "level": "MUST"}
            for name in required_items
        }
        return section

    def test_rework_warning_evidence_persisted_on_new_log(self) -> None:
        """After _run_rework_warning_step, session_end gains reworkWarning.Evidence."""
        session_end = self._make_minimal_session_end()
        with mock.patch.object(csl, "compute_rework_warning", return_value=[]):
            _, evidence = csl._run_rework_warning_step()
        # Simulate what main() does immediately after the step (ADR-060).
        session_end["reworkWarning"] = {"Evidence": evidence}
        self.assertIn("reworkWarning", session_end)
        self.assertIn("Evidence", session_end["reworkWarning"])
        self.assertEqual(session_end["reworkWarning"]["Evidence"], ["rework-warning: none"])

    def test_rework_warning_evidence_contains_warning_lines(self) -> None:
        """When rework files are found, Evidence carries their lines."""
        session_end = self._make_minimal_session_end()
        with mock.patch.object(
            csl, "compute_rework_warning", return_value=[("scan.py", 9)],
        ):
            _, evidence = csl._run_rework_warning_step()
        session_end["reworkWarning"] = {"Evidence": evidence}
        self.assertEqual(
            session_end["reworkWarning"]["Evidence"],
            ["rework-warning: scan.py edited 9 times"],
        )

    def test_old_log_without_rework_warning_field_is_tolerated(self) -> None:
        """An existing session_end dict without reworkWarning does not fail any check.

        validate_session_json only validates items declared as MUST/MUST NOT;
        an absent optional field is silently ignored (backward compatibility).
        """
        from scripts.validate_session_json import ValidationResult, validate_session_end

        session_end = self._make_minimal_session_end()
        # Confirm: no reworkWarning key present (simulates old log).
        self.assertNotIn("reworkWarning", session_end)

        result = ValidationResult()
        validate_session_end(session_end, result)
        self.assertEqual(result.errors, [], msg="Old log without reworkWarning must have no errors")

    def test_new_log_with_rework_warning_field_passes_validation(self) -> None:
        """A session_end dict WITH reworkWarning also passes validation."""
        from scripts.validate_session_json import ValidationResult, validate_session_end

        session_end = self._make_minimal_session_end()
        session_end["reworkWarning"] = {"Evidence": ["rework-warning: none"]}

        result = ValidationResult()
        validate_session_end(session_end, result)
        self.assertEqual(result.errors, [], msg="New log with reworkWarning must have no errors")

    def test_rework_warning_persistence_preserves_existing_keys(self) -> None:
        """Evidence assignment must not clobber pre-existing reworkWarning keys.

        Mirrors the persistence pattern used in main(): when reworkWarning
        already carries metadata (e.g., level, Complete) from a template,
        only Evidence is added or updated. Other keys must survive.
        """
        session_end = self._make_minimal_session_end()
        session_end["reworkWarning"] = {"level": "INFO", "Complete": True}

        with mock.patch.object(csl, "compute_rework_warning", return_value=[]):
            _, evidence = csl._run_rework_warning_step()

        # Mirror the main() guard pattern.
        if "reworkWarning" not in session_end:
            session_end["reworkWarning"] = {}
        session_end["reworkWarning"]["Evidence"] = evidence

        self.assertEqual(session_end["reworkWarning"]["level"], "INFO")
        self.assertTrue(session_end["reworkWarning"]["Complete"])
        self.assertEqual(
            session_end["reworkWarning"]["Evidence"], ["rework-warning: none"],
        )


class LazyLoadTests(unittest.TestCase):
    """Issue #2069 Finding B: sibling rework_warning module is loaded lazily.

    The docstring at the top of complete_session_log.py claimed lazy
    loading inside main(), but the implementation ran the load at module
    import time. Either the comment or the code was wrong. We fix the
    code: the sibling is not loaded until the first call to
    _run_rework_warning_step().

    Subprocess isolation ensures test ordering in the same pytest session
    cannot mask the bug. A peer test in this file imports the sibling
    directly (`import rework_warning as rw`), which warms sys.modules and
    triggers attribute access on `csl.compute_rework_warning`. The check
    that proves lazy loading is the membership of `compute_rework_warning`
    in `vars(csl)` BEFORE any access path triggers the load: the name
    must be absent from the module's `__dict__` (unbound). PEP 562
    `__getattr__` binds it on demand, so `getattr(csl, ...)` would
    falsely succeed; we inspect `vars()` directly to bypass that hook.

    PR #2070 follow-up (Copilot review thread): an earlier draft of this
    docstring said the proof was `csl.compute_rework_warning is None`,
    which contradicts the actual check (`'compute_rework_warning' in
    vars(csl)` is False). The docstring now matches the tested condition.
    """

    def _run_probe(self, post_import: str) -> tuple[int, str, str]:
        """Run a fresh-interpreter probe and return (rc, stdout, stderr)."""
        import subprocess

        script_dir = REPO_ROOT / ".claude" / "skills" / "session-end" / "scripts"
        probe = (
            "import sys;"
            f"sys.path.insert(0, {str(script_dir)!r});"
            "import complete_session_log as csl;"
            + post_import
        )
        completed = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True, text=True, timeout=10, check=False,
        )
        return completed.returncode, completed.stdout, completed.stderr

    def test_compute_unbound_immediately_after_import(self) -> None:
        """POSITIVE: compute_rework_warning is NOT in module globals at import time.

        Use vars() to inspect the module dict directly, avoiding the
        PEP 562 __getattr__ side effect that would trigger lazy loading.
        Before the lazy fix, the name was bound to the real function at
        import time; after the fix, the name is absent from globals
        until first access.
        """
        rc, stdout, _ = self._run_probe(
            "print('HAS=', 'compute_rework_warning' in vars(csl))"
        )
        self.assertEqual(rc, 0)
        self.assertIn(
            "HAS= False", stdout,
            f"compute_rework_warning bound at import time. stdout={stdout!r}",
        )

    def test_threshold_unbound_immediately_after_import(self) -> None:
        """POSITIVE: REWORK_THRESHOLD is the sentinel until first lazy load."""
        # Use the sentinel-known value 6 only AFTER load; before load, the
        # module dict should not have the real attribute bound.
        rc, stdout, _ = self._run_probe(
            "print('HAS=', 'REWORK_THRESHOLD' in vars(csl))"
        )
        self.assertEqual(rc, 0)
        self.assertIn(
            "HAS= False", stdout,
            f"REWORK_THRESHOLD bound at import. stdout={stdout!r}",
        )

    def test_compute_bound_after_ensure_loaded(self) -> None:
        """POSITIVE: calling _ensure_rework_loaded lazy-binds the sibling.

        PR #2070 Copilot review thread (LOGIC): the earlier probe invoked
        `csl._run_rework_warning_step()`, which spawns a real `git`
        subprocess via `compute_rework_warning()`. The minimal probe for
        "the lazy binding works" is calling `_ensure_rework_loaded()`
        directly; it triggers the binding without running the step's
        runtime work. The "step calls ensure" claim is covered by the
        in-process unit test `test_step_invokes_ensure_rework_loaded`
        below.
        """
        rc, stdout, _ = self._run_probe(
            "csl._ensure_rework_loaded();"
            "print('BOUND=', vars(csl).get('compute_rework_warning') is not None)"
        )
        self.assertEqual(rc, 0)
        self.assertIn(
            "BOUND= True", stdout,
            f"_ensure_rework_loaded did not bind the sibling. stdout={stdout!r}",
        )


class StepInvokesEnsureLoadedTest(unittest.TestCase):
    """PR #2070 Copilot follow-up: pair the lazy-load proof with the
    in-process claim that `_run_rework_warning_step` calls
    `_ensure_rework_loaded` before doing its runtime work. The probe
    test above proves the binding works; this test proves the step is
    the trigger. Together they cover "step lazy-loads" without running
    real subprocesses.
    """

    def test_step_invokes_ensure_rework_loaded(self) -> None:
        """POSITIVE: the step calls _ensure_rework_loaded before runtime work.

        The step body in complete_session_log.py first calls
        `_ensure_rework_loaded()`, then reads `compute_rework_warning` and
        `emit_rework_warning_lines` out of `globals()`. We stub those
        siblings into globals so the step does no real git work, and we
        wrap `_ensure_rework_loaded` to confirm it is the trigger.
        """
        import importlib
        import sys
        from unittest.mock import patch

        script_dir = REPO_ROOT / ".claude" / "skills" / "session-end" / "scripts"
        sys.path.insert(0, str(script_dir))
        try:
            csl = importlib.import_module("complete_session_log")
            csl = importlib.reload(csl)
            # Pre-populate globals so the step does not need real siblings.
            csl_globals = vars(csl)
            csl_globals["compute_rework_warning"] = lambda: []
            csl_globals["emit_rework_warning_lines"] = lambda paths: []
            csl_globals["REWORK_THRESHOLD"] = 6
            with patch.object(csl, "_ensure_rework_loaded") as ensure:
                csl._run_rework_warning_step()
                ensure.assert_called_once()
        finally:
            sys.path.remove(str(script_dir))


if __name__ == "__main__":
    unittest.main()

"""Tests for the rework warning module (REQ-010-01..04).

Pins the REQ-010 acceptance criteria:

- REQ-010-01: real-fixture test asserts scan.py at 14 edits appears in
  the warning list AND episode-2026-05-10.json at 19 edits does NOT,
  so generated-log churn does not swamp real signal.
- REQ-010-02: `_REWORK_EXCLUDED_PREFIXES` includes
  `.agents/memory/episodes/` so episode logs are filtered alongside
  session logs.
- REQ-010-03: self-apply gate (verified in /build, not in this file).
- REQ-010-04: test fixture loaded from a captured real-branch output
  saved as a test-data file, not constructed inline (per
  `testing-007-contract-testing` memory).

Fixture: tests/skills/session-end/fixtures/orphan_ref_validator_git_log.txt
Source: feat/issue-1939-orphan-ref-validator @ 79afa210 (merged via PR #1979).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = REPO_ROOT / ".claude" / "skills" / "session-end" / "scripts"
FIXTURE_PATH = (
    REPO_ROOT
    / "tests"
    / "skills"
    / "session-end"
    / "fixtures"
    / "orphan_ref_validator_git_log.txt"
)

sys.path.insert(0, str(SCRIPT_DIR))

import rework_warning as rw  # noqa: E402


def _stub_completed(stdout: str, returncode: int = 0):
    """subprocess.CompletedProcess double for one git invocation."""
    return mock.Mock(stdout=stdout, stderr="", returncode=returncode)


class Req010Tests(unittest.TestCase):
    """REQ-010 acceptance criteria pinned against captured real fixture."""

    @classmethod
    def setUpClass(cls) -> None:
        # PR #2004 copilot: guard the fixture read so test_fixture_file_exists
        # produces a clear assertion failure if the fixture is missing,
        # instead of FileNotFoundError on class setup that prevents any
        # test from running.
        if not FIXTURE_PATH.is_file():
            cls.fixture_text = ""
            return
        cls.fixture_text = FIXTURE_PATH.read_text(encoding="utf-8")

    def test_fixture_file_exists(self) -> None:
        """REQ-010-04: fixture loaded from a file, not constructed inline."""
        self.assertTrue(
            FIXTURE_PATH.is_file(),
            f"Expected captured-schema fixture at {FIXTURE_PATH}",
        )
        # Sanity: fixture contains the expected real-branch entries
        self.assertIn(
            ".claude/skills/orphan-ref-validator/scripts/scan.py",
            self.fixture_text,
            "Fixture must contain the real scan.py rework signal",
        )
        self.assertIn(
            ".agents/memory/episodes/episode-2026-05-10-session-1830.json",
            self.fixture_text,
            "Fixture must contain the episode-log noise that REQ-010-02 excludes",
        )

    def test_real_fixture_emits_scan_py_excludes_episode(self) -> None:
        """REQ-010-01 + REQ-010-02: real-fixture detector contract.

        Against the captured orphan-ref-validator git log:
        - scan.py at 14 edits MUST appear (real rework signal).
        - episode-2026-05-10-session-1830.json at 19 edits MUST NOT
          appear (excluded by `.agents/memory/episodes/` prefix).
        - session JSON at 19 edits MUST NOT appear (existing exclusion
          via `.agents/sessions/` prefix).
        """
        with mock.patch.object(
            rw.subprocess, "run", return_value=_stub_completed(self.fixture_text),
        ):
            result = rw.compute_rework_warning(branch_base="main")

        # Convert to a dict for easier assertions; preserve order via list.
        result_dict = dict(result)

        # MUST appear (real signal)
        self.assertIn(
            ".claude/skills/orphan-ref-validator/scripts/scan.py",
            result_dict,
            "scan.py at 14 edits is real rework; must surface in warning",
        )
        self.assertEqual(
            result_dict[".claude/skills/orphan-ref-validator/scripts/scan.py"],
            14,
            "scan.py edit count must match fixture (14)",
        )

        # MUST NOT appear (excluded by REQ-010-02 — new exclusion)
        self.assertNotIn(
            ".agents/memory/episodes/episode-2026-05-10-session-1830.json",
            result_dict,
            "Episode logs are generated artifacts; REQ-010-02 excludes them",
        )

        # MUST NOT appear (existing exclusion via `.agents/sessions/` prefix)
        self.assertNotIn(
            ".agents/sessions/2026-05-10-session-1830-resume-skill-catalog-triage-post-1942.json",
            result_dict,
            "Session JSON files were already excluded; verify still excluded",
        )

    def test_exclusion_list_contains_episodes_prefix(self) -> None:
        """REQ-010-02: `_REWORK_EXCLUDED_PREFIXES` includes the episodes path."""
        self.assertIn(
            ".agents/memory/episodes/",
            rw._REWORK_EXCLUDED_PREFIXES,
            "REQ-010-02: episode-log prefix must be in the exclusion list",
        )

    def test_threshold_is_six(self) -> None:
        """REQ-010 carries forward REQ-009-09's threshold-6 (empirically correct)."""
        self.assertEqual(rw.REWORK_THRESHOLD, 6)


if __name__ == "__main__":
    unittest.main()

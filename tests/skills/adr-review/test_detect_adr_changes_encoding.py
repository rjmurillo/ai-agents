#!/usr/bin/env python3
"""Encoding contract for detect_adr_changes: undecodable records are data, not crashes.

Split from ``test_detect_adr_changes.py`` rather than appended to it. That
module was at 490 lines and these cases pushed it to 562, over the 500-line
ceiling the taste-lint file-size rule enforces. A suppression would have been
the cheaper move and the wrong one: these cases share a single premise, that a
record which cannot be decoded is an undeclared state rather than a failure of
the tool, so they form a cohesive module on their own terms.
"""

from __future__ import annotations

import sys
from pathlib import Path

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
PROJECT_ROOT = str(Path(__file__).resolve().parents[3])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from claude_skills_import import import_skill_script

mod = import_skill_script(".claude/skills/adr-review/scripts/detect_adr_changes.py")


# ── Invalid UTF-8 must not raise past the handlers ───────────────────────────
#
# UnicodeDecodeError subclasses ValueError, not OSError, so an `except OSError`
# arm around read_text(encoding="utf-8") never sees it. Reported by Cursor
# Bugbot on PR #5209 against _get_adr_status; the sweep found the same shape in
# _get_dependent_adrs, which the report did not name.


class TestUndecodableRecords:
    """A record with a stray byte is skipped or unknown, never a traceback."""

    def test_get_adr_status_returns_unknown_for_invalid_utf8(
        self, tmp_path: Path
    ) -> None:
        """The undecodable state joins the other undeclared states.

        The caller is written around STATUS_UNKNOWN meaning 'this record does
        not declare a status'. Bytes that cannot be decoded are exactly that,
        so they take the same path rather than raising through it.
        """
        bad = tmp_path / "ADR-999-bad.md"
        bad.write_bytes(b"\xff\xfe not utf-8")

        assert mod._get_adr_status(bad) == mod.STATUS_UNKNOWN

    def test_get_adr_status_still_reads_a_decodable_record(
        self, tmp_path: Path
    ) -> None:
        """Negative control: the new arm does not swallow good input.

        Without this, a handler that returned STATUS_UNKNOWN unconditionally
        would pass the test above and be indistinguishable from a correct one.
        """
        good = tmp_path / "ADR-001-good.md"
        good.write_text("---\nstatus: accepted\n---\n\n# ADR-001\n", encoding="utf-8")

        assert mod._get_adr_status(good) == "accepted"

    def test_dependent_scan_skips_an_undecodable_record(
        self, tmp_path: Path
    ) -> None:
        """One corrupt record must not abort the scan of the rest.

        This site was NOT in the bug report. Fixing only the reported handler
        would have left the dependent scan crashing on the same input, which is
        the partial-guard failure the mirror obligation exists to prevent.
        """
        adr_dir = tmp_path / ".agents" / "architecture"
        adr_dir.mkdir(parents=True)
        (adr_dir / "ADR-002-bad.md").write_bytes(b"\xff\xfe not utf-8")
        (adr_dir / "ADR-003-refs.md").write_text(
            "# ADR-003\n\nSupersedes ADR-001.\n", encoding="utf-8"
        )

        dependents = mod._get_dependent_adrs("ADR-001", tmp_path)

        assert [Path(p).name for p in dependents] == ["ADR-003-refs.md"]

    def test_dependent_scan_finds_nothing_when_no_record_references_it(
        self, tmp_path: Path
    ) -> None:
        """Negative control for the scan: absence is reported as absence."""
        adr_dir = tmp_path / ".agents" / "architecture"
        adr_dir.mkdir(parents=True)
        (adr_dir / "ADR-002-bad.md").write_bytes(b"\xff\xfe not utf-8")
        (adr_dir / "ADR-003-quiet.md").write_text(
            "# ADR-003\n\nNo references here.\n", encoding="utf-8"
        )

        assert mod._get_dependent_adrs("ADR-001", tmp_path) == []

"""Regression tests for ADR-043 issue #4401.

Issue #4401 found that ADR-043 line 60 claims --no-globs ensures "only
specified files are processed", which is mechanically wrong: the flag governs
the config's globs key (which adds paths) but says nothing about ignores (which
drops them). Files matching ignores are silently excluded even when passed
explicitly. A correction note was appended to the ADR; this test ensures the
wrong phrase cannot re-enter any ADR or rule file.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ADR_PATH = PROJECT_ROOT / ".agents" / "architecture" / "ADR-043-scoped-tool-execution.md"
_DASH_PATTERN = re.compile("[\u2013\u2014]")

WRONG_PHRASE = "ensuring only specified files are processed"
CORRECTION_ANCHOR = "Correction Note"
IGNORES_CAVEAT = "`ignores`"
GLOBS_KEY_INERT = "no `globs` key"


@pytest.fixture(scope="module")
def adr_text() -> str:
    assert ADR_PATH.is_file(), f"ADR-043 not found at {ADR_PATH}"
    return ADR_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def normalized(adr_text: str) -> str:
    return re.sub(r"\s+", " ", adr_text)


class TestADR043CorrectionNote:
    def test_correction_note_present(self, adr_text: str) -> None:
        assert CORRECTION_ANCHOR in adr_text, "ADR-043 must contain a Correction Note section"

    def test_ignores_caveat_present(self, adr_text: str) -> None:
        assert IGNORES_CAVEAT in adr_text, (
            "Correction note must explain that ignores still applies to explicitly passed files"
        )

    def test_globs_key_inert_present(self, normalized: str) -> None:
        assert GLOBS_KEY_INERT in normalized, (
            "Correction note must state that this repo has no globs key so --no-globs is inert"
        )

    def test_original_decision_preserved(self, adr_text: str) -> None:
        assert "## Decision" in adr_text, "Original Decision section must be preserved"
        assert "MUST scope to changed files" in adr_text, (
            "Original decision text must be preserved unchanged"
        )

    def test_wrong_phrase_still_present_in_original_section(self, adr_text: str) -> None:
        head, sep, _ = adr_text.partition(CORRECTION_ANCHOR)
        assert sep, "ADR-043 must contain a Correction Note section"
        assert WRONG_PHRASE in head, (
            "Original Implementation Notes text must be preserved (not edited in place). "
            "The phrase must appear before the Correction Note; a copy quoted inside the "
            "note would not prove the original survived."
        )

    def test_no_dash_violations(self, adr_text: str) -> None:
        matches = _DASH_PATTERN.findall(adr_text)
        assert not matches, f"ADR-043 contains {len(matches)} prohibited dash(es)"


class TestNoPhraseRepetitionAcrossRules:
    """Verify the wrong phrase does not appear in any ADR or rule file."""

    def _gather_files(self) -> list[Path]:
        adrs = list((PROJECT_ROOT / ".agents" / "architecture").glob("ADR-*.md"))
        rules = list((PROJECT_ROOT / ".claude" / "rules").glob("*.md"))
        return adrs + rules

    def test_wrong_phrase_absent_from_all_adrs_and_rules(self) -> None:
        offenders: list[str] = []
        unreadable: list[str] = []
        for path in self._gather_files():
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as exc:
                unreadable.append(f"{path.relative_to(PROJECT_ROOT)} ({exc})")
                continue
            if WRONG_PHRASE in text and path != ADR_PATH:
                offenders.append(str(path.relative_to(PROJECT_ROOT)))
        assert not unreadable, (
            f"Could not read {len(unreadable)} target file(s): {unreadable}. "
            "This test enforces a repo-wide invariant, so an unreadable file means "
            "the invariant was not checked, not that it holds."
        )
        assert not offenders, (
            f"Wrong phrase '{WRONG_PHRASE}' found in: {offenders}. "
            "Remove or correct it; the phrase implies a scope guarantee "
            "--no-globs does not provide."
        )

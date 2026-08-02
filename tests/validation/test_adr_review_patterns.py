"""Tests for ADR_REVIEW_PATTERNS: case-insensitive and natural-language coverage.

Issue #4135: the validator accepted only exact phrases (/adr-review,
adr-review skill, ADR Review Protocol). Natural evidence such as
"Completed six-role ADR review" or "Ran six-role adr-review" failed.
The validator measured compliance with a phrasebook, not the presence
of evidence. This test suite verifies the fix: patterns are now
case-insensitive and recognise common natural-language forms.

Tests cover:
- Positive: each accepted form passes _session_has_adr_review.
- Negative: missing evidence is still blocked.
- Edge: case variations, hyphen vs space, slash prefix.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "validation" / "git_hook_policy.py"

_spec = importlib.util.spec_from_file_location("git_hook_policy", _SCRIPT)
assert _spec is not None and _spec.loader is not None
policy = importlib.util.module_from_spec(_spec)
sys.modules["git_hook_policy"] = policy
_spec.loader.exec_module(policy)


def _write_session(tmp_path: Path, content: str) -> Path:
    log = tmp_path / "today-session.json"
    log.write_text(content, encoding="utf-8")
    return log


# --- Positive cases: evidence that must pass ---

@pytest.mark.parametrize(
    "evidence",
    [
        # Original exact phrases still work.
        "invoked /adr-review skill",
        "ran the adr-review skill",
        "ADR Review Protocol followed",
        # Case variations of the slash form.
        "/ADR-Review invoked",
        "/Adr-Review logged",
        # Case variations of the skill form.
        "ADR-Review Skill invoked for ADR-092",
        "adr-review SKILL completed",
        # Natural six-role phrasing with space separator (the bug).
        "Completed six-role ADR review",
        "Ran six-role adr-review",
        # All-lowercase natural form.
        "six-role adr review completed",
        # Uppercase natural form.
        "SIX-ROLE ADR REVIEW COMPLETE",
        # Inline mention inside prose.
        "Skill catalog reviewed via AGENTS.md; adr-review skill invoked for ADR-092",
        # Multi-agent consensus evidence (only caught by the consensus pattern).
        "multi-agent consensus reached on ADR content",
        "multi-agent consensus was reached; ADR approved",
    ],
)
def test_evidence_passes(tmp_path: Path, evidence: str) -> None:
    log = _write_session(tmp_path, f'{{"evidence": "{evidence}"}}')
    result = policy._session_has_adr_review(log)
    assert result is True, (
        f"Expected _session_has_adr_review to return True for: {evidence!r}"
    )


# --- Negative cases: missing evidence must still block ---

@pytest.mark.parametrize(
    "content",
    [
        # Completely unrelated content.
        '{"action": "updated CHANGELOG"}',
        # ADR mentioned but no review evidence.
        '{"action": "read ADR-007 for context"}',
        # Partial word that should not match.
        '{"action": "reviewed a draught document"}',
        # Empty log.
        "{}",
        "",
    ],
)
def test_no_evidence_fails(tmp_path: Path, content: str) -> None:
    log = _write_session(tmp_path, content)
    result = policy._session_has_adr_review(log)
    assert result is False, (
        f"Expected _session_has_adr_review to return False for: {content!r}"
    )


# --- Edge cases ---

def _symlink_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink unavailable on this platform: {exc}")


def test_symlink_returns_false(tmp_path: Path) -> None:
    """Symlinks are unconditionally rejected to avoid following attacker-controlled paths."""
    target = tmp_path / "target.json"
    target.write_text('{"evidence": "/adr-review invoked"}', encoding="utf-8")
    link = tmp_path / "link.json"
    _symlink_or_skip(link, target)
    assert policy._session_has_adr_review(link) is False


def test_symlink_creation_error_skips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def raise_os_error(self: Path, target: Path) -> None:
        raise OSError("symlink denied")

    monkeypatch.setattr(Path, "symlink_to", raise_os_error)

    with pytest.raises(pytest.skip.Exception) as exc_info:
        _symlink_or_skip(tmp_path / "link.json", tmp_path / "target.json")

    assert "symlink unavailable on this platform" in str(exc_info.value)


def test_unreadable_file_returns_false(tmp_path: Path) -> None:
    """An unreadable file (OSError) must not raise; return False."""
    missing = tmp_path / "does_not_exist.json"
    assert policy._session_has_adr_review(missing) is False


def test_adr_word_boundary_not_matched_inside_word(tmp_path: Path) -> None:
    """'healthcare' does not contain 'adr' as a word boundary."""
    log = _write_session(tmp_path, '{"action": "updated healthcare policies"}')
    assert policy._session_has_adr_review(log) is False

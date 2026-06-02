"""Tests for the halt-block secret/PII redaction pre-emit rule in /spec.

Issue #1975, REQ-008 Sec F4 (CWE-209 information exposure through a diagnostic
message, CWE-532 sensitive data in a log).

Two layers, matching the issue acceptance criteria:

1. Static: the redaction pre-emit rule prose appears in the Step 0 (`answer`)
   and Step 0.5 (`evidence`) halt-block sections of `.claude/commands/spec.md`,
   and is mirrored into the Copilot CLI skill at
   `src/copilot-cli/skills/spec/SKILL.md`.
2. Behavioral: a halt block whose `answer`/`evidence` field carries a
   `Bearer <token>` (or other token shape) is rewritten so the secret becomes
   `[redacted: <reason>]` when run through the canonical redactor the spec
   wires in (`scripts/redact_secrets.py`).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SPEC_MD = PROJECT_ROOT / ".claude" / "commands" / "spec.md"
SKILL_MD = PROJECT_ROOT / "src" / "copilot-cli" / "skills" / "spec" / "SKILL.md"

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from redact_secrets import redact  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def spec_text() -> str:
    return SPEC_MD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def skill_text() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


def _section(text: str, start_marker: str, end_marker: str) -> str:
    """Return the slice of ``text`` from ``start_marker`` up to ``end_marker``.

    Used to scope an assertion to one halt-block section so a token present
    elsewhere in the file cannot make the test pass for the wrong reason.
    """
    start = text.find(start_marker)
    assert start != -1, f"missing section start marker: {start_marker!r}"
    end = text.find(end_marker, start)
    assert end != -1, f"missing section end marker: {end_marker!r}"
    return text[start:end]


# ---------------------------------------------------------------------------
# Static: redaction prose present in spec.md
# ---------------------------------------------------------------------------


def test_step0_halt_section_documents_redaction_pre_emit(spec_text: str) -> None:
    """AC: Step 0 halt section names the redaction pre-emit rule, the redactor,
    the policy file, and the CWE references, scoped to the Step 0 halt block."""
    section = _section(
        spec_text,
        "**Halt emission format**",
        "**Auto-mode behavior**",
    )
    assert "Redaction pre-emit" in section
    assert "scripts/redact_secrets.py" in section
    assert ".claude/rules/secret-redaction.md" in section
    assert "CWE-209" in section
    assert "CWE-532" in section


def test_step0_halt_redaction_targets_answer_field(spec_text: str) -> None:
    """AC: Step 0 redaction prose targets the `answer` field (the verbatim
    author text) and names the `[redacted: <reason>]` output placeholder."""
    section = _section(
        spec_text,
        "**Halt emission format**",
        "**Auto-mode behavior**",
    )
    assert "`answer`" in section
    assert "[redacted: <reason>]" in section


def test_step0_5_halt_section_documents_redaction_pre_emit(spec_text: str) -> None:
    """AC: Step 0.5 halt section names the redaction pre-emit rule for the
    `evidence` field, scoped to the Step 0.5 halt block format section."""
    section = _section(
        spec_text,
        "#### Step 0.5 halt block format",
        "#### Step 0.5 supplemental traversal hook",
    )
    assert "Redaction pre-emit" in section
    assert "`evidence`" in section
    assert "scripts/redact_secrets.py" in section
    assert "[redacted: <reason>]" in section
    assert "CWE-209" in section
    assert "CWE-532" in section


def test_halt_sections_note_durable_git_history(spec_text: str) -> None:
    """AC: both halt sections warn that the emitted block lands in git history
    (PR descriptions, session logs, tally) so the author does not paste live
    secrets. Each section carries its own warning."""
    step0 = _section(
        spec_text,
        "**Halt emission format**",
        "**Auto-mode behavior**",
    )
    step0_5 = _section(
        spec_text,
        "#### Step 0.5 halt block format",
        "#### Step 0.5 supplemental traversal hook",
    )
    assert "git history" in step0
    assert "git history" in step0_5


# ---------------------------------------------------------------------------
# Static: spec.md prose mirrored into the Copilot CLI SKILL.md
# ---------------------------------------------------------------------------


def test_skill_md_mirrors_step0_redaction(skill_text: str) -> None:
    """AC: the Copilot CLI mirror carries the Step 0 redaction pre-emit prose."""
    section = _section(
        skill_text,
        "**Halt emission format**",
        "**Auto-mode behavior**",
    )
    assert "Redaction pre-emit" in section
    assert "scripts/redact_secrets.py" in section


def test_skill_md_mirrors_step0_5_redaction(skill_text: str) -> None:
    """AC: the Copilot CLI mirror carries the Step 0.5 redaction pre-emit prose."""
    section = _section(
        skill_text,
        "#### Step 0.5 halt block format",
        "#### Step 0.5 supplemental traversal hook",
    )
    assert "Redaction pre-emit" in section
    assert "`evidence`" in section


def test_redaction_prose_byte_identical_between_spec_and_skill(
    spec_text: str, skill_text: str
) -> None:
    """AC-10 style: the Step 0.5 halt block section is byte-identical between
    spec.md and the generated SKILL.md, so the redaction rule cannot drift
    between the two surfaces."""
    spec_section = _section(
        spec_text,
        "#### Step 0.5 halt block format",
        "#### Step 0.5 supplemental traversal hook",
    )
    skill_section = _section(
        skill_text,
        "#### Step 0.5 halt block format",
        "#### Step 0.5 supplemental traversal hook",
    )
    assert spec_section == skill_section


# ---------------------------------------------------------------------------
# Behavioral: the redact-before-emit contract on a halt block
# ---------------------------------------------------------------------------


def _emit_halt_evidence(evidence: str) -> str:
    """Model the redact-before-emit step the spec wires in: the `evidence`
    (or `answer`) field is passed through the redactor before the block is
    written. Returns the value the spec would emit."""
    return redact(evidence).text


def test_bearer_token_in_evidence_is_redacted() -> None:
    """AC (behavioral): a halt block with a `Bearer <token>` in evidence emits
    `[redacted: ...]` rather than the live token."""
    raw = "Q3 paste: Alice blocked on Bearer abc123DEF456ghijkl+/= last Tuesday"
    emitted = _emit_halt_evidence(raw)
    assert "[redacted: bearer-token]" in emitted
    assert "abc123DEF456ghijkl" not in emitted


def test_email_and_hostname_paste_in_answer_is_redacted() -> None:
    """The issue's worked example: an author answer that names an email is
    redacted before emit. Single-label `Alice@corp` is matched (the safe
    over-redaction failure mode for untrusted free-text)."""
    raw = "users would want this; Alice@corp on prod-east-12.internal asked"
    emitted = _emit_halt_evidence(raw)
    assert "[redacted: email]" in emitted
    assert "Alice@corp" not in emitted


def test_clean_evidence_is_unchanged() -> None:
    """Negative: evidence with no secret shape passes through unmodified and
    emits no spurious placeholder."""
    raw = "3 unmatched entities marked blast-radius (entity-a, entity-b, entity-c)"
    emitted = _emit_halt_evidence(raw)
    assert emitted == raw
    assert "[redacted:" not in emitted


def test_only_the_secret_substring_is_replaced() -> None:
    """Edge: in a multi-token evidence string, only the matched token shape is
    replaced; the surrounding factual record (entity names, dates) survives so
    the halt stays diagnosable."""
    raw = "billing-service blocked; key sk_live_abcdef0123456789; re-run after fix"
    emitted = _emit_halt_evidence(raw)
    assert "[redacted: stripe-key]" in emitted
    assert "sk_live_abcdef0123456789" not in emitted
    assert "billing-service blocked" in emitted
    assert "re-run after fix" in emitted


def test_commit_sha_evidence_preserved_when_hex_disabled() -> None:
    """Edge: an evidence field whose contract is a git SHA (40 hex chars) must
    survive when the broad hex rule is disabled, per the redactor's SHA caveat.
    Redacting a real SHA would corrupt the record."""
    sha = "a" * 40
    raw = f"spec proposes reverting commit {sha}"
    emitted = redact(raw, include_hex=False).text
    assert sha in emitted
    assert "[redacted:" not in emitted

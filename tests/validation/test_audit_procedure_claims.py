"""Guard the qualitative membership guidance in the audit procedure."""

from __future__ import annotations

from tests.validation.always_on_corpus_helpers import REPO_ROOT

AUDIT_PROCEDURE = (
    REPO_ROOT
    / ".claude"
    / "skills"
    / "context-optimizer"
    / "references"
    / "rule-audit-procedure.md"
)


def test_audit_reads_generated_mirrors_for_membership() -> None:
    text = AUDIT_PROCEDURE.read_text(encoding="utf-8")
    assert "generated `.github/instructions/` mirrors" in text
    assert "canonical `.claude/rules/` files" in text
    assert "Parse their frontmatter" in text


def test_audit_does_not_publish_volatile_membership_measurements() -> None:
    text = AUDIT_PROCEDURE.read_text(encoding="utf-8")
    baseline = text.split("## Step 0b", 1)[0].lower()
    assert "bytes" not in baseline
    assert "instruction_budget" not in baseline
    assert "record the byte" not in text.lower()

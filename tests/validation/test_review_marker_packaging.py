"""Packaging tests for the review-marker validator."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_SCRIPT = REPO_ROOT / "scripts" / "validation" / "validate_review_marker.py"
SKILL_SCRIPT = REPO_ROOT / ".claude" / "skills" / "review" / "scripts" / "validate_review_marker.py"
COPILOT_SCRIPT = (
    REPO_ROOT / "src" / "copilot-cli" / "skills" / "review"
    / "scripts" / "validate_review_marker.py"
)
SHIP_COMMAND = REPO_ROOT / ".claude" / "skills" / "ship" / "SKILL.md"
COPILOT_SHIP_SKILL = REPO_ROOT / "src" / "copilot-cli" / "skills" / "ship" / "SKILL.md"
# ADR-064 (issue #5632) made ship a skill, so `references/` became available and
# the resolver moved there to clear an MD046 violation the old markdownlint
# exemption had been hiding. The contract is unchanged; it now spans two files,
# so "the ship docs" is the body plus its reference.
SHIP_REFERENCE = (
    REPO_ROOT / ".claude" / "skills" / "ship" / "references"
    / "review-marker-resolution.md"
)
COPILOT_SHIP_REFERENCE = (
    REPO_ROOT / "src" / "copilot-cli" / "skills" / "ship" / "references"
    / "review-marker-resolution.md"
)
SHIP_DOC_SETS = (
    (SHIP_COMMAND, SHIP_REFERENCE),
    (COPILOT_SHIP_SKILL, COPILOT_SHIP_REFERENCE),
)


def test_copilot_plugin_contains_review_validator() -> None:
    """Vendored plugin installs include the same validator under the review skill."""
    source_text = SOURCE_SCRIPT.read_text(encoding="utf-8")
    assert SKILL_SCRIPT.read_text(encoding="utf-8") == source_text
    assert COPILOT_SCRIPT.read_text(encoding="utf-8") == source_text


def test_ship_docs_use_review_skill_validator_paths() -> None:
    """Source and Copilot /ship docs point at plugin-shipped validator paths."""
    for paths in SHIP_DOC_SETS:
        for path in paths:
            assert path.is_file(), f"missing ship doc: {path}"
        text = "\n".join(p.read_text(encoding="utf-8") for p in paths)
        assert "review/scripts/validate_review_marker.py" in text
        # Canonical portable resolution: COPILOT_PLUGIN_ROOT primary,
        # CLAUDE_PLUGIN_ROOT fallback, .claude source-checkout default, in one
        # expression. Replaces the old per-variable branch lines (issue #2922).
        assert (
            "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}"
            "/skills/review/scripts/validate_review_marker.py" in text
        )
        assert '--repo-root "$(pwd)"' in text
        assert "git status --porcelain" in text
        assert "must not create a new commit after this check passes" in text
        assert "scripts/validation/validate_review_marker.py --ref HEAD" not in text


def test_review_marker_docs_use_repo_resolvable_references() -> None:
    """Shipped docs and scripts do not point at private memory identifiers."""
    private_ref = "decision-review-marker-sha-binding-mechanism"
    paths = [
        SOURCE_SCRIPT,
        SKILL_SCRIPT,
        COPILOT_SCRIPT,
        REPO_ROOT / ".claude" / "skills" / "review" / "SKILL.md",
        REPO_ROOT / "src" / "copilot-cli" / "skills" / "review" / "SKILL.md",
    ]
    for path in paths:
        assert private_ref not in path.read_text(encoding="utf-8")

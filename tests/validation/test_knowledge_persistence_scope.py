"""Pins the issue #5492 rescope of ``knowledge-persistence.md``.

Three properties are guarded here, because each one can regress silently:

a. ``.claude/rules/knowledge-persistence.md`` is scoped to the four trees it
   governs, never back to ``**``. A widened scope puts the file back in the
   always-on corpus without changing a single word of its prose, so no prose
   check would catch it.
b. The three discovery-time ``MUST NOT`` statements that moved out of it live
   in ``.claude/rules/universal.md``, with the evidence tails and commit SHAs
   that make them auditable. A later edit could drop one of those blocks and
   leave every existing count intact.
c. Both generated instruction mirrors carry the same relocated statements, so
   the move reached Copilot in this repository and in the shipped plugin.

The spec-coverage validator on PR #5497 named (b) and (c) as unguarded. This
module is that guard.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

KNOWLEDGE_PERSISTENCE = REPO_ROOT / ".claude/rules/knowledge-persistence.md"

EXPECTED_SCOPE = [
    ".claude/rules/**",
    ".serena/memories/**",
    ".github/instructions/**",
    "src/copilot-cli/instructions/**",
]

UNIVERSAL_TREES = [
    REPO_ROOT / ".claude/rules/universal.md",
    REPO_ROOT / ".github/instructions/universal.instructions.md",
    REPO_ROOT / "src/copilot-cli/instructions/universal.instructions.md",
]

# One distinguishing phrase per relocated statement. Each is specific enough
# that a paraphrase-and-lose-the-point edit fails the assertion.
RELOCATED_PHRASES = {
    "serena-alone": "retrieval complements, not the cross-harness binding",
    "operator-preference": "MUST NOT cite an operator preference as a repository rule",
    "single-probe": "MUST NOT assert an absence from a single probe",
}

# Evidence tails. These are the citations that let a reader check the claim.
RELOCATED_EVIDENCE = [
    "parallel/parallel-001-worktree-isolation.md",
    "memory/update_memory_index_tokens.py",
    "78e808238",
    "9cd7097f1",
]


def _frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path} has no YAML frontmatter"
    closing = text.index("\n---\n", 3)
    return yaml.safe_load(text[4:closing])


def test_knowledge_persistence_scope_is_the_four_governed_trees() -> None:
    assert _frontmatter(KNOWLEDGE_PERSISTENCE)["paths"] == EXPECTED_SCOPE


def test_knowledge_persistence_is_not_always_on() -> None:
    """Negative case: any universal glob re-admits the rule to every turn."""
    paths = _frontmatter(KNOWLEDGE_PERSISTENCE)["paths"]
    assert "**" not in paths
    assert "**/*" not in paths


def test_knowledge_persistence_points_at_the_relocated_items() -> None:
    text = KNOWLEDGE_PERSISTENCE.read_text(encoding="utf-8")
    assert ".claude/rules/universal.md" in text
    assert "items 7, 8, and 9" in text


@pytest.mark.parametrize("tree", UNIVERSAL_TREES, ids=lambda p: p.parts[-2])
@pytest.mark.parametrize("phrase", RELOCATED_PHRASES.values(), ids=RELOCATED_PHRASES.keys())
def test_relocated_statement_survives_in_every_universal_tree(tree: Path, phrase: str) -> None:
    assert phrase in tree.read_text(encoding="utf-8")


@pytest.mark.parametrize("tree", UNIVERSAL_TREES, ids=lambda p: p.parts[-2])
@pytest.mark.parametrize("citation", RELOCATED_EVIDENCE)
def test_relocated_evidence_survives_in_every_universal_tree(tree: Path, citation: str) -> None:
    """Edge case: the prose can survive while the citation that proves it is cut."""
    assert citation in tree.read_text(encoding="utf-8")

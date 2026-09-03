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

import re
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
    "opening-paragraph": "choose the persistence surface by who must obey it",
    "opening-harnesses": "invisible to the other two",
    "tier-1-ephemeral": "Ephemeral, this-task-only",
    "tier-2-retrieval": "Retrieval aid, non-binding",
    "tier-3-durable": "Durable convention that binds every contributor and every harness",
    "serena-alone": "retrieval complements, not the cross-harness binding",
    "operator-preference": "MUST NOT cite an operator preference as a repository rule",
    "single-probe": "MUST NOT assert an absence from a single probe",
}

# Evidence tails. These are the citations that let a reader check the claim.
RELOCATED_EVIDENCE = [
    "parallel/parallel-001-worktree-isolation.md",
    "scripts/memory/update_memory_index_tokens.py",
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
    """The pointer names the destination by title, never by tree-local path.

    Plugin consumers receive this file without `.claude/rules/universal.md`,
    so a path reference would send them to a file they do not have
    (`.claude/rules/plugin-self-containment.md`).
    """
    text = KNOWLEDGE_PERSISTENCE.read_text(encoding="utf-8")
    assert "the always-on Universal Rules" in text
    assert "items 7, 8, and 9" in text
    assert ".claude/rules/universal.md" not in text


@pytest.mark.parametrize("tree", UNIVERSAL_TREES, ids=lambda p: p.parts[-2])
@pytest.mark.parametrize("phrase", RELOCATED_PHRASES.values(), ids=RELOCATED_PHRASES.keys())
def test_relocated_statement_survives_in_every_universal_tree(tree: Path, phrase: str) -> None:
    assert phrase in tree.read_text(encoding="utf-8")


@pytest.mark.parametrize("tree", UNIVERSAL_TREES, ids=lambda p: p.parts[-2])
@pytest.mark.parametrize("citation", RELOCATED_EVIDENCE)
def test_relocated_evidence_survives_in_every_universal_tree(tree: Path, citation: str) -> None:
    """Edge case: the prose can survive while the citation that proves it is cut."""
    assert citation in tree.read_text(encoding="utf-8")


# Live surfaces: prose a session actually loads and obeys. Historical trees
# under `.agents/` are deliberately excluded. Those documents cite the number
# an item carried when they were written, with a "when written" parenthetical,
# and rewriting them to the current number would falsify the record they exist
# to keep.
LIVE_PROSE_ROOTS = [
    REPO_ROOT / ".claude" / "rules",
    REPO_ROOT / ".claude" / "skills",
    REPO_ROOT / ".github" / "instructions",
    REPO_ROOT / "src" / "copilot-cli" / "instructions",
    REPO_ROOT / "src" / "copilot-cli" / "skills",
]

# `knowledge-persistence.md` keeps exactly one MUST NOT item after the
# relocation. Any live citation of items 2 and up is a dangling pointer into
# a list that no longer has that many entries.
_STALE_MUST_NOT = re.compile(
    r"knowledge-persistence(?:\.md)?[^.\n]{0,40}?MUST[- ]NOT[- ]?(\d+)",
    re.IGNORECASE,
)

SURVIVING_MUST_NOT_COUNT = 1


def _live_markdown_files() -> list[Path]:
    files: list[Path] = []
    for root in LIVE_PROSE_ROOTS:
        if root.is_dir():
            files.extend(sorted(root.rglob("*.md")))
    return files


def test_surviving_must_not_list_has_the_expected_length() -> None:
    """Anchor the count the staleness scan below depends on.

    If a future change adds a MUST NOT item back, this fails first and names
    the reason, instead of the scan silently permitting a wider number range.
    """
    text = KNOWLEDGE_PERSISTENCE.read_text(encoding="utf-8")
    section = text.split("## MUST NOT", 1)[1].split("## References", 1)[0]
    items = re.findall(r"^\d+\. ", section, re.MULTILINE)
    assert len(items) == SURVIVING_MUST_NOT_COUNT


def test_no_live_prose_cites_a_relocated_must_not_number() -> None:
    """Repo-wide: no loaded instruction points at a MUST NOT that moved.

    Criterion 3 of issue #5492. A citation left at its old number does not
    fail loudly; it silently sends a reader to a different rule than the one
    the author meant, which is worse than a broken link.
    """
    offenders: list[str] = []
    for path in _live_markdown_files():
        for line_no, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            for match in _STALE_MUST_NOT.finditer(line):
                if int(match.group(1)) > SURVIVING_MUST_NOT_COUNT:
                    rel = path.relative_to(REPO_ROOT)
                    offenders.append(f"{rel}:{line_no}: {match.group(0)}")
    assert not offenders, "stale knowledge-persistence MUST NOT citations: " + "; ".join(
        offenders
    )


def test_the_staleness_scan_can_actually_fail() -> None:
    """Negative control: the regex matches the shape it is meant to catch.

    Without this, a regex that never matches anything would leave the test
    above vacuously green forever.
    """
    sample = "see `.claude/rules/knowledge-persistence.md` MUST NOT 4 for the bar"
    match = _STALE_MUST_NOT.search(sample)
    assert match is not None
    assert int(match.group(1)) > SURVIVING_MUST_NOT_COUNT

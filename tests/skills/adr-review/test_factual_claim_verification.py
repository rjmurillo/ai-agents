"""Every adr-review seat must verify factual claims against primary sources.

Issue #5297: PR #5283 shipped four unverified supporting-prose claims (a
deciders line, a status claim, an implementing PR number, a cross-artifact
contract) through a six-seat debate, because no seat prompt told seats to check
prose that is not framed as the decision. The contract below pins the shared
verification block, its Phase 1 and Phase 4 hooks, and the protocol steps, in
the source tree and in both rendered trees.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
TREES = (
    "src/claude/skills/adr-review",
    ".claude/skills/adr-review",
    "src/copilot-cli/skills/adr-review",
)
BLOCK_HEADING = "## Factual Claim Verification Block"
CLAIM_KINDS = (
    "Deciders, approvers, authors",
    "Issue or PR number",
    '"Implemented", "never implemented", "superseded"',
    "Count, path, `path:line`",
    "Cross-artifact contract",
)
RESULTS = ("VERIFIED", "REFUTED", "UNVERIFIED")


def _read(tree: str, name: str) -> str:
    return (REPO_ROOT / tree / "references" / name).read_text(encoding="utf-8")


def _block(tree: str) -> str:
    text = _read(tree, "agent-prompts.md")
    start = text.index(BLOCK_HEADING)
    end = text.index("## Phase 1: Independent Review Prompts", start)
    return text[start:end]


@pytest.mark.parametrize("tree", TREES)
def test_block_precedes_phase_1_prompts(tree: str) -> None:
    text = _read(tree, "agent-prompts.md")
    assert text.index(BLOCK_HEADING) < text.index("## Phase 1: Independent Review Prompts")


@pytest.mark.parametrize("tree", TREES)
def test_block_covers_every_claim_kind_from_the_issue(tree: str) -> None:
    block = _block(tree)
    for kind in CLAIM_KINDS:
        assert kind in block, kind


@pytest.mark.parametrize("tree", TREES)
def test_block_applies_to_all_seats_and_supporting_prose(tree: str) -> None:
    block = _block(tree)
    assert "every seat" in block
    assert "Supporting\nprose gets the same bar as the claim framed as the decision" in block
    assert "Claims outside it are still\n   yours to check" in block
    assert "build one before you review" in block


@pytest.mark.parametrize("tree", TREES)
def test_block_defines_result_states_and_output_table(tree: str) -> None:
    block = _block(tree)
    for result in RESULTS:
        assert result in block, result
    assert "### Claims Checked" in block
    assert "Never mark a claim `VERIFIED` from memory" in block
    assert "A `REFUTED` claim is a blocking concern" in block


@pytest.mark.parametrize("tree", TREES)
def test_convergence_prompt_checks_claims_added_this_round(tree: str) -> None:
    text = _read(tree, "agent-prompts.md")
    phase4 = text[text.index("## Phase 4: Convergence Check Prompts") :]
    assert "## Factual Claim Verification" in phase4
    assert "added or\nchanged this round" in phase4
    assert "Claims Checked table" in phase4


@pytest.mark.parametrize("tree", TREES)
def test_toc_lists_the_block(tree: str) -> None:
    text = _read(tree, "agent-prompts.md")
    assert "[Factual Claim Verification Block](#factual-claim-verification-block)" in text


@pytest.mark.parametrize("tree", TREES)
def test_protocol_phase_1_requires_verification_without_ledger(tree: str) -> None:
    text = _read(tree, "debate-protocol.md")
    phase1 = text[text.index("## Phase 1: Independent Review") : text.index("## Phase 2")]
    assert "When no ledger exists, each\nseat builds one" in phase1
    assert "Every seat verifies factual claims, not only the analyst" in phase1
    assert "### Claims Checked" in phase1
    assert "6. Verify every factual claim in the ADR against its primary source" in phase1
    assert "Check claims the ledger omits" in phase1
    assert "7. Return structured review per Phase 1 format" in phase1


@pytest.mark.parametrize("tree", TREES)
def test_protocol_phase_4_checks_changed_text(tree: str) -> None:
    text = _read(tree, "debate-protocol.md")
    phase4 = text[text.index("## Phase 4: Convergence Check") : text.index("## Round Management")]
    assert "Verify every factual claim in text added or changed this round" in phase4
    assert "A fix round can add a wrong claim" in phase4

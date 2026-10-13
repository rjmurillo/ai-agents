"""Pin the corrected ADR-109 claims in docs that once described a retired model.

Drive-by fix for defect D43. After ADR-109 B1 to B5 the agent, rule, skill,
hook, and settings trees under src/claude/ and .claude/ are generated, not
hand-maintained. Five documents kept the old wording. Each case names a phrase
that was wrong at origin/main 8d182f241 and must stay out of the file.

Tests:
- Negative: each retired phrase is absent from its file.
- Positive: each file still carries the corrected anchor phrase.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

RETIRED = {
    "templates/rules/templates.md": (
        "are hand-maintained",
        "no shipped agent template defines it",
        "over an 18-section allowlist",
        "`python3 build/scripts/detect_agent_drift.py`",
    ),
    "templates/rules/plugin-self-containment.md": (
        "### Agent files are not scanned at all",
        "Issue #3465 tracks widening the ratchet",
        "It also scans three extra roots",
        "What sits outside is everything else, such as the rendered agent files",
        "Neither are the rendered",
        "ships into `src/copilot-cli/` unchecked",
        "and no gate objects.",
    ),
    "build/scripts/check_agent_content_parity.py": (
        "two hand-maintained copies",
        "hand-maintained siblings",
    ),
    ".agents/governance/FAIL-OPEN-INVENTORY.md": (
        "`checks_dash.py:94-136`",
        "1 of 2 markdown file(s) checked",
        "`agent-drift-detection.yml:138`",
        "`agent-drift-detection.yml:150`",
        "`agent-drift-detection.yml:156`",
        "Check plugin manifest parity |",
    ),
    ".serena/memories/unicode-dash-guard-scope-gap.md": ("`_branch_markdown_files`",),
}

ANCHORS = {
    "templates/rules/templates.md": "agent_templates.py",
    "templates/rules/plugin-self-containment.md": "### Agent files are scanned in part",
    "build/scripts/check_agent_content_parity.py": "binplace",
    ".agents/governance/FAIL-OPEN-INVENTORY.md": "Check plugin manifest parity and description",
    ".serena/memories/unicode-dash-guard-scope-gap.md": "`_branch_scan_files`",
}

CASES = [(path, phrase) for path, phrases in RETIRED.items() for phrase in phrases]


def _read(relpath: str) -> str:
    return (REPO_ROOT / relpath).read_text(encoding="utf-8")


@pytest.mark.parametrize(("relpath", "phrase"), CASES)
def test_retired_phrase_is_absent(relpath: str, phrase: str) -> None:
    assert phrase not in _read(relpath), f"{relpath} still says {phrase!r}"


@pytest.mark.parametrize("relpath", sorted(ANCHORS))
def test_corrected_anchor_is_present(relpath: str) -> None:
    assert ANCHORS[relpath] in _read(relpath)


SCAN_ROOT_ANCHORS = (
    "It also scans the six `EXTRA_SCAN_ROOTS`",
    "`src/claude/agents`, `src/copilot-cli/agents`, and `.github/agents`",
    "`REQUIRED_EXTRA_ROOTS`",
    "`UPSTREAM_PATTERNS`",
)


@pytest.mark.parametrize("anchor", SCAN_ROOT_ANCHORS)
def test_scan_root_claims_match_the_validator(anchor: str) -> None:
    assert anchor in _read("templates/rules/plugin-self-containment.md")


def test_rule_names_every_extra_scan_root_the_validator_scans() -> None:
    """Every EXTRA_SCAN_ROOTS entry the rule claims is scanned must exist in the validator."""
    validator = _read("scripts/validation/check_skill_md_portability.py")
    for root in ("src/claude/agents", "src/copilot-cli/agents", ".github/agents"):
        assert f'"{root}"' in validator

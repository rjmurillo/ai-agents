"""Retrospectives list findings for the owner and never file issues or backlog memory (#5703)."""

from __future__ import annotations

import importlib.util
import sys
from hashlib import sha1
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

AGENT_SURFACES = (
    "templates/agents/retrospective.shared.md",
    "templates/agents/partials/retrospective-integration-with-skillbook.mustache",
    ".claude/agents/retrospective.md",
    "src/claude/agents/retrospective.md",
    ".github/agents/retrospective.agent.md",
    "src/copilot-cli/agents/retrospective.agent.md",
    "src/vs-code-agents/retrospective.agent.md",
)
# The partial is a fragment; learning persistence lives in sibling partials.
AGENT_FILES = tuple(rel for rel in AGENT_SURFACES if not rel.endswith(".mustache"))
# Only the Claude template carries the mandatory structured handoff block.
CLAUDE_AGENT_FILES = (
    "templates/agents/retrospective.claude.md.tmpl",
    ".claude/agents/retrospective.md",
    "src/claude/agents/retrospective.md",
)
SKILL_TREES = (
    ".claude/skills/retrospective",
    "src/claude/skills/retrospective",
    "src/copilot-cli/skills/retrospective",
)
SKILL_FILES = (
    "SKILL.md",
    "references/diagnosis-and-actions.md",
    "references/frameworks.md",
    "references/learning-template.md",
    "scripts/run_retrospective.py",
)
SKILL_SURFACES = ("templates/skills/retrospective.SKILL.md.tmpl",) + tuple(
    f"{tree}/{name}" for tree in SKILL_TREES for name in SKILL_FILES
)
# Surfaces that carry the Delta Triage activity prose, not only the artifact skeleton.
TRIAGE_PROSE_SURFACES = AGENT_SURFACES + tuple(
    f"{tree}/references/frameworks.md" for tree in SKILL_TREES
)
ARTIFACT_SURFACES = tuple(f"{tree}/references/learning-template.md" for tree in SKILL_TREES)

FORBIDDEN_ROUTING = (
    "new_issue.py",
    "Create GitHub issue immediately",
    "gh issue create",
    "issue_write",
    "Issues Created",
    "Backlog Items Stored",
    "Backlog Candidates",
    "Store in backlog memory",
    "backlog/retro-",
    "source:retrospective",
    "P0/P1 Issue Creation",
    "P2/P3 Backlog Memory Storage",
)
CLASSES = ("Blocker", "Requested improvement", "Optional enhancement", "Side quest")
FINDINGS_HEADER = "| Item | Evidence (path:line) | Proposed action | Class |"
CLASS_PLACEHOLDER = "[" + " / ".join(CLASSES) + "]"
BLOCKER_RULE = (
    "A Blocker stays blocking; recording it here does not permit declaring the work complete."
)
OPTIONAL_RULE = "It does not reopen completed work."
EMPTY_RULE = "An empty table is valid."
OWNER_DECIDES = "The owner reads the table and decides what becomes an issue."
BLOCKER_BEFORE_FILTER = (
    "Check for a Blocker before filtering. If evidence falsifies a frozen acceptance "
    "criterion or mandatory policy, keep it as a Blocker."
)
LEARNING_PERSISTENCE_ANCHORS = ("### Memory Storage Pattern", "## Memory Protocol")

SCRIPT = ROOT / ".claude/skills/retrospective/scripts/run_retrospective.py"
MODULE_NAME = f"retrospective_owner_findings_{sha1(str(SCRIPT).encode()).hexdigest()[:12]}"


def _load_renderer():
    spec = importlib.util.spec_from_file_location(MODULE_NAME, SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _forbidden_hits(text: str) -> list[str]:
    return [needle for needle in FORBIDDEN_ROUTING if needle in text]


def _findings_rows(text: str, heading: str) -> list[list[str]]:
    """Return the body rows of the findings table under ``heading``."""
    section = text.split(heading, maxsplit=1)[1].lstrip("\n")
    lines = section.splitlines()
    if lines[0] != FINDINGS_HEADER:
        raise ValueError(f"findings table header drifted: {lines[0]!r}")
    rows: list[list[str]] = []
    for line in lines[2:]:
        if not line.startswith("|"):
            break
        rows.append([cell.strip() for cell in line.strip("|").split("|")])
    return rows


@pytest.mark.parametrize("rel", AGENT_SURFACES + SKILL_SURFACES)
def test_no_issue_or_backlog_routing(rel: str) -> None:
    assert _forbidden_hits(_read(rel)) == []


@pytest.mark.parametrize("rel", TRIAGE_PROSE_SURFACES)
def test_triage_prose_emits_owner_table_with_four_classes(rel: str) -> None:
    text = _read(rel)
    prose = " ".join(text.split())
    triage = text.split("### Activity: Delta Triage", maxsplit=1)[1]
    triage = triage.split("### Activity: ROTI", maxsplit=1)[0]
    assert triage.count("### Findings for the owner") == 1
    assert FINDINGS_HEADER in text
    assert CLASS_PLACEHOLDER in text
    for cls in CLASSES:
        assert f"**{cls}**" in text
    assert BLOCKER_RULE in prose
    assert prose.count(OPTIONAL_RULE) == 2
    assert EMPTY_RULE in prose
    assert OWNER_DECIDES in prose
    assert BLOCKER_BEFORE_FILTER in prose.replace("**", "")
    assert prose.index("Check for a Blocker before filtering") < prose.index("drop items")


@pytest.mark.parametrize("rel", AGENT_FILES)
def test_agent_surfaces_keep_learning_persistence(rel: str) -> None:
    text = _read(rel)
    for anchor in LEARNING_PERSISTENCE_ANCHORS:
        assert anchor in text
    storage = text.split("### Memory Storage Pattern", maxsplit=1)[1]
    storage = storage.split("### Failure Prevention Matrix", maxsplit=1)[0]
    assert "mcp__serena__write_memory" in storage
    assert "backlog/" not in storage
    handoff = " ".join(text.split("## Handoff Protocol", maxsplit=1)[1].split())
    assert "the `Findings for the owner` table (Blocker rows first) to orchestrator" in handoff


@pytest.mark.parametrize("rel", CLAUDE_AGENT_FILES)
def test_structured_handoff_carries_owner_findings(rel: str) -> None:
    text = _read(rel)
    template = text.split("## Retrospective Handoff", maxsplit=2)[1]
    template = template.split("### Handoff Output Rules", maxsplit=1)[0]
    findings = template.split("### Findings for the owner", maxsplit=1)[1]
    assert findings.lstrip("\n").startswith(FINDINGS_HEADER)
    assert CLASS_PLACEHOLDER in findings
    assert "**Blockers for the owner**" in template
    prose = " ".join(text.split())
    assert "Copy the artifact's table, Blocker rows first. An empty table is valid." in prose


@pytest.mark.parametrize("rel", ARTIFACT_SURFACES)
def test_artifact_template_has_one_owner_table(rel: str) -> None:
    text = _read(rel)
    assert text.count("#### Findings for the owner") == 1
    rows = _findings_rows(text, "#### Findings for the owner")
    assert len(rows) == 1
    assert rows[0][3] == CLASS_PLACEHOLDER


@pytest.mark.parametrize("tree", SKILL_TREES)
def test_skill_phase_5_points_at_owner_table(tree: str) -> None:
    text = _read(f"{tree}/SKILL.md")
    assert "Persist learnings with atomicity at or above 70 percent" in text
    assert "`Findings for the owner` table" in text
    assert "The owner decides what becomes tracked work." in text
    assert "it lists delta items for the owner in the artifact" in text


def _rendered_artifact() -> str:
    module = _load_renderer()

    class _Evidence:
        work_items: list[str] = []
        outcomes: list[str] = []
        commits: list[str] = []
        notes: list[str] = []
        session_log_available = True

    artifact, _ = module.render_artifact("owner-findings", "2026-09-28", _Evidence(), [])
    return artifact


def test_rendered_artifact_has_no_routing() -> None:
    assert _forbidden_hits(_rendered_artifact()) == []


def test_empty_findings_table_is_valid() -> None:
    artifact = _rendered_artifact()
    placeholder = (
        "| [Delta item] | [path:line] | [Smallest action that resolves it] | "
        f"{CLASS_PLACEHOLDER} |\n"
    )
    assert placeholder in artifact
    empty = artifact.replace(placeholder, "", 1)
    assert _findings_rows(empty, "#### Findings for the owner") == []


# Parser and scanner self-tests: negative controls for the helpers above, not product coverage.


def test_drifted_header_is_rejected() -> None:
    table = "#### Findings for the owner\n\n| Item | Priority | Destination |\n"
    with pytest.raises(ValueError, match="header drifted"):
        _findings_rows(table, "#### Findings for the owner")


def test_forbidden_scan_catches_reintroduced_routing() -> None:
    reintroduced = "Run new_issue.py and store in backlog/retro-2026-09-28-items.md"
    assert _forbidden_hits(reintroduced) == ["new_issue.py", "backlog/retro-"]

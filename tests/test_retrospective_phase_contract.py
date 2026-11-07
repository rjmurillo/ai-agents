"""Contract tests between the retrospective process, template, and renderer."""

from __future__ import annotations

import importlib.util
import re
import sys
from dataclasses import dataclass, field
from hashlib import sha1
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".claude" / "skills" / "retrospective" / "SKILL.md"
TEMPLATE = ROOT / ".claude" / "skills" / "retrospective" / "references" / "learning-template.md"
SCRIPT = ROOT / ".claude" / "skills" / "retrospective" / "scripts" / "run_retrospective.py"
COPILOT_TEMPLATE = (
    ROOT
    / "src"
    / "copilot-cli"
    / "skills"
    / "retrospective"
    / "references"
    / "learning-template.md"
)
COPILOT_SCRIPT = (
    ROOT / "src" / "copilot-cli" / "skills" / "retrospective" / "scripts" / "run_retrospective.py"
)
MODULE_NAME = f"retrospective_phase_contract_{sha1(str(SCRIPT).encode()).hexdigest()[:12]}"
PHASE_5_SECTIONS = (
    "### Memory Persistence",
    "### +/Delta",
    "### Delta Triage",
    "### ROTI Assessment",
    "### Helped, Hindered, Hypothesis",
)
DELTA_TRIAGE_CONTRACT = (
    "#### Actionable Items Identified",
    "| Delta Item | Category |",
    "#### Findings for the owner",
    "| Item | Evidence (path:line) | Proposed action | Class |",
)
REMOVED_DELTA_ROUTING = (
    "Issues Created",
    "Backlog Items Stored",
    "Skipped Items",
    "backlog/retro-",
    "source:retrospective",
)
MEMORY_RESULT_OPTIONS = "[Added / Updated / Deduplicated / Skipped / Failed]"

SPEC = importlib.util.spec_from_file_location(MODULE_NAME, SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise ImportError(f"Unable to load retrospective renderer from {SCRIPT}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[MODULE_NAME] = MODULE
SPEC.loader.exec_module(MODULE)


@dataclass
class Evidence:
    work_items: list[str] = field(default_factory=list)
    outcomes: list[str] = field(default_factory=list)
    commits: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    session_log_available: bool = True


def _process_phase_numbers(text: str) -> set[int]:
    process = text.split("## Process", maxsplit=1)[1].split("\n---", maxsplit=1)[0]
    return {int(number) for number in re.findall(r"^### Phase (\d+):", process, re.M)}


def _template_phase_numbers(text: str) -> set[int]:
    return {int(number) for number in re.findall(r"^## Phase (\d+):", text, re.M)}


def _missing_process_phases(skill_text: str, artifact_text: str) -> set[int]:
    return _process_phase_numbers(skill_text) - _template_phase_numbers(artifact_text)


def _phase_5_block(text: str) -> str:
    marker = "## Phase 5: Persist and Close"
    remainder = text.split(marker, maxsplit=1)[1].split("\n````", maxsplit=1)[0]
    return f"{marker}{remainder}".strip()


def test_template_and_renderer_cover_every_process_phase() -> None:
    skill_text = SKILL.read_text(encoding="utf-8")
    template_text = TEMPLATE.read_text(encoding="utf-8")
    artifact, _ = MODULE.render_artifact(
        "phase-contract",
        "2026-08-12",
        Evidence(),
        [],
    )
    assert _missing_process_phases(skill_text, template_text) == set()
    assert _missing_process_phases(skill_text, artifact) == set()
    template_phase_5 = _phase_5_block(template_text)
    assert _phase_5_block(artifact) == template_phase_5
    for section in PHASE_5_SECTIONS:
        assert section in template_phase_5
    assert MEMORY_RESULT_OPTIONS in template_phase_5
    for contract_line in DELTA_TRIAGE_CONTRACT:
        assert contract_line in template_phase_5
    for removed in REMOVED_DELTA_ROUTING:
        assert removed not in template_phase_5


def test_copilot_cli_files_match_canonical_sources() -> None:
    assert COPILOT_TEMPLATE.read_bytes() == TEMPLATE.read_bytes()
    assert COPILOT_SCRIPT.read_bytes() == SCRIPT.read_bytes()


def test_phase_contract_reports_a_missing_template_phase() -> None:
    skill_text = SKILL.read_text(encoding="utf-8")
    template_text = TEMPLATE.read_text(encoding="utf-8")
    incomplete_template = template_text.replace(
        "## Phase 5: Persist and Close",
        "## Persist and Close",
        1,
    )

    assert _missing_process_phases(skill_text, incomplete_template) == {5}


def test_phase_contract_does_not_confuse_phase_50_with_phase_5() -> None:
    skill_text = SKILL.read_text(encoding="utf-8")
    template_text = TEMPLATE.read_text(encoding="utf-8")
    mistyped_template = template_text.replace(
        "## Phase 5: Persist and Close",
        "## Phase 50: Persist and Close",
        1,
    )

    assert _missing_process_phases(skill_text, mistyped_template) == {5}


RECURSIVE = ROOT / ".claude" / "skills" / "retrospective" / "references" / "recursive-extraction.md"
AGENT_SURFACES = (
    "templates/agents/retrospective.shared.md",
    "src/claude/agents/retrospective.md",
    "src/copilot-cli/agents/retrospective.agent.md",
    "src/vs-code-agents/retrospective.agent.md",
)
RECURSIVE_HEADING = "#### Recursive Learning Extraction"
ASSEMBLY_RULE = (
    "Record the Phase 5 result as the `#### Recursive Learning Extraction` block from "
    "`recursive-extraction.md`, the last block under `### Memory Persistence`."
)


def _fenced_block(text: str, after: str) -> str:
    """Return the ````markdown block that follows the first occurrence of ``after``."""
    tail = text.split(after, maxsplit=1)[1]
    body = tail.split("````markdown\n", maxsplit=1)[1]
    return body.split("\n````", maxsplit=1)[0]


def _assemble_artifact() -> str:
    """Apply the agent's documented assembly rule to the template and the Phase 5 block."""
    skeleton = _fenced_block(TEMPLATE.read_text(encoding="utf-8"), "# Learning Extraction Template")
    recursive = _fenced_block(
        RECURSIVE.read_text(encoding="utf-8"), "## Documentation Requirements"
    )
    head, tail = skeleton.split("\n### +/Delta\n", maxsplit=1)
    return f"{head.rstrip()}\n\n{recursive.strip()}\n\n### +/Delta\n{tail}"


def _headings(text: str, level: int) -> list[str]:
    prefix = "#" * level + " "
    return [line for line in text.splitlines() if line.startswith(prefix)]


def test_assembled_artifact_has_each_phase_heading_exactly_once() -> None:
    headings = _headings(_assemble_artifact(), 2)
    for number in range(6):
        matching = [h for h in headings if h.startswith(f"## Phase {number}:")]
        assert len(matching) == 1, (number, matching)
    assert not [h for h in headings if h.startswith("## Phase 6")]
    assert len([h for h in headings if h.startswith("## Phase ")]) == 6


def test_assembled_artifact_nests_recursive_block_under_phase_5() -> None:
    artifact = _assemble_artifact()
    assert artifact.count(RECURSIVE_HEADING) == 1
    phase_5 = artifact.split("## Phase 5: Persist and Close", maxsplit=1)[1]
    assert RECURSIVE_HEADING in phase_5
    assert phase_5.index("### Memory Persistence") < phase_5.index(RECURSIVE_HEADING)
    assert phase_5.index(RECURSIVE_HEADING) < phase_5.index("### +/Delta")


def test_recursive_block_cannot_add_a_phase_heading() -> None:
    block = _fenced_block(RECURSIVE.read_text(encoding="utf-8"), "## Documentation Requirements")
    assert not [h for h in _headings(block, 2) if h.startswith("## Phase")]


def test_duplicate_phase_heading_is_detected() -> None:
    # Negative control: the old shape (a second Phase 5 heading) must fail the check.
    broken = _assemble_artifact().replace(
        RECURSIVE_HEADING, "## Phase 5: Recursive Learning Extraction"
    )
    matching = [h for h in _headings(broken, 2) if h.startswith("## Phase 5:")]
    assert len(matching) == 2


def test_agent_surfaces_carry_the_one_artifact_shape() -> None:
    for rel in AGENT_SURFACES:
        prose = " ".join((ROOT / rel).read_text(encoding="utf-8").split())
        assert ASSEMBLY_RULE in prose, rel
        assert "there is no Phase 6 heading in the artifact" in prose, rel
        assert "byte for byte" not in prose, rel

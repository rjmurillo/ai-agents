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
    "| Delta Item | Category | Priority | Destination | Reference |",
    "#### Issues Created",
    "| Issue | Title | Priority | Labels |",
    "#### Backlog Items Stored",
    "| Item | Priority | Memory File |",
    "#### Skipped Items",
    "| Item | Reason |",
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

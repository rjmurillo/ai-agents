"""Pin the QA reviewer-asymmetry and completeness contracts."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "build" / "scripts" / "detect_agent_drift.py"
QA_CLAUDE = REPO_ROOT / ".claude" / "agents" / "qa.md"
QA_COPILOT = REPO_ROOT / ".github" / "agents" / "qa.agent.md"
QA_SURFACES = [
    REPO_ROOT / "templates" / "agents" / "qa.shared.md",
    QA_CLAUDE,
    QA_COPILOT,
    REPO_ROOT / "src" / "claude" / "qa.md",
    REPO_ROOT / "src" / "copilot-cli" / "agents" / "qa.agent.md",
    REPO_ROOT / "src" / "vs-code-agents" / "qa.agent.md",
]
PARTIAL_DELIVERY_FIXTURE = REPO_ROOT / "evals" / "qa-spike" / "fixtures" / "Q011.json"

SPEC = importlib.util.spec_from_file_location("qa_contract_drift", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
drift = importlib.util.module_from_spec(SPEC)
sys.modules["qa_contract_drift"] = drift
SPEC.loader.exec_module(drift)

REQUIRED_SECTIONS = {
    "Reviewer Asymmetry (Read First)",
    "Completeness Verification (Mandatory)",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _remove_section(content: str, heading: str) -> str:
    pattern = re.compile(
        rf"^## {re.escape(heading)}\n.*?(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    mutated, count = pattern.subn("", content)
    assert count == 1
    return mutated


def _compare(copilot_content: str):
    return drift.compare_agent(
        _read(QA_CLAUDE),
        copilot_content,
        "qa",
        80,
        drift._INSTALL_COMPARISON_LABEL,
    )


def test_qa_install_pair_compares_required_contracts() -> None:
    result = _compare(_read(QA_COPILOT))

    compared_sections = {section.section for section in result.sections}
    assert REQUIRED_SECTIONS <= compared_sections
    assert result.status == "OK"


@pytest.mark.parametrize("heading", sorted(REQUIRED_SECTIONS))
def test_qa_required_contract_omission_fails_drift_gate(heading: str) -> None:
    result = _compare(_remove_section(_read(QA_COPILOT), heading))

    assert result.status == "DRIFT DETECTED"
    assert heading in result.drifting_sections


@pytest.mark.parametrize("surface", QA_SURFACES)
def test_qa_partial_delivery_fixture_requires_fail(surface: Path) -> None:
    fixture = json.loads(PARTIAL_DELIVERY_FIXTURE.read_text(encoding="utf-8"))
    counts = [int(value) for value in re.findall(r"\b(?:16|49)\b", fixture["input"])]
    sections = drift.get_markdown_sections(drift.remove_yaml_frontmatter(_read(surface)))
    completeness = sections["Completeness Verification (Mandatory)"]

    assert min(counts) < max(counts)
    assert "validation = FAIL regardless" in completeness
    assert "Promised:" in completeness
    assert "Delivered:" in completeness
    assert "Gap:" in completeness
    assert "Cannot verify completeness without requirements" in completeness

"""Regression guard: the backlog-generator agent stays retired (issue #5701).

The agent filed GitHub issues when agent slots were idle, which is the
manufactured-work pattern epic #5698 removes. It shipped as a template family
under templates/agents/ plus rendered bodies in five trees. build_all.py does
not delete an orphaned rendered body when its template disappears, so a
retirement can be half done and still render cleanly. These tests read the
committed trees, so a surviving body, a routing row, a labeler block, or a
metrics or eval reference fails here.

Each inventory assertion also checks that surviving agents are present, so an
empty or mis-pointed inventory cannot pass vacuously.

Historical records are deliberately not scanned: evals/ (the preserved
backlog-generator-spike and baseline results), .project-toolkit/, and .agents/.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
THIS_FILE = Path(__file__).resolve()

RETIRED = "backlog-generator"
_RETIRED_PATTERN = re.compile(r"backlog[-_ ]?generator", re.IGNORECASE)

# tree name -> (directory, suffix that follows the agent name)
AGENT_TREES: dict[str, tuple[Path, str]] = {
    "template": (REPO_ROOT / "templates" / "agents", ".shared.md"),
    "claude-install": (REPO_ROOT / ".claude" / "agents", ".md"),
    "github-install": (REPO_ROOT / ".github" / "agents", ".agent.md"),
    "src-claude": (REPO_ROOT / "src" / "claude" / "agents", ".md"),
    "copilot-cli": (REPO_ROOT / "src" / "copilot-cli" / "agents", ".agent.md"),
    "vscode": (REPO_ROOT / "src" / "vs-code-agents", ".agent.md"),
}

ORCHESTRATOR_FILES = {
    "template": REPO_ROOT / "templates" / "agents" / "orchestrator.shared.md",
    "partial": REPO_ROOT
    / "templates"
    / "agents"
    / "partials"
    / "orchestrator-core-behavior.mustache",
    "claude-install": REPO_ROOT / ".claude" / "agents" / "orchestrator.md",
    "github-install": REPO_ROOT / ".github" / "agents" / "orchestrator.agent.md",
    "src-claude": REPO_ROOT / "src" / "claude" / "agents" / "orchestrator.md",
    "copilot-cli": REPO_ROOT / "src" / "copilot-cli" / "agents" / "orchestrator.agent.md",
    "vscode": REPO_ROOT / "src" / "vs-code-agents" / "orchestrator.agent.md",
}

# Surviving agents that every tree must still ship.
SURVIVORS = ("analyst", "critic", "orchestrator", "task-decomposer")

# Active surfaces. Historical records (evals/, .project-toolkit/, .agents/) are
# excluded on purpose.
SCAN_ROOTS = (
    "templates",
    "src",
    ".claude",
    ".github",
    "build",
    "scripts",
    "docs",
    "tests",
)
SCAN_FILES = ("README.md", "CONTRIBUTING.md")
_SKIP_DIRS = {"__pycache__", "node_modules", ".git", ".pytest_cache", ".ruff_cache"}
_MAX_BYTES = 2_000_000

_MATRIX_ROW = re.compile(r"^\| \*\*(?P<agent>[^*]+)\*\* \|", re.MULTILINE)


def _agent_names(tree: str) -> set[str]:
    directory, suffix = AGENT_TREES[tree]
    names: set[str] = set()
    for path in directory.iterdir():
        if not path.is_file() or not path.name.endswith(suffix):
            continue
        if tree in ("claude-install", "src-claude") and path.name in {
            "AGENTS.md",
            "CLAUDE.md",
        }:
            continue
        names.add(path.name[: -len(suffix)])
    return names


def _scan_targets() -> list[Path]:
    targets: list[Path] = []
    for root in SCAN_ROOTS:
        base = REPO_ROOT / root
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if any(part in _SKIP_DIRS for part in path.parts):
                continue
            if path.resolve() == THIS_FILE or not path.is_file():
                continue
            targets.append(path)
    targets.extend(REPO_ROOT / name for name in SCAN_FILES)
    return targets


@pytest.mark.parametrize("tree", AGENT_TREES)
def test_no_agent_body_in_any_tree(tree: str) -> None:
    """No tree ships a backlog-generator body; survivors are still present."""
    names = _agent_names(tree)

    assert set(SURVIVORS) <= names, f"{tree}: inventory is missing survivors ({len(names)} found)"
    assert RETIRED not in names, f"{tree} still ships {RETIRED}"


@pytest.mark.parametrize("tree", [t for t in AGENT_TREES if t != "template"])
def test_rendered_tree_has_no_orphan_without_a_template(tree: str) -> None:
    """A rendered body whose template is gone is the leftover this retirement risked."""
    template_names = _agent_names("template")
    orphans = _agent_names(tree) - template_names

    assert template_names, "template inventory is empty"
    assert not orphans, f"{tree} ships agents with no template: {sorted(orphans)}"


def test_no_template_part_survives() -> None:
    """Templates, partials, and fixtures carry no backlog-generator file."""
    roots = (
        REPO_ROOT / "templates",
        REPO_ROOT / "tests" / "build_scripts" / "fixtures",
    )
    examined = 0
    leftovers: list[str] = []
    for root in roots:
        for path in root.rglob("*"):
            if path.is_file():
                examined += 1
                if _RETIRED_PATTERN.search(path.name):
                    leftovers.append(str(path.relative_to(REPO_ROOT)))

    assert examined > 100, f"only {examined} files examined"
    assert not leftovers, f"retired agent files remain: {leftovers}"


@pytest.mark.parametrize("surface", ORCHESTRATOR_FILES)
def test_orchestrator_routing_has_no_row_for_the_retired_agent(surface: str) -> None:
    """Every orchestrator copy routes to survivors only."""
    text = ORCHESTRATOR_FILES[surface].read_text(encoding="utf-8")
    routed = {m.group("agent") for m in _MATRIX_ROW.finditer(text)}

    assert set(SURVIVORS) - {"orchestrator"} <= routed, f"{surface}: routing rows not parsed"
    assert RETIRED not in routed, f"{surface} still routes to {RETIRED}"


def test_labeler_has_no_block_or_glob_for_the_retired_agent() -> None:
    """Parsed .github/labeler.yml: no label key and no glob names the agent."""
    data = yaml.safe_load((REPO_ROOT / ".github" / "labeler.yml").read_text(encoding="utf-8"))

    assert "agent-critic" in data, "labeler.yml did not parse to the expected labels"
    assert not [key for key in data if _RETIRED_PATTERN.search(key)]
    assert not _RETIRED_PATTERN.search(json.dumps(data))


def test_discriminator_baseline_has_no_entry_for_the_retired_agent() -> None:
    """The skill-shape ratchet baseline records no score for a deleted agent."""
    path = REPO_ROOT / "scripts" / "validation" / "agent_skill_discriminator_baseline.json"
    files = json.loads(path.read_text(encoding="utf-8"))["files"]

    assert ".claude/agents/analyst.md" in files, "baseline did not load"
    assert not [name for name in files if _RETIRED_PATTERN.search(name)]


def test_no_active_surface_references_the_retired_agent() -> None:
    """Whole-tree sweep of active surfaces (see SCAN_ROOTS) for any reference."""
    targets = _scan_targets()
    hits: list[str] = []
    examined = 0
    for path in targets:
        try:
            if path.stat().st_size > _MAX_BYTES:
                continue
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        examined += 1
        if _RETIRED_PATTERN.search(path.as_posix()) or _RETIRED_PATTERN.search(text):
            hits.append(str(path.relative_to(REPO_ROOT)))

    assert examined > 1000, f"only {examined} files examined"
    assert not hits, f"active surfaces still reference {RETIRED}: {hits}"


def test_recorded_eval_history_is_preserved_and_annotated() -> None:
    """Retirement removes the agent, not its recorded results (issue #5701 review)."""
    spike = REPO_ROOT / "evals" / "backlog-generator-spike"
    report = (REPO_ROOT / "evals" / "baseline-report.md").read_text(encoding="utf-8")

    assert len(list((spike / "fixtures").glob("B*.json"))) == 8
    assert any((spike / "reports").rglob("REPORT.md"))
    assert any((spike / "runs").rglob("runs.jsonl"))
    assert "| backlog-generator | 8 | 0.750 | 0.833 | -0.083 |" in report
    assert "Retirement note (issue #5701" in report

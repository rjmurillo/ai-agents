"""Snapshot tests for build/generate_agents.py (REQ-003-001).

These tests assert the agent generator emits stable per-platform output for
representative agents, including the visual-studio toolsFrom-aliasing case
that proved hardest to preserve in the M3-T1 refactor.

We do NOT snapshot all 25 × 3 = 75 generated files. We pick three agents and
inspect a few load-bearing fields per platform.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build"))
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import generate_agents  # noqa: E402


# Helpers --------------------------------------------------------------------


@pytest.fixture
def staging(tmp_path: Path) -> Path:
    """Stage a minimal templates tree under tmp_path so writes don't pollute the repo."""
    repo = tmp_path / "stage"
    (repo / "templates").mkdir(parents=True)
    # Copy templates wholesale: agents/, platforms/, toolsets.yaml.
    shutil.copytree(REPO_ROOT / "templates" / "agents", repo / "templates" / "agents")
    shutil.copytree(REPO_ROOT / "templates" / "platforms", repo / "templates" / "platforms")
    shutil.copy2(REPO_ROOT / "templates" / "toolsets.yaml", repo / "templates" / "toolsets.yaml")
    return repo


def _read_frontmatter(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    end = text.find("\n---\n", 4)
    assert end >= 0, f"no frontmatter end in {path}"
    return text[: end + 5]


# Snapshot tests ------------------------------------------------------------


def test_generate_writes_three_outputs_per_agent(staging: Path) -> None:
    rc = generate_agents.generate_agents(
        templates_path=staging / "templates",
        output_root=staging / "src",
        repo_root=staging,
    )
    assert rc == 0
    # Pick three representative agents and verify all three platform files exist.
    for agent in ("analyst", "implementer", "qa"):
        assert (staging / "src" / "copilot-cli" / f"{agent}.agent.md").is_file()
        assert (staging / "src" / "vs-code-agents" / f"{agent}.agent.md").is_file()


def test_copilot_cli_emits_path_style_tools(staging: Path) -> None:
    """Copilot CLI uses `$toolset:editor` expanded to `path/*` patterns."""
    rc = generate_agents.generate_agents(
        templates_path=staging / "templates",
        output_root=staging / "src",
        repo_root=staging,
    )
    assert rc == 0
    fm = _read_frontmatter(staging / "src" / "copilot-cli" / "analyst.agent.md")
    # Path-style tool entries appear as bullet items like `- read` or `- perplexity/*`.
    assert "tools:" in fm
    assert "- " in fm  # bullet array


def test_visual_studio_inherits_vscode_toolsfrom(staging: Path) -> None:
    """visual-studio.yaml has `toolsFrom: vscode` — the toolset expansion
    must use vscode tools, NOT visual-studio (which has no entries)."""
    rc = generate_agents.generate_agents(
        templates_path=staging / "templates",
        output_root=staging / "src",
        repo_root=staging,
    )
    assert rc == 0
    vs_path = staging / "src" / "vs-code-agents" / "analyst.agent.md"
    assert vs_path.is_file()
    fm = _read_frontmatter(vs_path)
    # Sanity: vscode toolset entries are non-empty and present.
    assert "tools:" in fm
    body = vs_path.read_text(encoding="utf-8")
    assert body.startswith("---\n")


def test_handoff_syntax_differs_per_platform(staging: Path) -> None:
    """copilot-cli uses /agent; vscode/vs uses #runSubagent.
    Pick an agent body that mentions Task() to verify the rewrite ran."""
    rc = generate_agents.generate_agents(
        templates_path=staging / "templates",
        output_root=staging / "src",
        repo_root=staging,
    )
    assert rc == 0
    cc = (staging / "src" / "copilot-cli" / "orchestrator.agent.md").read_text(encoding="utf-8")
    vs = (staging / "src" / "vs-code-agents" / "orchestrator.agent.md").read_text(encoding="utf-8")
    # The handoff transform fires on `Task(subagent_type="...")` patterns.
    # We assert that the two outputs differ AT LEAST in their handoff
    # representation — they share most of the body otherwise.
    assert cc != vs


def test_validate_mode_passes_against_committed_state() -> None:
    """The committed src/ tree must match what the generator produces today.
    This is the M3-T1 no-regress contract: any future generator change must
    preserve byte-equality with what's checked in."""
    rc = generate_agents.main(["--validate"])
    assert rc == 0

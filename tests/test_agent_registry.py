"""Tests for agent registry parser and validator.

Covers:
- Frontmatter parsing from agent markdown files
- Validation: required fields, model values, duplicates
- Integration: real src/claude/ files
"""

from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest

from scripts.validation.agent_registry import (
    AgentDefinition,
    ValidationResult,
    parse_agent_file,
    parse_agent_files,
    validate,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = REPO_ROOT / "src" / "claude"


@pytest.fixture()
def tmp_agent_dir(tmp_path: Path) -> Path:
    """Create a temporary directory with sample agent files."""
    agent_dir = tmp_path / "agents"
    agent_dir.mkdir()
    return agent_dir


def _write_agent(directory: Path, filename: str, content: str) -> Path:
    p = directory / filename
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Unit: parse_agent_file
# ---------------------------------------------------------------------------


class TestParseAgentFile:
    def test_valid_agent(self, tmp_agent_dir: Path) -> None:
        path = _write_agent(
            tmp_agent_dir,
            "tester.md",
            """\
            ---
            name: tester
            description: Runs tests
            model: sonnet
            argument-hint: Describe what to test
            ---
            # Tester Agent
            Body content here.
            """,
        )
        agent = parse_agent_file(path)
        assert agent is not None
        assert agent.name == "tester"
        assert agent.description == "Runs tests"
        assert agent.model == "sonnet"
        assert agent.argument_hint == "Describe what to test"
        assert agent.file_path == path

    def test_missing_frontmatter(self, tmp_agent_dir: Path) -> None:
        path = _write_agent(
            tmp_agent_dir,
            "no_fm.md",
            """\
            # No frontmatter here
            Just body content.
            """,
        )
        assert parse_agent_file(path) is None

    def test_missing_name(self, tmp_agent_dir: Path) -> None:
        path = _write_agent(
            tmp_agent_dir,
            "no_name.md",
            """\
            ---
            description: Agent without a name
            model: sonnet
            ---
            # Nameless
            """,
        )
        assert parse_agent_file(path) is None

    def test_optional_argument_hint(self, tmp_agent_dir: Path) -> None:
        path = _write_agent(
            tmp_agent_dir,
            "minimal.md",
            """\
            ---
            name: minimal
            description: Minimal agent
            model: haiku
            ---
            # Minimal
            """,
        )
        agent = parse_agent_file(path)
        assert agent is not None
        assert agent.argument_hint == ""


# ---------------------------------------------------------------------------
# Unit: parse_agent_files
# ---------------------------------------------------------------------------


class TestParseAgentFiles:
    def test_skips_excluded_files(self, tmp_agent_dir: Path) -> None:
        _write_agent(
            tmp_agent_dir,
            "AGENTS.md",
            """\
            ---
            name: should-skip
            description: Not an agent
            model: sonnet
            ---
            """,
        )
        _write_agent(
            tmp_agent_dir,
            "claude-instructions.template.md",
            """\
            ---
            name: template
            description: Not an agent
            model: sonnet
            ---
            """,
        )
        _write_agent(
            tmp_agent_dir,
            "real-agent.md",
            """\
            ---
            name: real-agent
            description: A real agent
            model: sonnet
            ---
            """,
        )
        agents, errors = parse_agent_files(tmp_agent_dir)
        assert errors == []
        names = [a.name for a in agents]
        assert "real-agent" in names
        assert "should-skip" not in names
        assert "template" not in names

    @pytest.mark.skipif(
        os.geteuid() == 0,
        reason="chmod-based permission denial is a no-op for root (web containers)",
    )
    def test_unreadable_file_collected_as_error(self, tmp_agent_dir: Path) -> None:
        _write_agent(
            tmp_agent_dir,
            "good.md",
            "---\nname: good\ndescription: Good agent\nmodel: sonnet\n---\n",
        )
        bad = tmp_agent_dir / "bad.md"
        bad.write_text("---\nname: bad\n---\n", encoding="utf-8")
        bad.chmod(0o000)
        agents, errors = parse_agent_files(tmp_agent_dir)
        bad.chmod(0o644)  # restore for cleanup
        assert len(agents) == 1
        assert agents[0].name == "good"
        assert len(errors) == 1
        assert "bad.md" in errors[0]

    def test_sorted_output(self, tmp_agent_dir: Path) -> None:
        for name in ["zebra", "alpha", "middle"]:
            _write_agent(
                tmp_agent_dir,
                f"{name}.md",
                f"---\nname: {name}\ndescription: Agent {name}\nmodel: sonnet\n---\n",
            )
        agents, errors = parse_agent_files(tmp_agent_dir)
        assert errors == []
        names = [a.name for a in agents]
        assert names == ["alpha", "middle", "zebra"]


# ---------------------------------------------------------------------------
# Unit: validate
# ---------------------------------------------------------------------------


class TestValidate:
    def test_valid_agents(self) -> None:
        agents = [
            AgentDefinition("a1", "Desc", "sonnet", "hint", Path("a1.md")),
        ]
        result = validate(agents)
        assert result.ok
        assert result.errors == []

    def test_invalid_model(self) -> None:
        agents = [
            AgentDefinition("a1", "Desc", "gpt4", "hint", Path("a1.md")),
        ]
        result = validate(agents)
        assert not result.ok
        assert any("invalid model 'gpt4'" in e for e in result.errors)

    def test_missing_required_field(self) -> None:
        agents = [
            AgentDefinition("a1", "", "sonnet", "", Path("a1.md")),
        ]
        result = validate(agents)
        assert not result.ok
        assert any("missing required field 'description'" in e for e in result.errors)

    def test_duplicate_agent_names(self) -> None:
        agents = [
            AgentDefinition("a1", "Desc1", "sonnet", "", Path("a1.md")),
            AgentDefinition("a1", "Desc2", "sonnet", "", Path("a1_copy.md")),
        ]
        result = validate(agents)
        assert not result.ok
        assert any("Duplicate agent name 'a1'" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Integration: real files
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not AGENT_DIR.is_dir(), reason="src/claude/ not found")
class TestIntegration:
    def test_parse_real_agents(self) -> None:
        agents, _errors = parse_agent_files(AGENT_DIR)
        assert len(agents) >= 15, f"Expected at least 15 agents, got {len(agents)}"
        names = {a.name for a in agents}
        assert "orchestrator" in names
        assert "analyst" in names
        assert "implementer" in names

    def test_validate_real_agents_runs_without_crash(self) -> None:
        """Verify validation completes and returns structured results."""
        agents, _errors = parse_agent_files(AGENT_DIR)
        result = validate(agents)
        assert isinstance(result, ValidationResult)
        assert isinstance(result.errors, list)
        assert isinstance(result.warnings, list)

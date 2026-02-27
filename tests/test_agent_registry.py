"""Tests for agent registry parser and validator.

Covers:
- Frontmatter parsing from agent markdown files
- Catalog table extraction from AGENTS.md
- Validation: required fields, model values, model mismatches, duplicates
- Integration: real src/claude/ files against real AGENTS.md
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from scripts.validation.agent_registry import (
    AgentDefinition,
    CatalogEntry,
    ValidationResult,
    parse_agent_file,
    parse_agent_files,
    parse_catalog,
    validate,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = REPO_ROOT / "src" / "claude"
AGENTS_MD = REPO_ROOT / "AGENTS.md"


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
# Unit: parse_catalog
# ---------------------------------------------------------------------------


class TestParseCatalog:
    def test_extracts_agents_from_table(self, tmp_path: Path) -> None:
        catalog_path = tmp_path / "AGENTS.md"
        catalog_path.write_text(
            textwrap.dedent("""\
            # AGENTS.md

            ## Agent Catalog

            | Agent | Purpose | Model |
            |-------|---------|-------|
            | orchestrator | Task coordination | opus |
            | analyst | Research | sonnet |
            | memory | Context retrieval | haiku |

            Some other content.
            """),
            encoding="utf-8",
        )
        entries = parse_catalog(catalog_path)
        assert len(entries) == 3
        by_name = {e.name: e.model for e in entries}
        assert by_name["orchestrator"] == "opus"
        assert by_name["analyst"] == "sonnet"
        assert by_name["memory"] == "haiku"

    def test_ignores_non_table_lines(self, tmp_path: Path) -> None:
        catalog_path = tmp_path / "AGENTS.md"
        catalog_path.write_text(
            "# No table here\nJust text.\n",
            encoding="utf-8",
        )
        entries = parse_catalog(catalog_path)
        assert entries == []


# ---------------------------------------------------------------------------
# Unit: validate
# ---------------------------------------------------------------------------


class TestValidate:
    def test_valid_agents(self) -> None:
        agents = [
            AgentDefinition("a1", "Desc", "sonnet", "hint", Path("a1.md")),
        ]
        catalog = [CatalogEntry("a1", "sonnet")]
        result = validate(agents, catalog)
        assert result.ok
        assert result.errors == []

    def test_model_mismatch(self) -> None:
        agents = [
            AgentDefinition("a1", "Desc", "haiku", "hint", Path("a1.md")),
        ]
        catalog = [CatalogEntry("a1", "opus")]
        result = validate(agents, catalog)
        assert not result.ok
        assert any("model 'haiku' does not match catalog 'opus'" in e for e in result.errors)

    def test_invalid_model(self) -> None:
        agents = [
            AgentDefinition("a1", "Desc", "gpt4", "hint", Path("a1.md")),
        ]
        catalog = [CatalogEntry("a1", "sonnet")]
        result = validate(agents, catalog)
        assert not result.ok
        assert any("invalid model 'gpt4'" in e for e in result.errors)

    def test_missing_required_field(self) -> None:
        agents = [
            AgentDefinition("a1", "", "sonnet", "", Path("a1.md")),
        ]
        catalog = [CatalogEntry("a1", "sonnet")]
        result = validate(agents, catalog)
        assert not result.ok
        assert any("missing required field 'description'" in e for e in result.errors)

    def test_duplicate_agent_names(self) -> None:
        agents = [
            AgentDefinition("a1", "Desc1", "sonnet", "", Path("a1.md")),
            AgentDefinition("a1", "Desc2", "sonnet", "", Path("a1_copy.md")),
        ]
        catalog = [CatalogEntry("a1", "sonnet")]
        result = validate(agents, catalog)
        assert not result.ok
        assert any("Duplicate agent name 'a1'" in e for e in result.errors)

    def test_missing_from_catalog_warns(self) -> None:
        agents: list[AgentDefinition] = []
        catalog = [CatalogEntry("missing-agent", "sonnet")]
        result = validate(agents, catalog)
        assert result.ok  # Warnings do not fail
        assert any("missing-agent" in w for w in result.warnings)

    def test_extra_agent_warns(self) -> None:
        agents = [
            AgentDefinition("extra", "Desc", "sonnet", "", Path("extra.md")),
        ]
        catalog: list[CatalogEntry] = []
        result = validate(agents, catalog)
        assert result.ok  # Warnings do not fail
        assert any("extra" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Integration: real files
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not AGENT_DIR.is_dir(), reason="src/claude/ not found")
@pytest.mark.skipif(not AGENTS_MD.is_file(), reason="AGENTS.md not found")
class TestIntegration:
    def test_parse_real_agents(self) -> None:
        agents, _errors = parse_agent_files(AGENT_DIR)
        assert len(agents) >= 15, f"Expected at least 15 agents, got {len(agents)}"
        names = {a.name for a in agents}
        assert "orchestrator" in names
        assert "analyst" in names
        assert "implementer" in names

    def test_parse_real_catalog(self) -> None:
        catalog = parse_catalog(AGENTS_MD)
        assert len(catalog) >= 15, f"Expected at least 15 catalog entries, got {len(catalog)}"
        names = {e.name for e in catalog}
        assert "orchestrator" in names

    def test_validate_real_agents_runs_without_crash(self) -> None:
        """Verify validation completes and returns structured results.

        Does not assert zero errors because pre-existing model drift
        between agent files and AGENTS.md is a known condition.
        The validator correctly detects this drift.
        """
        agents, _errors = parse_agent_files(AGENT_DIR)
        catalog = parse_catalog(AGENTS_MD)
        result = validate(agents, catalog)
        assert isinstance(result, ValidationResult)
        assert isinstance(result.errors, list)
        assert isinstance(result.warnings, list)

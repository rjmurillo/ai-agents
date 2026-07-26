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
    MalformedAgentFileError,
    ValidationResult,
    main,
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
        with pytest.raises(MalformedAgentFileError, match="no YAML frontmatter"):
            parse_agent_file(path)

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
        with pytest.raises(MalformedAgentFileError, match="frontmatter has no name"):
            parse_agent_file(path)

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
        getattr(os, "geteuid", lambda: -1)() == 0,
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


class TestAMalformedFileFailsInsteadOfDisappearing:
    """PR #3361 review: this validator is wired into CI as a guard.

    A file that lost its frontmatter used to be dropped from the registry,
    which left validate() with nothing to complain about and the CI step
    exiting 0. The guard was blind to the one failure it exists to catch.
    """

    def test_a_file_without_frontmatter_is_reported_not_skipped(self, tmp_agent_dir: Path) -> None:
        _write_agent(tmp_agent_dir, "broken.md", "# Lost its frontmatter\n")
        agents, errors = parse_agent_files(tmp_agent_dir)
        assert agents == []
        assert any("broken.md" in e and "no YAML frontmatter" in e for e in errors)

    def test_a_file_without_a_name_is_reported_not_skipped(self, tmp_agent_dir: Path) -> None:
        _write_agent(
            tmp_agent_dir,
            "nameless.md",
            """\
            ---
            description: Has everything but a name
            model: sonnet
            ---
            """,
        )
        agents, errors = parse_agent_files(tmp_agent_dir)
        assert agents == []
        assert any("nameless.md" in e and "no name" in e for e in errors)

    def test_the_cli_exits_nonzero_on_a_malformed_file(self, tmp_agent_dir: Path) -> None:
        """The behavior CI depends on: a broken agent turns the step red."""
        _write_agent(
            tmp_agent_dir,
            "good.md",
            """\
            ---
            name: good
            description: A well formed agent
            model: sonnet
            ---
            """,
        )
        _write_agent(tmp_agent_dir, "broken.md", "# Lost its frontmatter\n")
        assert main(["--agent-dir", str(tmp_agent_dir)]) != 0

    def test_the_cli_exits_zero_when_every_file_is_well_formed(self, tmp_agent_dir: Path) -> None:
        """The negative control: the nonzero above is about the broken file."""
        _write_agent(
            tmp_agent_dir,
            "good.md",
            """\
            ---
            name: good
            description: A well formed agent
            model: sonnet
            ---
            """,
        )
        assert main(["--agent-dir", str(tmp_agent_dir)]) == 0

    def test_excluded_files_are_still_skipped_without_an_error(self, tmp_agent_dir: Path) -> None:
        """AGENTS.md has no frontmatter by design and must stay quiet."""
        _write_agent(tmp_agent_dir, "AGENTS.md", "# Directory notes, not an agent\n")
        agents, errors = parse_agent_files(tmp_agent_dir)
        assert agents == []
        assert errors == []


class TestAnUnreadableFileFailsCleanly:
    """A traceback is not a validation result; CI cannot act on it."""

    def test_non_utf8_bytes_raise_the_registry_error(self, tmp_path: Path) -> None:
        bad = tmp_path / "broken.md"
        bad.write_bytes(b"---\nname: x\n---\n\xff\xfe not utf-8\n")
        with pytest.raises(MalformedAgentFileError, match="not valid UTF-8"):
            parse_agent_file(bad)

    def test_non_utf8_bytes_are_reported_not_raised_by_the_directory_walk(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "good.md").write_text(
            "---\nname: good\ndescription: d\n---\n", encoding="utf-8"
        )
        (tmp_path / "bad.md").write_bytes(b"---\nname: x\n---\n\xff\xfe\n")
        agents, errors = parse_agent_files(tmp_path)
        assert [a.name for a in agents] == ["good"]
        assert any("not valid UTF-8" in e for e in errors)

    def test_the_error_names_the_offending_file(self, tmp_path: Path) -> None:
        bad = tmp_path / "culprit.md"
        bad.write_bytes(b"---\nname: x\n---\n\xff\n")
        with pytest.raises(MalformedAgentFileError, match="culprit.md"):
            parse_agent_file(bad)

    def test_a_directory_in_place_of_a_file_reports_rather_than_crashes(
        self, tmp_path: Path
    ) -> None:
        """OSError takes the same path; the walk must not die on one bad entry."""
        (tmp_path / "notafile.md").mkdir()
        agents, errors = parse_agent_files(tmp_path)
        assert agents == []
        assert any("notafile.md" in e for e in errors)

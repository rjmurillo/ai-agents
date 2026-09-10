"""Tests for agent registry parser and validator.

Covers:
- Frontmatter parsing from agent markdown files
- Validation: required fields, model values, duplicates
- Integration: real src/claude/ files
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from scripts.validation.agent_registry import (
    AgentDefinition,
    MalformedAgentFileError,
    ValidationResult,
    _build_utility_path,
    _load_read_yaml_frontmatter,
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

    @pytest.mark.parametrize(
        "name_field",
        ["", 'name: "   "\n'],
        ids=["missing", "blank"],
    )
    def test_missing_or_blank_name(self, tmp_agent_dir: Path, name_field: str) -> None:
        path = _write_agent(
            tmp_agent_dir,
            "invalid_name.md",
            f"---\n{name_field}description: Agent without a usable name\nmodel: sonnet\n---\n",
        )
        with pytest.raises(MalformedAgentFileError, match="frontmatter has no name"):
            parse_agent_file(path)

    @pytest.mark.parametrize(
        ("frontmatter", "message"),
        [
            (
                "name: broken\ndescription: invalid: plain scalar\nmodel: sonnet",
                "invalid YAML frontmatter",
            ),
            (
                "name: first\nname: second\ndescription: duplicate\nmodel: sonnet",
                "duplicate frontmatter key 'name'",
            ),
            # A YAML complex key (a sequence or mapping used as a key) makes
            # key_node.value a list, which the duplicate-key set cannot hash.
            # _parse_frontmatter rejects non-scalar key nodes before it builds
            # that set. Both shapes are covered: a reader who sees only the
            # sequence case would not know the mapping case is handled too.
            (
                "? [a, b]\n: value\nname: seqkey\n",
                "frontmatter keys must be scalar values",
            ),
            (
                "? {a: 1}\n: value\nname: mapkey\n",
                "frontmatter keys must be scalar values",
            ),
        ],
        ids=["invalid-yaml", "duplicate-key", "sequence-key", "mapping-key"],
    )
    def test_malformed_yaml_is_rejected(
        self,
        tmp_agent_dir: Path,
        frontmatter: str,
        message: str,
    ) -> None:
        path = _write_agent(
            tmp_agent_dir,
            "malformed.md",
            f"---\n{frontmatter}\n---\n",
        )
        with pytest.raises(MalformedAgentFileError, match=message):
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

    def test_invalid_utf8_bytes_fail_cli(
        self,
        tmp_agent_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        bad = tmp_agent_dir / "corrupt.md"
        bad.write_bytes(b"---\nname: corrupt\n---\n\xff\xfe invalid utf-8")

        assert main(["--agent-dir", str(tmp_agent_dir)]) == 1
        assert "corrupt.md: cannot decode as UTF-8" in capsys.readouterr().out


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

    def test_unpinned_agent_is_valid(self) -> None:
        """ADR-080: no model line is the correct default, not a missing field."""
        agents = [
            AgentDefinition("a1", "Desc", "", "hint", Path("a1.md")),
        ]
        result = validate(agents)
        assert result.ok
        assert result.errors == []

    def test_unpinned_agent_parses_and_validates_from_disk(
        self, tmp_agent_dir: Path
    ) -> None:
        """An agent file with no model: line reaches validate() and passes."""
        unpinned = tmp_agent_dir / "unpinned.md"
        unpinned.write_text(
            "---\nname: unpinned\ndescription: Inherits the harness model\n---\n",
            encoding="utf-8",
        )

        agent = parse_agent_file(unpinned)

        assert agent.model == ""
        assert validate([agent]).ok

    def test_cost_justified_alias_is_valid(self) -> None:
        """ADR-080 rule 3 keeps the cheap-tier alias legal, so haiku must pass."""
        agents = [
            AgentDefinition("a1", "Desc", "haiku", "hint", Path("a1.md")),
        ]
        result = validate(agents)
        assert result.ok

    def test_versioned_pin_is_rejected(self) -> None:
        """A versioned id is not a rolling alias, so the value check rejects it."""
        agents = [
            AgentDefinition("a1", "Desc", "claude-opus-4-6", "hint", Path("a1.md")),
        ]
        result = validate(agents)
        assert not result.ok
        assert any("invalid model 'claude-opus-4-6'" in e for e in result.errors)

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
    def test_import_does_not_mutate_sys_path(self) -> None:
        code = textwrap.dedent(
            """\
            import sys

            before = sys.path.copy()
            import scripts.validation.agent_registry
            raise SystemExit(sys.path != before)
            """
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=REPO_ROOT,
            check=False,
        )
        assert result.returncode == 0

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
        assert main(["--agent-dir", str(tmp_agent_dir)]) == 1


class TestBuildUtilityLoaderNamesTheFailure:
    """The import-time loader must say which build utility it could not load.

    This code runs at module import, so a bare FileNotFoundError or SyntaxError
    from inside importlib leaves a CI reader with no hint that a *validation*
    script died because a *build* utility was unloadable.
    """

    def test_a_missing_build_utility_is_reported_as_an_import_error(self, tmp_path: Path) -> None:
        """spec_from_file_location succeeds for a missing path; exec_module is the guard."""
        missing = tmp_path / "generate_agents_common.py"
        with pytest.raises(ImportError) as excinfo:
            _load_read_yaml_frontmatter(missing)
        assert str(missing) in str(excinfo.value)

    def test_a_broken_build_utility_is_reported_as_an_import_error(self, tmp_path: Path) -> None:
        """A SyntaxError inside the utility must not escape as a SyntaxError."""
        broken = tmp_path / "generate_agents_common.py"
        broken.write_text("def (\n", encoding="utf-8")
        with pytest.raises(ImportError) as excinfo:
            _load_read_yaml_frontmatter(broken)
        assert str(broken) in str(excinfo.value)

    def test_a_utility_missing_the_symbol_is_reported_as_an_import_error(
        self, tmp_path: Path
    ) -> None:
        """Importing cleanly is not enough; the symbol has to be there."""
        empty = tmp_path / "generate_agents_common.py"
        empty.write_text("# no read_yaml_frontmatter here\n", encoding="utf-8")
        with pytest.raises(ImportError) as excinfo:
            _load_read_yaml_frontmatter(empty)
        assert "read_yaml_frontmatter" in str(excinfo.value)

    def test_the_default_path_points_at_the_real_build_utility(self) -> None:
        """The production default must resolve to a file that actually loads."""
        assert _build_utility_path().is_file()
        assert callable(_load_read_yaml_frontmatter())

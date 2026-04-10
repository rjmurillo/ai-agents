"""Tests for the OpenClaw bridge export script."""

from __future__ import annotations

import json
import textwrap

import pytest

from scripts.openclaw_bridge import (
    AgentDefinition,
    ExportResult,
    export_agents,
    export_json,
    generate_agents_md,
    generate_skill_md,
    load_agents,
    main,
    parse_agent_file,
    write_workspace,
)


@pytest.fixture
def sample_agent():
    return AgentDefinition(
        name="analyst",
        description="Research specialist who digs deep into root causes.",
        model="sonnet",
        tier="integration",
        argument_hint="Describe the topic to research",
        body="# Analyst Agent\n\nCore identity text.",
        source_path="src/claude/analyst.md",
    )


@pytest.fixture
def sample_agents():
    return [
        AgentDefinition(
            name="orchestrator",
            description="Enterprise task orchestrator for multi-step coordination.",
            model="opus",
            tier="manager",
            argument_hint="Describe the task to solve end-to-end",
        ),
        AgentDefinition(
            name="implementer",
            description="Execution-focused engineering expert.",
            model="opus",
            tier="builder",
            argument_hint="Specify the plan file path",
        ),
        AgentDefinition(
            name="analyst",
            description="Research specialist.",
            model="sonnet",
            tier="integration",
        ),
    ]


@pytest.fixture
def agent_md_file(tmp_path):
    content = textwrap.dedent("""\
        ---
        name: test-agent
        description: A test agent for unit testing.
        model: sonnet
        tier: builder
        argument-hint: Provide the test scenario
        ---
        # Test Agent

        This is the agent body.
    """)
    md_file = tmp_path / "test-agent.md"
    md_file.write_text(content, encoding="utf-8")
    return md_file


@pytest.fixture
def agents_dir(tmp_path):
    """Create a directory with multiple agent files."""
    agents = tmp_path / "agents"
    agents.mkdir()

    for name, model, tier in [
        ("orchestrator", "opus", "manager"),
        ("implementer", "opus", "builder"),
        ("analyst", "sonnet", "integration"),
    ]:
        content = textwrap.dedent(f"""\
            ---
            name: {name}
            description: The {name} agent.
            model: {model}
            tier: {tier}
            argument-hint: Use {name}
            ---
            # {name.title()} Agent
        """)
        (agents / f"{name}.md").write_text(content, encoding="utf-8")

    # Add files that should be skipped
    (agents / "AGENTS.md").write_text("# Skip me", encoding="utf-8")
    (agents / "claude-instructions.template.md").write_text("# Skip me too", encoding="utf-8")

    return agents


class TestParseAgentFile:
    def test_parses_valid_file(self, agent_md_file):
        result = parse_agent_file(agent_md_file)
        assert result is not None
        assert result.name == "test-agent"
        assert result.description == "A test agent for unit testing."
        assert result.model == "sonnet"
        assert result.tier == "builder"
        assert result.argument_hint == "Provide the test scenario"
        assert "This is the agent body." in result.body

    def test_returns_none_for_missing_name(self, tmp_path):
        content = textwrap.dedent("""\
            ---
            description: No name field
            model: sonnet
            ---
            # Body
        """)
        md_file = tmp_path / "no-name.md"
        md_file.write_text(content, encoding="utf-8")
        assert parse_agent_file(md_file) is None

    def test_returns_none_for_missing_description(self, tmp_path):
        content = textwrap.dedent("""\
            ---
            name: no-desc
            model: sonnet
            ---
            # Body
        """)
        md_file = tmp_path / "no-desc.md"
        md_file.write_text(content, encoding="utf-8")
        assert parse_agent_file(md_file) is None

    def test_defaults_model_and_tier(self, tmp_path):
        content = textwrap.dedent("""\
            ---
            name: minimal
            description: Minimal agent.
            ---
            # Body
        """)
        md_file = tmp_path / "minimal.md"
        md_file.write_text(content, encoding="utf-8")
        result = parse_agent_file(md_file)
        assert result is not None
        assert result.model == "sonnet"
        assert result.tier == "integration"

    def test_handles_invalid_frontmatter(self, tmp_path):
        md_file = tmp_path / "invalid.md"
        md_file.write_bytes(b"\x80\x81\x82")
        result = parse_agent_file(md_file)
        assert result is None


class TestLoadAgents:
    def test_loads_all_agents(self, agents_dir):
        agents = load_agents(agents_dir)
        assert len(agents) == 3
        names = [a.name for a in agents]
        assert "orchestrator" in names
        assert "implementer" in names
        assert "analyst" in names

    def test_skips_non_agent_files(self, agents_dir):
        agents = load_agents(agents_dir)
        names = [a.name for a in agents]
        assert "AGENTS" not in names

    def test_returns_sorted(self, agents_dir):
        agents = load_agents(agents_dir)
        names = [a.name for a in agents]
        assert names == sorted(names)

    def test_empty_directory(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        assert load_agents(empty) == []


class TestGenerateAgentsMd:
    def test_contains_header(self, sample_agents):
        result = generate_agents_md(sample_agents)
        assert "# AGENTS.md" in result
        assert "Multi-agent routing table" in result

    def test_contains_all_agents(self, sample_agents):
        result = generate_agents_md(sample_agents)
        assert "orchestrator" in result
        assert "implementer" in result
        assert "analyst" in result

    def test_maps_tiers_to_roles(self, sample_agents):
        result = generate_agents_md(sample_agents)
        assert "coordinator" in result
        assert "executor" in result
        assert "support" in result

    def test_maps_models(self, sample_agents):
        result = generate_agents_md(sample_agents)
        assert "anthropic/claude-opus-4-6" in result
        assert "anthropic/claude-sonnet-4-6" in result

    def test_includes_routing_rules(self, sample_agents):
        result = generate_agents_md(sample_agents)
        assert "Routing Rules" in result
        assert "Describe the task to solve end-to-end" in result

    def test_truncates_long_descriptions(self):
        agent = AgentDefinition(
            name="verbose",
            description="A" * 100,
            model="sonnet",
            tier="builder",
        )
        result = generate_agents_md([agent])
        assert "..." in result


class TestGenerateSkillMd:
    def test_contains_agent_name(self, sample_agent):
        result = generate_skill_md(sample_agent)
        assert "# analyst" in result

    def test_contains_description(self, sample_agent):
        result = generate_skill_md(sample_agent)
        assert "Research specialist" in result

    def test_contains_model(self, sample_agent):
        result = generate_skill_md(sample_agent)
        assert "anthropic/claude-sonnet-4-6" in result

    def test_contains_role(self, sample_agent):
        result = generate_skill_md(sample_agent)
        assert "support" in result

    def test_contains_usage_when_hint_present(self, sample_agent):
        result = generate_skill_md(sample_agent)
        assert "## Usage" in result
        assert "Describe the topic to research" in result

    def test_no_usage_section_without_hint(self):
        agent = AgentDefinition(
            name="minimal",
            description="Minimal agent.",
            model="sonnet",
            tier="builder",
        )
        result = generate_skill_md(agent)
        assert "## Usage" not in result


class TestExportAgents:
    def test_returns_export_result(self, sample_agents):
        result = export_agents(sample_agents)
        assert isinstance(result, ExportResult)
        assert result.agent_count == 3
        assert "# AGENTS.md" in result.agents_md
        assert "orchestrator" in result.agent_skills
        assert "implementer" in result.agent_skills
        assert "analyst" in result.agent_skills

    def test_empty_agents(self):
        result = export_agents([])
        assert result.agent_count == 0
        assert result.agent_skills == {}


class TestExportJson:
    def test_valid_json(self, sample_agents):
        result = export_json(sample_agents)
        data = json.loads(result)
        assert data["count"] == 3
        assert len(data["agents"]) == 3

    def test_agent_fields(self, sample_agents):
        result = export_json(sample_agents)
        data = json.loads(result)
        orch = next(a for a in data["agents"] if a["name"] == "orchestrator")
        assert orch["model"] == "anthropic/claude-opus-4-6"
        assert orch["role"] == "coordinator"
        assert orch["source"] == "orchestrator"

    def test_empty_list(self):
        result = export_json([])
        data = json.loads(result)
        assert data["count"] == 0
        assert data["agents"] == []


class TestWriteWorkspace:
    def test_creates_files(self, tmp_path, sample_agents):
        result = export_agents(sample_agents)
        output_dir = tmp_path / "workspace"
        count = write_workspace(result, output_dir)
        assert count == 4  # 1 AGENTS.md + 3 skills
        assert (output_dir / "AGENTS.md").exists()
        assert (output_dir / "skills" / "orchestrator" / "SKILL.md").exists()
        assert (output_dir / "skills" / "implementer" / "SKILL.md").exists()
        assert (output_dir / "skills" / "analyst" / "SKILL.md").exists()

    def test_dry_run_no_files(self, tmp_path, sample_agents):
        result = export_agents(sample_agents)
        output_dir = tmp_path / "workspace"
        count = write_workspace(result, output_dir, dry_run=True)
        assert count == 4
        assert not output_dir.exists()

    def test_agents_md_content(self, tmp_path, sample_agents):
        result = export_agents(sample_agents)
        output_dir = tmp_path / "workspace"
        write_workspace(result, output_dir)
        content = (output_dir / "AGENTS.md").read_text(encoding="utf-8")
        assert "orchestrator" in content
        assert "coordinator" in content


class TestMain:
    def test_success_with_valid_dir(self, agents_dir, tmp_path):
        output = tmp_path / "output"
        exit_code = main([
            "--agents-dir", str(agents_dir),
            "--output-dir", str(output),
        ])
        assert exit_code == 0
        assert (output / "AGENTS.md").exists()

    def test_dry_run(self, agents_dir, tmp_path):
        output = tmp_path / "output"
        exit_code = main([
            "--agents-dir", str(agents_dir),
            "--output-dir", str(output),
            "--dry-run",
        ])
        assert exit_code == 0
        assert not output.exists()

    def test_json_format(self, agents_dir, capsys):
        exit_code = main([
            "--agents-dir", str(agents_dir),
            "--format", "json",
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["count"] == 3

    def test_invalid_agents_dir(self, tmp_path):
        exit_code = main([
            "--agents-dir", str(tmp_path / "nonexistent"),
        ])
        assert exit_code == 2

    def test_empty_agents_dir(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        exit_code = main(["--agents-dir", str(empty)])
        assert exit_code == 1

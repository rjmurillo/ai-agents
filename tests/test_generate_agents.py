"""Tests for generate_agents module.

These tests verify the agent generation orchestration including
platform config loading, template processing, validate mode, and what-if mode.

This is a Python port of Generate-Agents.ps1 tests following ADR-042 migration.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add build directory to path for imports
_BUILD_DIR = Path(__file__).resolve().parent.parent / "build"
sys.path.insert(0, str(_BUILD_DIR))

from generate_agents import (  # noqa: E402
    generate_agents,
    main,
    read_platform_config,
)


def _create_test_structure(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create a minimal test directory structure for agent generation.

    Returns (repo_root, templates_path, output_root).
    """
    repo_root = tmp_path / "repo"
    templates_path = repo_root / "templates"
    output_root = repo_root / "src"

    # Platform configs
    platforms_dir = templates_path / "platforms"
    platforms_dir.mkdir(parents=True)
    (platforms_dir / "vscode.yaml").write_text(
        "platform: vscode\n"
        "outputDir: src/vs-code-agents\n"
        "fileExtension: .agent.md\n"
        "frontmatter:\n"
        '  model: "Claude Opus 4.5 (copilot)"\n'
        "  includeNameField: false\n"
        'handoffSyntax: "#runSubagent"\n'
        'memoryPrefix: "serena/"\n',
        encoding="utf-8",
    )

    # Agents directory with a shared template
    agents_dir = templates_path / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "test-agent.shared.md").write_text(
        "---\n"
        "description: A test agent for verification\n"
        "tools: ['read', 'edit']\n"
        "---\n"
        "# Test Agent\n\n"
        "## Core Identity\n\n"
        "**Test Specialist** for verification purposes.\n",
        encoding="utf-8",
    )

    # Output directory
    output_root.mkdir(parents=True)

    return repo_root, templates_path, output_root


class TestReadPlatformConfig:
    """Tests for read_platform_config."""

    def test_reads_basic_config(self, tmp_path: Path) -> None:
        config_file = tmp_path / "vscode.yaml"
        config_file.write_text(
            "platform: vscode\n"
            "outputDir: src/vs-code-agents\n"
            "fileExtension: .agent.md\n"
            "frontmatter:\n"
            "  model: Claude Opus 4.5\n"
            "  includeNameField: false\n",
            encoding="utf-8",
        )
        result = read_platform_config(config_file)
        assert result is not None
        assert result["platform"] == "vscode"
        assert result["fileExtension"] == ".agent.md"
        assert isinstance(result["frontmatter"], dict)
        assert result["frontmatter"]["includeNameField"] is False

    def test_nonexistent_config(self, tmp_path: Path) -> None:
        result = read_platform_config(tmp_path / "nonexistent.yaml")
        assert result is None

    def test_parses_boolean_values(self, tmp_path: Path) -> None:
        config_file = tmp_path / "test.yaml"
        config_file.write_text(
            "platform: test\n"
            "settings:\n"
            "  enabled: true\n"
            "  disabled: false\n",
            encoding="utf-8",
        )
        result = read_platform_config(config_file)
        assert result is not None
        settings = result.get("settings")
        assert isinstance(settings, dict)
        assert settings["enabled"] is True
        assert settings["disabled"] is False

    def test_parses_quoted_strings(self, tmp_path: Path) -> None:
        config_file = tmp_path / "test.yaml"
        config_file.write_text(
            'platform: test\n'
            'frontmatter:\n'
            '  model: "Claude Opus 4.5 (copilot)"\n',
            encoding="utf-8",
        )
        result = read_platform_config(config_file)
        assert result is not None
        frontmatter = result.get("frontmatter")
        assert isinstance(frontmatter, dict)
        assert frontmatter["model"] == "Claude Opus 4.5 (copilot)"

    def test_skips_comments(self, tmp_path: Path) -> None:
        config_file = tmp_path / "test.yaml"
        config_file.write_text(
            "# This is a comment\n"
            "platform: test\n"
            "# Another comment\n"
            "outputDir: src/test\n",
            encoding="utf-8",
        )
        result = read_platform_config(config_file)
        assert result is not None
        assert result["platform"] == "test"
        assert result["outputDir"] == "src/test"


class TestGenerateAgents:
    """Tests for generate_agents orchestration."""

    def test_generates_output_file(self, tmp_path: Path) -> None:
        repo_root, templates_path, output_root = _create_test_structure(tmp_path)
        exit_code = generate_agents(templates_path, output_root, repo_root)
        assert exit_code == 0

        output_file = output_root / "vs-code-agents" / "test-agent.agent.md"
        assert output_file.exists()

    def test_generated_content_has_frontmatter(self, tmp_path: Path) -> None:
        repo_root, templates_path, output_root = _create_test_structure(tmp_path)
        generate_agents(templates_path, output_root, repo_root)

        output_file = output_root / "vs-code-agents" / "test-agent.agent.md"
        content = output_file.read_text(encoding="utf-8")
        assert content.startswith("---")
        assert "model:" in content
        assert "description:" in content

    def test_generated_content_has_crlf(self, tmp_path: Path) -> None:
        repo_root, templates_path, output_root = _create_test_structure(tmp_path)
        generate_agents(templates_path, output_root, repo_root)

        output_file = output_root / "vs-code-agents" / "test-agent.agent.md"
        raw_content = output_file.read_bytes()
        assert b"\r\n" in raw_content

    def test_what_if_mode_no_files(self, tmp_path: Path) -> None:
        repo_root, templates_path, output_root = _create_test_structure(tmp_path)
        exit_code = generate_agents(templates_path, output_root, repo_root, what_if=True)
        assert exit_code == 0

        output_dir = output_root / "vs-code-agents"
        assert not output_dir.exists() or not list(output_dir.glob("*.md"))

    def test_validate_mode_passes_when_matching(self, tmp_path: Path) -> None:
        repo_root, templates_path, output_root = _create_test_structure(tmp_path)

        # First generate, then validate
        generate_agents(templates_path, output_root, repo_root)
        exit_code = generate_agents(templates_path, output_root, repo_root, validate=True)
        assert exit_code == 0

    def test_validate_mode_fails_when_different(self, tmp_path: Path) -> None:
        repo_root, templates_path, output_root = _create_test_structure(tmp_path)

        # Generate first
        generate_agents(templates_path, output_root, repo_root)

        # Modify the output file
        output_file = output_root / "vs-code-agents" / "test-agent.agent.md"
        output_file.write_text("Modified content", encoding="utf-8")

        exit_code = generate_agents(templates_path, output_root, repo_root, validate=True)
        assert exit_code == 1

    def test_validate_mode_fails_when_missing(self, tmp_path: Path) -> None:
        repo_root, templates_path, output_root = _create_test_structure(tmp_path)

        # Do not generate, just validate
        (output_root / "vs-code-agents").mkdir(parents=True, exist_ok=True)
        exit_code = generate_agents(templates_path, output_root, repo_root, validate=True)
        assert exit_code == 1

    def test_no_platform_configs_returns_error(self, tmp_path: Path) -> None:
        repo_root = tmp_path / "repo"
        templates_path = repo_root / "templates"
        output_root = repo_root / "src"

        # Create agents but no platform configs
        agents_dir = templates_path / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "test.shared.md").write_text("---\nname: test\n---\nBody", encoding="utf-8")
        (templates_path / "platforms").mkdir()
        output_root.mkdir(parents=True)

        exit_code = generate_agents(templates_path, output_root, repo_root)
        assert exit_code == 2

    def test_no_shared_files_returns_error(self, tmp_path: Path) -> None:
        repo_root = tmp_path / "repo"
        templates_path = repo_root / "templates"
        output_root = repo_root / "src"

        # Create platform config but no shared agents
        platforms_dir = templates_path / "platforms"
        platforms_dir.mkdir(parents=True)
        (platforms_dir / "vscode.yaml").write_text(
            "platform: vscode\noutputDir: src/out\nfileExtension: .md\n",
            encoding="utf-8",
        )
        (templates_path / "agents").mkdir()
        output_root.mkdir(parents=True)

        exit_code = generate_agents(templates_path, output_root, repo_root)
        assert exit_code == 1

    def test_handoff_syntax_transformed(self, tmp_path: Path) -> None:
        repo_root, templates_path, output_root = _create_test_structure(tmp_path)

        # Add handoff syntax to the shared template
        agents_dir = templates_path / "agents"
        (agents_dir / "test-agent.shared.md").write_text(
            "---\n"
            "description: Test\n"
            "tools: ['read']\n"
            "---\n"
            "Use `/agent analyst` for research.\n",
            encoding="utf-8",
        )

        generate_agents(templates_path, output_root, repo_root)
        output_file = output_root / "vs-code-agents" / "test-agent.agent.md"
        content = output_file.read_text(encoding="utf-8")
        assert "#runSubagent with subagentType=analyst" in content

    def test_memory_prefix_replaced(self, tmp_path: Path) -> None:
        repo_root, templates_path, output_root = _create_test_structure(tmp_path)

        agents_dir = templates_path / "agents"
        (agents_dir / "test-agent.shared.md").write_text(
            "---\n"
            "description: Test\n"
            "tools: ['read']\n"
            "---\n"
            "Use {{MEMORY_PREFIX}}search for lookup.\n",
            encoding="utf-8",
        )

        generate_agents(templates_path, output_root, repo_root)
        output_file = output_root / "vs-code-agents" / "test-agent.agent.md"
        content = output_file.read_text(encoding="utf-8")
        assert "serena/search" in content

    def test_toolset_expansion(self, tmp_path: Path) -> None:
        repo_root, templates_path, output_root = _create_test_structure(tmp_path)

        # Create toolsets.yaml
        (templates_path / "toolsets.yaml").write_text(
            "editor:\n  tools_vscode:\n    - vscode\n    - read\n    - edit\n",
            encoding="utf-8",
        )

        # Use toolset reference in shared template
        agents_dir = templates_path / "agents"
        (agents_dir / "test-agent.shared.md").write_text(
            "---\n"
            "description: Test\n"
            "tools: ['$toolset:editor', 'web']\n"
            "---\n"
            "# Test Agent\n",
            encoding="utf-8",
        )

        generate_agents(templates_path, output_root, repo_root)
        output_file = output_root / "vs-code-agents" / "test-agent.agent.md"
        content = output_file.read_text(encoding="utf-8")
        assert "vscode" in content
        assert "read" in content
        assert "web" in content

    def test_multiple_platforms(self, tmp_path: Path) -> None:
        repo_root, templates_path, output_root = _create_test_structure(tmp_path)

        # Add a second platform
        platforms_dir = templates_path / "platforms"
        (platforms_dir / "copilot-cli.yaml").write_text(
            "platform: copilot-cli\n"
            "outputDir: src/copilot-cli\n"
            "fileExtension: .agent.md\n"
            "frontmatter:\n"
            '  model: "claude-opus-4.5"\n'
            "  includeNameField: true\n"
            'handoffSyntax: "/agent"\n'
            'memoryPrefix: "serena/"\n',
            encoding="utf-8",
        )

        exit_code = generate_agents(templates_path, output_root, repo_root)
        assert exit_code == 0

        vscode_file = output_root / "vs-code-agents" / "test-agent.agent.md"
        copilot_file = output_root / "copilot-cli" / "test-agent.agent.md"
        assert vscode_file.exists()
        assert copilot_file.exists()

        copilot_content = copilot_file.read_text(encoding="utf-8")
        assert "name: test-agent" in copilot_content


class TestMain:
    """Tests for main entry point."""

    def test_missing_templates_path(self, tmp_path: Path) -> None:
        exit_code = main(["--templates-path", str(tmp_path / "nonexistent")])
        assert exit_code == 2

    def test_help_flag(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0

    def test_full_run(self, tmp_path: Path) -> None:
        repo_root, templates_path, output_root = _create_test_structure(tmp_path)
        exit_code = main([
            "--templates-path", str(templates_path),
            "--output-root", str(output_root),
        ])
        assert exit_code == 0

    def test_what_if_flag(self, tmp_path: Path) -> None:
        repo_root, templates_path, output_root = _create_test_structure(tmp_path)
        exit_code = main([
            "--templates-path", str(templates_path),
            "--output-root", str(output_root),
            "--what-if",
        ])
        assert exit_code == 0

    def test_validate_flag(self, tmp_path: Path) -> None:
        repo_root, templates_path, output_root = _create_test_structure(tmp_path)

        # Generate first, then validate
        main([
            "--templates-path", str(templates_path),
            "--output-root", str(output_root),
        ])
        exit_code = main([
            "--templates-path", str(templates_path),
            "--output-root", str(output_root),
            "--validate",
        ])
        assert exit_code == 0

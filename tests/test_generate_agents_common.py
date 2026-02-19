"""Tests for generate_agents_common module.

These tests verify the shared functions used by generate_agents.py
for agent generation.

This is a Python port of Generate-Agents.Common tests following ADR-042 migration.
"""

# mypy: disable-error-code="arg-type"

from __future__ import annotations

import os
import sys
from pathlib import Path

# Add build directory to path for imports
_BUILD_DIR = Path(__file__).resolve().parent.parent / "build"
sys.path.insert(0, str(_BUILD_DIR))

from generate_agents_common import (  # noqa: E402
    convert_frontmatter_for_platform,
    convert_handoff_syntax,
    convert_memory_prefix,
    expand_toolset_references,
    format_frontmatter_yaml,
    is_path_within_root,
    parse_simple_frontmatter,
    read_toolset_definitions,
    read_yaml_frontmatter,
)


class TestIsPathWithinRoot:
    """Tests for is_path_within_root."""

    def test_path_within_root(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        root.mkdir()
        child = root / "src" / "file.py"
        assert is_path_within_root(str(child), str(root)) is True

    def test_path_equals_root(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        root.mkdir()
        assert is_path_within_root(str(root), str(root)) is True

    def test_path_outside_root(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        root.mkdir()
        outside = tmp_path / "other" / "file.py"
        assert is_path_within_root(str(outside), str(root)) is False

    def test_prefix_attack_prevented(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        root.mkdir()
        evil = tmp_path / "repo_evil" / "file.py"
        assert is_path_within_root(str(evil), str(root)) is False

    def test_trailing_separators_handled(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        root.mkdir()
        child = root / "src"
        assert is_path_within_root(str(child) + os.sep, str(root) + os.sep) is True


class TestReadYamlFrontmatter:
    """Tests for read_yaml_frontmatter."""

    def test_extracts_frontmatter_and_body(self) -> None:
        content = "---\nname: test\ndescription: A test\n---\n# Heading\n\nBody text."
        result = read_yaml_frontmatter(content)
        assert result is not None
        assert "name: test" in result["frontmatter_raw"]
        assert result["body"].startswith("# Heading")

    def test_returns_none_without_frontmatter(self) -> None:
        content = "# Just a heading\n\nNo frontmatter."
        result = read_yaml_frontmatter(content)
        assert result is None

    def test_handles_crlf_line_endings(self) -> None:
        content = "---\r\nname: test\r\n---\r\n# Body"
        result = read_yaml_frontmatter(content)
        assert result is not None
        assert "name: test" in result["frontmatter_raw"]

    def test_multiline_frontmatter(self) -> None:
        content = "---\nname: test\ndescription: Long description\nmodel: opus\n---\nBody"
        result = read_yaml_frontmatter(content)
        assert result is not None
        assert "model: opus" in result["frontmatter_raw"]


class TestParseSimpleFrontmatter:
    """Tests for parse_simple_frontmatter."""

    def test_basic_key_value(self) -> None:
        raw = "name: test\ndescription: A test agent"
        result = parse_simple_frontmatter(raw)
        assert result["name"] == "test"
        assert result["description"] == "A test agent"

    def test_inline_array(self) -> None:
        raw = "tools: ['tool1', 'tool2']"
        result = parse_simple_frontmatter(raw)
        assert result["tools"] == "['tool1', 'tool2']"

    def test_block_array(self) -> None:
        raw = "tools:\n  - tool1\n  - tool2"
        result = parse_simple_frontmatter(raw)
        assert result["tools"] is not None
        assert "tool1" in result["tools"]
        assert "tool2" in result["tools"]

    def test_quoted_values_stripped(self) -> None:
        raw = "model: \"Claude Opus 4.5\""
        result = parse_simple_frontmatter(raw)
        assert result["model"] == "Claude Opus 4.5"

    def test_single_quoted_values_stripped(self) -> None:
        raw = "model: 'Claude Opus 4.5'"
        result = parse_simple_frontmatter(raw)
        assert result["model"] == "Claude Opus 4.5"

    def test_null_value(self) -> None:
        raw = "name: test\nmodel: null"
        result = parse_simple_frontmatter(raw)
        assert result["model"] is None

    def test_empty_value_no_array_following(self) -> None:
        raw = "name: test\nmodel:"
        result = parse_simple_frontmatter(raw)
        assert result["model"] is None

    def test_empty_input(self) -> None:
        result = parse_simple_frontmatter("")
        assert result == {}

    def test_whitespace_only_input(self) -> None:
        result = parse_simple_frontmatter("   \n  ")
        assert result == {}

    def test_hyphenated_key(self) -> None:
        raw = "argument-hint: Provide the issue number"
        result = parse_simple_frontmatter(raw)
        assert result["argument-hint"] == "Provide the issue number"

    def test_block_array_with_quoted_items(self) -> None:
        raw = "tools:\n  - 'tool1'\n  - \"tool2\""
        result = parse_simple_frontmatter(raw)
        tools = result.get("tools")
        assert tools is not None
        assert "tool1" in tools
        assert "tool2" in tools

    def test_multiple_arrays(self) -> None:
        raw = "tools_vscode:\n  - vscode\n  - read\ntools_copilot:\n  - read\n  - edit"
        result = parse_simple_frontmatter(raw)
        tools_vscode = result.get("tools_vscode")
        tools_copilot = result.get("tools_copilot")
        assert tools_vscode is not None and "vscode" in tools_vscode
        assert tools_copilot is not None and "edit" in tools_copilot


class TestConvertFrontmatterForPlatform:
    """Tests for convert_frontmatter_for_platform."""

    def test_vscode_platform_removes_name(self) -> None:
        fm: dict[str, str | None] = {"name": "test", "description": "A test"}
        config: dict[str, object] = {
            "platform": "vscode",
            "frontmatter": {"includeNameField": False, "model": "Claude Opus 4.5"},
        }
        result = convert_frontmatter_for_platform(fm, config, "test")
        assert "name" not in result
        assert result["model"] == "Claude Opus 4.5"

    def test_copilot_platform_includes_name(self) -> None:
        fm: dict[str, str | None] = {"description": "A test"}
        config: dict[str, object] = {
            "platform": "copilot-cli",
            "frontmatter": {"includeNameField": True, "model": "claude-opus-4.5"},
        }
        result = convert_frontmatter_for_platform(fm, config, "test-agent")
        assert result["name"] == "test-agent"
        assert result["model"] == "claude-opus-4.5"

    def test_skips_placeholder_values(self) -> None:
        fm: dict[str, str | None] = {"name": "test", "model": "{{PLATFORM_MODEL}}"}
        config: dict[str, object] = {
            "platform": "vscode",
            "frontmatter": {"includeNameField": False, "model": "Claude Opus 4.5"},
        }
        result = convert_frontmatter_for_platform(fm, config, "test")
        assert result["model"] == "Claude Opus 4.5"

    def test_uses_platform_specific_tools(self) -> None:
        fm: dict[str, str | None] = {
            "description": "test",
            "tools_vscode": "['vscode', 'read']",
            "tools_copilot": "['read', 'edit']",
        }
        config: dict[str, object] = {
            "platform": "vscode",
            "frontmatter": {"includeNameField": False},
        }
        result = convert_frontmatter_for_platform(fm, config, "test")
        assert result.get("tools") == "['vscode', 'read']"

    def test_falls_back_to_generic_tools(self) -> None:
        fm = {"description": "test", "tools": "['read', 'edit']"}
        config = {
            "platform": "vscode",
            "frontmatter": {"includeNameField": False},
        }
        result = convert_frontmatter_for_platform(fm, config, "test")
        assert result.get("tools") == "['read', 'edit']"

    def test_copilot_cli_tools_key_resolution(self) -> None:
        fm = {
            "description": "test",
            "tools_copilot": "['read', 'edit']",
        }
        config = {
            "platform": "copilot-cli",
            "frontmatter": {"includeNameField": True, "model": "claude-opus-4.5"},
        }
        result = convert_frontmatter_for_platform(fm, config, "test")
        assert result.get("tools") == "['read', 'edit']"


class TestFormatFrontmatterYaml:
    """Tests for format_frontmatter_yaml."""

    def test_simple_key_value(self) -> None:
        fm = {"description": "A test agent"}
        result = format_frontmatter_yaml(fm)
        assert "description: A test agent" in result

    def test_field_ordering(self) -> None:
        fm = {"model": "opus", "name": "test", "description": "desc"}
        result = format_frontmatter_yaml(fm)
        lines = result.split("\n")
        name_idx = next(i for i, line in enumerate(lines) if line.startswith("name:"))
        desc_idx = next(i for i, line in enumerate(lines) if line.startswith("description:"))
        model_idx = next(i for i, line in enumerate(lines) if line.startswith("model:"))
        assert name_idx < desc_idx < model_idx

    def test_array_output_as_block(self) -> None:
        fm = {"tools": "['vscode', 'read', 'edit']"}
        result = format_frontmatter_yaml(fm)
        assert "tools:" in result
        assert "  - vscode" in result
        assert "  - read" in result
        assert "  - edit" in result

    def test_none_values_skipped(self) -> None:
        fm = {"name": "test", "model": None}
        result = format_frontmatter_yaml(fm)
        assert "model" not in result

    def test_argument_hint_field(self) -> None:
        fm = {"argument-hint": "Specify the context"}
        result = format_frontmatter_yaml(fm)
        assert "argument-hint: Specify the context" in result


class TestConvertHandoffSyntax:
    """Tests for convert_handoff_syntax."""

    def test_convert_to_runsubagent(self) -> None:
        body = "Use `/agent analyst` for research."
        result = convert_handoff_syntax(body, "#runSubagent")
        assert "`#runSubagent with subagentType=analyst`" in result

    def test_convert_to_agent(self) -> None:
        body = "Use `#runSubagent with subagentType=analyst` for research."
        result = convert_handoff_syntax(body, "/agent")
        assert "`/agent analyst`" in result

    def test_convert_placeholder_to_runsubagent(self) -> None:
        body = "Use /agent [agent_name] for delegation."
        result = convert_handoff_syntax(body, "#runSubagent")
        assert "#runSubagent with subagentType={agent_name}" in result

    def test_convert_placeholder_to_agent(self) -> None:
        body = "Use #runSubagent with subagentType={agent_name} for delegation."
        result = convert_handoff_syntax(body, "/agent")
        assert "/agent [agent_name]" in result

    def test_no_change_for_unknown_syntax(self) -> None:
        body = "No handoff syntax here."
        result = convert_handoff_syntax(body, "#runSubagent")
        assert result == body


class TestConvertMemoryPrefix:
    """Tests for convert_memory_prefix."""

    def test_replaces_placeholder(self) -> None:
        body = "Use {{MEMORY_PREFIX}}memory-search for looking up memories."
        result = convert_memory_prefix(body, "serena/")
        assert "serena/memory-search" in result

    def test_no_placeholder_unchanged(self) -> None:
        body = "No placeholder in this text."
        result = convert_memory_prefix(body, "serena/")
        assert result == body

    def test_multiple_replacements(self) -> None:
        body = "First: {{MEMORY_PREFIX}}search, second: {{MEMORY_PREFIX}}write"
        result = convert_memory_prefix(body, "cloudmcp-manager/")
        assert "cloudmcp-manager/search" in result
        assert "cloudmcp-manager/write" in result


class TestReadToolsetDefinitions:
    """Tests for read_toolset_definitions."""

    def test_reads_basic_toolset(self, tmp_path: Path) -> None:
        content = "editor:\n  tools:\n    - vscode\n    - read\n    - edit\n"
        toolsets_file = tmp_path / "toolsets.yaml"
        toolsets_file.write_text(content, encoding="utf-8")

        result = read_toolset_definitions(toolsets_file)
        assert "editor" in result
        assert result["editor"]["tools"] == ["vscode", "read", "edit"]

    def test_reads_platform_specific(self, tmp_path: Path) -> None:
        content = (
            "editor:\n  tools_vscode:\n    - vscode\n    - read\n"
            "  tools_copilot:\n    - read\n    - edit\n"
        )
        toolsets_file = tmp_path / "toolsets.yaml"
        toolsets_file.write_text(content, encoding="utf-8")

        result = read_toolset_definitions(toolsets_file)
        assert result["editor"]["tools_vscode"] == ["vscode", "read"]
        assert result["editor"]["tools_copilot"] == ["read", "edit"]

    def test_reads_description(self, tmp_path: Path) -> None:
        content = "editor:\n  description: Core editing tools\n  tools:\n    - read\n"
        toolsets_file = tmp_path / "toolsets.yaml"
        toolsets_file.write_text(content, encoding="utf-8")

        result = read_toolset_definitions(toolsets_file)
        assert result["editor"]["description"] == "Core editing tools"

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        result = read_toolset_definitions(tmp_path / "nonexistent.yaml")
        assert result == {}

    def test_multiple_toolsets(self, tmp_path: Path) -> None:
        content = "editor:\n  tools:\n    - read\nresearch:\n  tools:\n    - web\n"
        toolsets_file = tmp_path / "toolsets.yaml"
        toolsets_file.write_text(content, encoding="utf-8")

        result = read_toolset_definitions(toolsets_file)
        assert "editor" in result
        assert "research" in result

    def test_skips_comments(self, tmp_path: Path) -> None:
        content = "# This is a comment\neditor:\n  tools:\n    - read\n"
        toolsets_file = tmp_path / "toolsets.yaml"
        toolsets_file.write_text(content, encoding="utf-8")

        result = read_toolset_definitions(toolsets_file)
        assert "editor" in result


class TestExpandToolsetReferences:
    """Tests for expand_toolset_references."""

    def test_no_toolset_refs_unchanged(self) -> None:
        result = expand_toolset_references("['read', 'edit']", {}, "vscode")
        assert result == "['read', 'edit']"

    def test_expands_simple_toolset(self) -> None:
        toolsets = {"editor": {"tools": ["vscode", "read", "edit"]}}
        result = expand_toolset_references("['$toolset:editor']", toolsets, "vscode")
        assert "'vscode'" in result
        assert "'read'" in result
        assert "'edit'" in result

    def test_expands_platform_specific(self) -> None:
        toolsets = {
            "editor": {
                "tools_vscode": ["vscode", "read"],
                "tools_copilot": ["read", "edit"],
            }
        }
        result = expand_toolset_references("['$toolset:editor']", toolsets, "vscode")
        assert "'vscode'" in result
        assert "'read'" in result
        assert "'edit'" not in result

    def test_mixed_toolset_and_literal(self) -> None:
        toolsets = {"editor": {"tools": ["vscode", "read"]}}
        result = expand_toolset_references("['$toolset:editor', 'web']", toolsets, "vscode")
        assert "'vscode'" in result
        assert "'read'" in result
        assert "'web'" in result

    def test_unknown_toolset_skipped(self) -> None:
        result = expand_toolset_references("['$toolset:unknown']", {}, "vscode")
        assert result == "[]"

    def test_deduplicates_tools(self) -> None:
        toolsets = {"editor": {"tools": ["read", "edit"]}}
        result = expand_toolset_references("['$toolset:editor', 'read']", toolsets, "vscode")
        assert result.count("'read'") == 1

    def test_not_array_format_unchanged(self) -> None:
        result = expand_toolset_references("not an array", {}, "vscode")
        assert result == "not an array"

    def test_copilot_cli_platform_key(self) -> None:
        toolsets = {
            "editor": {
                "tools_copilot": ["read", "edit"],
            }
        }
        result = expand_toolset_references("['$toolset:editor']", toolsets, "copilot-cli")
        assert "'read'" in result
        assert "'edit'" in result

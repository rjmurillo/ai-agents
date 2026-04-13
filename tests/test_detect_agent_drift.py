"""Tests for detect_agent_drift module.

These tests verify the drift detection functionality that compares
Claude agents with VS Code/Copilot agents for semantic drift.

This is a Python port of Detect-AgentDrift.Tests.ps1 following ADR-042 migration.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

# Add build/scripts to path for imports
_BUILD_SCRIPTS = Path(__file__).resolve().parent.parent / "build" / "scripts"
sys.path.insert(0, str(_BUILD_SCRIPTS))

from detect_agent_drift import (  # noqa: E402
    AgentResult,
    SectionResult,
    calculate_similarity,
    compare_agent,
    format_json,
    format_markdown,
    format_text,
    get_markdown_sections,
    main,
    normalize_content,
    remove_yaml_frontmatter,
    run_detection,
)

if TYPE_CHECKING:
    pass


class TestRemoveYamlFrontmatter:
    """Tests for remove_yaml_frontmatter."""

    def test_removes_standard_frontmatter(self) -> None:
        content = (
            "---\nname: test\ndescription: Test agent\nmodel: opus\n---\n"
            "# Agent Title\n\nBody content here."
        )
        result = remove_yaml_frontmatter(content)
        assert result.startswith("# Agent Title")
        assert "---" not in result
        assert "name: test" not in result

    def test_handles_content_without_frontmatter(self) -> None:
        content = "# Just a heading\n\nNo frontmatter."
        result = remove_yaml_frontmatter(content)
        assert result == content

    def test_handles_vscode_frontmatter_with_tools_array(self) -> None:
        content = (
            "---\ndescription: Test description\ntools: ['tool1', 'tool2']\n"
            "model: Claude Opus 4.5 (anthropic)\n---\n# Agent Title\n\nContent."
        )
        result = remove_yaml_frontmatter(content)
        assert result.startswith("# Agent Title")
        assert "tools:" not in result


class TestGetMarkdownSections:
    """Tests for get_markdown_sections."""

    def test_extracts_sections_by_headers(self) -> None:
        content = (
            "# Title\n\nPreamble content.\n\n## Core Identity\n\n"
            "Identity content here.\n\n## Core Mission\n\nMission content here."
        )
        result = get_markdown_sections(content)
        assert "preamble" in result
        assert "Core Identity" in result
        assert "Core Mission" in result
        assert "Identity content" in result["Core Identity"]
        assert "Mission content" in result["Core Mission"]

    def test_handles_subsections(self) -> None:
        content = (
            "## Section One\n\nContent one.\n\n### Subsection\n\nSub content.\n\n"
            "## Section Two\n\nContent two."
        )
        result = get_markdown_sections(content)
        assert "Section One" in result
        assert "Section Two" in result
        assert "Sub content" in result["Section One"]

    def test_handles_empty_sections(self) -> None:
        content = "## Empty Section\n\n## Non-Empty Section\n\nHas content."
        result = get_markdown_sections(content)
        assert "Empty Section" in result
        assert result["Empty Section"] == ""

    def test_preamble_only_content(self) -> None:
        content = "Just some text without headers."
        result = get_markdown_sections(content)
        assert "preamble" in result
        assert result["preamble"] == "Just some text without headers."


class TestNormalizeContent:
    """Tests for normalize_content."""

    def test_normalizes_cloudmcp_syntax(self) -> None:
        content = "mcp__cloudmcp-manager__memory-search_nodes"
        result = normalize_content(content)
        assert result == "cloudmcp-manager/memory-search_nodes"

    def test_normalizes_deepwiki_syntax(self) -> None:
        content = "mcp__cognitionai-deepwiki__ask_question"
        result = normalize_content(content)
        assert result == "cognitionai/deepwiki/ask_question"

    def test_normalizes_context7_syntax(self) -> None:
        content = "mcp__context7__resolve-library-id"
        result = normalize_content(content)
        assert result == "context7/resolve-library-id"

    def test_normalizes_runsubagent_syntax(self) -> None:
        content = "Use `#runSubagent with subagentType=analyst` for research"
        result = normalize_content(content)
        assert "invoke analyst" in result

    def test_normalizes_agent_syntax(self) -> None:
        content = "Use `/agent analyst` for research"
        result = normalize_content(content)
        assert "invoke analyst" in result

    def test_preserves_non_backticked_references(self) -> None:
        content = "Use #runSubagent with subagentType=analyst for research"
        result = normalize_content(content)
        assert "#runSubagent" in result

    def test_removes_trailing_whitespace(self) -> None:
        content = "Line with trailing spaces   \nAnother line  "
        result = normalize_content(content)
        for line in result.split("\n"):
            assert line == line.rstrip()

    def test_collapses_multiple_blank_lines(self) -> None:
        content = "Line one\n\n\n\n\nLine two"
        result = normalize_content(content)
        assert result == "Line one\n\nLine two"

    def test_normalizes_crlf_to_lf(self) -> None:
        content = "Line one\r\nLine two"
        result = normalize_content(content)
        assert "\r" not in result

    def test_normalizes_code_block_languages(self) -> None:
        content = "```bash\necho hello\n```"
        result = normalize_content(content)
        assert "```bash" not in result
        assert result.startswith("```")


class TestCalculateSimilarity:
    """Tests for calculate_similarity."""

    def test_identical_text_returns_100(self) -> None:
        text = "This is identical content for testing purposes."
        assert calculate_similarity(text, text) == 100.0

    def test_both_empty_returns_100(self) -> None:
        assert calculate_similarity("", "") == 100.0

    def test_both_whitespace_returns_100(self) -> None:
        assert calculate_similarity("   ", "   ") == 100.0

    def test_whitespace_differences_ignored(self) -> None:
        text1 = "Same words here"
        text2 = "Same   words   here"
        assert calculate_similarity(text1, text2) == 100.0

    def test_case_differences_ignored(self) -> None:
        text1 = "Research technical approaches implementation"
        text2 = "RESEARCH TECHNICAL APPROACHES IMPLEMENTATION"
        assert calculate_similarity(text1, text2) == 100.0

    def test_completely_different_returns_0(self) -> None:
        text1 = "Alpha beta gamma delta"
        text2 = "One two three four"
        assert calculate_similarity(text1, text2) == 0.0

    def test_partial_overlap(self) -> None:
        text1 = "Research analyze investigate document"
        text2 = "Research investigate verify document"
        result = calculate_similarity(text1, text2)
        assert 50.0 < result < 100.0

    def test_one_empty_returns_0(self) -> None:
        assert calculate_similarity("Content here", "") == 0.0

    def test_short_words_ignored(self) -> None:
        text1 = "a is to by"
        text2 = "I am at on"
        assert calculate_similarity(text1, text2) == 100.0


class TestCompareAgent:
    """Tests for compare_agent."""

    def test_matching_agents_no_drift(self) -> None:
        claude = (
            "---\nname: test\nmodel: opus\n---\n# Test\n\n## Core Identity\n\n"
            "**Test Specialist** for integration testing.\n\n## Core Mission\n\n"
            "Execute tests and validate results."
        )
        vscode = (
            "---\ndescription: Test\ntools: ['vscode']\nmodel: Claude Opus 4.5\n---\n"
            "# Test\n\n## Core Identity\n\n**Test Specialist** for integration testing.\n\n"
            "## Core Mission\n\nExecute tests and validate results."
        )
        result = compare_agent(claude, vscode, "test-agent", 80)
        assert result.status == "OK"
        assert result.overall_similarity is not None
        assert result.overall_similarity >= 80

    def test_drifted_agents_detected(self) -> None:
        claude = (
            "---\nname: drifted\n---\n## Core Identity\n\n"
            "**Original Role** for specific purposes.\n\n## Core Mission\n\n"
            "Perform original tasks."
        )
        vscode = (
            "---\ndescription: drifted\n---\n## Core Identity\n\n"
            "**New Enhanced Role** for completely different purposes.\n\n"
            "## Core Mission\n\nExecute new workflows and manage new features."
        )
        result = compare_agent(claude, vscode, "drifted", 80)
        assert len(result.drifting_sections) > 0

    def test_normalized_mcp_syntax_matches(self) -> None:
        claude = (
            "---\nname: test\n---\n## Memory Protocol\n\n"
            "Use mcp__cloudmcp-manager__memory-search_nodes for searching."
        )
        vscode = (
            "---\ndescription: test\n---\n## Memory Protocol\n\n"
            "Use cloudmcp-manager/memory-search_nodes for searching."
        )
        result = compare_agent(claude, vscode, "test", 80)
        for section in result.sections:
            if section.section == "Memory Protocol":
                assert section.similarity == 100.0


class TestRunDetection:
    """Tests for run_detection with filesystem."""

    def test_no_counterpart(self, tmp_path: Path) -> None:
        claude_dir = tmp_path / "claude"
        vscode_dir = tmp_path / "vscode"
        claude_dir.mkdir()
        vscode_dir.mkdir()
        (claude_dir / "orphan.md").write_text("# Orphan Agent\n\nContent.", encoding="utf-8")

        results = run_detection(claude_dir, vscode_dir, 80)
        assert len(results) == 1
        assert results[0].status == "NO COUNTERPART"
        assert results[0].overall_similarity is None

    def test_matching_pair(self, tmp_path: Path) -> None:
        claude_dir = tmp_path / "claude"
        vscode_dir = tmp_path / "vscode"
        claude_dir.mkdir()
        vscode_dir.mkdir()

        agent_content = "---\nname: test\n---\n## Core Identity\n\n**Test Agent** for testing."
        (claude_dir / "test.md").write_text(agent_content, encoding="utf-8")
        (vscode_dir / "test.agent.md").write_text(agent_content, encoding="utf-8")

        results = run_detection(claude_dir, vscode_dir, 80)
        assert len(results) == 1
        assert results[0].status == "OK"

    def test_empty_directory(self, tmp_path: Path) -> None:
        claude_dir = tmp_path / "claude"
        vscode_dir = tmp_path / "vscode"
        claude_dir.mkdir()
        vscode_dir.mkdir()

        results = run_detection(claude_dir, vscode_dir, 80)
        assert results == []


class TestFormatText:
    """Tests for format_text output."""

    def test_no_drift_message(self) -> None:
        results = [
            AgentResult(agent_name="test", overall_similarity=95.0, status="OK"),
        ]
        output = format_text(results, 80, 0.5, 0, 1, 0)
        assert "No significant drift detected" in output

    def test_drift_detected_message(self) -> None:
        results = [
            AgentResult(
                agent_name="drifted",
                overall_similarity=50.0,
                status="DRIFT DETECTED",
                drifting_sections=["Core Identity"],
            ),
        ]
        output = format_text(results, 80, 0.5, 1, 0, 0)
        assert "1 agent(s) with drift detected" in output
        assert 'Section "Core Identity" differs' in output

    def test_no_counterpart_shown(self) -> None:
        results = [
            AgentResult(agent_name="orphan", overall_similarity=None, status="NO COUNTERPART"),
        ]
        output = format_text(results, 80, 0.5, 0, 0, 1)
        assert "NO COUNTERPART" in output


class TestFormatJson:
    """Tests for format_json output."""

    def test_valid_json_output(self) -> None:
        results = [
            AgentResult(agent_name="test", overall_similarity=95.0, status="OK"),
        ]
        output = format_json(results, 80, 0.5, 0, 1, 0)
        parsed = json.loads(output)
        assert parsed["threshold"] == 80
        assert parsed["summary"]["ok"] == 1
        assert len(parsed["results"]) == 1

    def test_json_includes_sections(self) -> None:
        results = [
            AgentResult(
                agent_name="test",
                overall_similarity=95.0,
                status="OK",
                sections=[
                    SectionResult("Core Identity", 100.0, True, True, "OK"),
                ],
            ),
        ]
        output = format_json(results, 80, 0.5, 0, 1, 0)
        parsed = json.loads(output)
        assert parsed["results"][0]["sections"][0]["section"] == "Core Identity"


class TestFormatMarkdown:
    """Tests for format_markdown output."""

    def test_markdown_structure(self) -> None:
        results = [
            AgentResult(agent_name="test", overall_similarity=90.0, status="OK"),
        ]
        output = format_markdown(results, 80, 0.5, 0, 1, 0)
        assert "# Agent Drift Detection Report" in output
        assert "| Metric | Count |" in output
        assert "| Agent | Status | Similarity | Drifting Sections |" in output
        assert "| test | OK | 90.0% | - |" in output


class TestMain:
    """Tests for main entry point."""

    def test_invalid_claude_path(self, tmp_path: Path) -> None:
        exit_code = main(["--claude-path", str(tmp_path / "nonexistent")])
        assert exit_code == 2

    def test_invalid_vscode_path(self, tmp_path: Path) -> None:
        claude_dir = tmp_path / "claude"
        claude_dir.mkdir()
        exit_code = main([
            "--claude-path",
            str(claude_dir),
            "--vscode-path",
            str(tmp_path / "nonexistent"),
        ])
        assert exit_code == 2

    def test_no_drift_returns_0(self, tmp_path: Path) -> None:
        claude_dir = tmp_path / "claude"
        vscode_dir = tmp_path / "vscode"
        claude_dir.mkdir()
        vscode_dir.mkdir()

        content = "---\nname: test\n---\n## Core Identity\n\n**Test Agent** for testing."
        (claude_dir / "test.md").write_text(content, encoding="utf-8")
        (vscode_dir / "test.agent.md").write_text(content, encoding="utf-8")

        exit_code = main([
            "--claude-path", str(claude_dir),
            "--vscode-path", str(vscode_dir),
        ])
        assert exit_code == 0

    def test_json_output_format(self, tmp_path: Path) -> None:
        claude_dir = tmp_path / "claude"
        vscode_dir = tmp_path / "vscode"
        claude_dir.mkdir()
        vscode_dir.mkdir()

        exit_code = main([
            "--claude-path", str(claude_dir),
            "--vscode-path", str(vscode_dir),
            "--output-format", "json",
        ])
        assert exit_code == 0

    def test_help_flag(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0

#!/usr/bin/env python3
"""Detect semantic drift between Claude agents and VS Code/Copilot agents.

Compares Claude agents (src/claude/*.md) with corresponding VS Code agents
(src/vs-code-agents/*.agent.md) to detect significant content differences.

Claude agents have unique content and are NOT generated from templates.
This script detects when Claude agents diverge significantly from the
shared content that VS Code/Copilot agents are generated from.

The script ignores known platform-specific differences:
- YAML frontmatter format differences
- Tool invocation syntax (mcp__cloudmcp-manager__* vs cloudmcp-manager/*)
- Claude Code Tools section (Claude-specific)
- Platform-specific tool references

The script focuses on detecting drift in:
- Core Identity / Core Mission sections
- Key Responsibilities
- Review criteria / checklists
- Templates and output formats

EXIT CODES:
  0  - No significant drift detected
  1  - Drift detected (similarity below threshold)
  2  - Error during execution

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

SECTIONS_TO_COMPARE = (
    "Core Identity",
    "Core Mission",
    "Key Responsibilities",
    "Constraints",
    "Handoff Options",
    "Execution Mindset",
    "Memory Protocol",
    "Memory Protocol (cloudmcp-manager)",
    "Impact Analysis Mode",
    "Analysis Types",
    "ADR Template",
    "ADR Format",
    "Review Phases",
    "Architecture Review Process",
    "Handoff Protocol",
    "Analysis Document Format",
)

# MCP syntax normalization patterns (compiled once)
_MCP_PATTERNS = (
    (re.compile(r"mcp__cloudmcp-manager__"), "cloudmcp-manager/"),
    (re.compile(r"mcp__cognitionai-deepwiki__"), "cognitionai/deepwiki/"),
    (re.compile(r"mcp__context7__"), "context7/"),
    (re.compile(r"mcp__deepwiki__"), "deepwiki/"),
)

_HANDOFF_PATTERNS = (
    (re.compile(r"`#runSubagent with subagentType=(\w+)`"), r"`invoke \1`"),
    (re.compile(r"`/agent\s+(\w+)`"), r"`invoke \1`"),
)

_CODE_BLOCK_LANG = re.compile(r"```(bash|powershell|text|markdown|python)")
_MULTI_BLANK_LINES = re.compile(r"\n{3,}")
_WORD_SPLIT = re.compile(r"\W+")


@dataclass
class SectionResult:
    """Result of comparing a single section between two agents."""

    section: str
    similarity: float
    claude_has: bool
    vscode_has: bool
    status: str


@dataclass
class AgentResult:
    """Result of comparing a single agent pair."""

    agent_name: str
    overall_similarity: float | None
    status: str
    sections: list[SectionResult] = field(default_factory=list)
    drifting_sections: list[str] = field(default_factory=list)


def remove_yaml_frontmatter(content: str) -> str:
    """Remove YAML frontmatter from markdown content."""
    match = re.match(r"^---\r?\n[\s\S]*?\r?\n---\r?\n([\s\S]*)$", content)
    if match:
        return match.group(1)
    return content


def get_markdown_sections(content: str) -> dict[str, str]:
    """Extract sections from markdown content based on ## headers."""
    sections: dict[str, str] = {}
    current_section = "preamble"
    current_lines: list[str] = []

    for line in content.splitlines():
        header_match = re.match(r"^##\s+(.+)$", line)
        if header_match:
            if current_lines:
                sections[current_section] = "\n".join(current_lines).strip()
            current_section = header_match.group(1).strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        sections[current_section] = "\n".join(current_lines).strip()

    return sections


def normalize_content(content: str) -> str:
    """Normalize content by removing platform-specific syntax."""
    result = content

    for pattern, replacement in _MCP_PATTERNS:
        result = pattern.sub(replacement, result)

    for pattern, replacement in _HANDOFF_PATTERNS:
        result = pattern.sub(replacement, result)

    result = _CODE_BLOCK_LANG.sub("```", result)

    result = result.replace("\r\n", "\n")
    lines = [line.rstrip() for line in result.split("\n")]
    result = "\n".join(lines).strip()

    result = _MULTI_BLANK_LINES.sub("\n\n", result)

    return result


def calculate_similarity(text1: str, text2: str) -> float:
    """Calculate Jaccard similarity on word tokens (>2 chars, case-insensitive)."""
    if not text1.strip() and not text2.strip():
        return 100.0
    if not text1.strip() or not text2.strip():
        return 0.0

    words1 = {w.lower() for w in _WORD_SPLIT.split(text1) if len(w) > 2}
    words2 = {w.lower() for w in _WORD_SPLIT.split(text2) if len(w) > 2}

    if not words1 and not words2:
        return 100.0

    intersection = words1 & words2
    union = words1 | words2

    if not union:
        return 100.0

    return round((len(intersection) / len(union)) * 100, 1)


def compare_agent(
    claude_content: str,
    vscode_content: str,
    agent_name: str,
    threshold: int,
) -> AgentResult:
    """Compare two agent files and return drift analysis."""
    claude_body = remove_yaml_frontmatter(claude_content)
    vscode_body = remove_yaml_frontmatter(vscode_content)

    claude_sections = get_markdown_sections(claude_body)
    vscode_sections = get_markdown_sections(vscode_body)

    section_results: list[SectionResult] = []
    total_similarity = 0.0
    compared_count = 0

    for section in SECTIONS_TO_COMPARE:
        claude_section = claude_sections.get(section)
        vscode_section = vscode_sections.get(section)

        if claude_section is None and vscode_section is None:
            continue

        claude_normalized = normalize_content(claude_section) if claude_section else ""
        vscode_normalized = normalize_content(vscode_section) if vscode_section else ""

        similarity = calculate_similarity(claude_normalized, vscode_normalized)
        status = "OK" if similarity >= threshold else "DRIFT"

        section_results.append(
            SectionResult(
                section=section,
                similarity=similarity,
                claude_has=claude_section is not None,
                vscode_has=vscode_section is not None,
                status=status,
            )
        )

        total_similarity += similarity
        compared_count += 1

    overall = round(total_similarity / compared_count, 1) if compared_count > 0 else 100.0
    overall_status = "OK" if overall >= threshold else "DRIFT DETECTED"
    drifting = [r.section for r in section_results if r.status == "DRIFT"]

    return AgentResult(
        agent_name=agent_name,
        overall_similarity=overall,
        status=overall_status,
        sections=section_results,
        drifting_sections=drifting,
    )


def format_text(
    results: list[AgentResult],
    threshold: int,
    duration: float,
    drift_count: int,
    ok_count: int,
    no_counterpart_count: int,
) -> str:
    """Format results as colored text output."""
    lines: list[str] = []
    lines.append("")
    lines.append("=== Agent Drift Detection ===")
    lines.append("Comparing: Claude vs VS Code/Copilot")
    lines.append(f"Similarity Threshold: {threshold}%")
    lines.append("")

    for result in sorted(results, key=lambda r: r.agent_name):
        if result.overall_similarity is not None:
            lines.append(
                f"{result.agent_name}: {result.status} ({result.overall_similarity}% similar)"
            )
        else:
            lines.append(f"{result.agent_name}: {result.status}")

        for section in result.drifting_sections:
            lines.append(f'  - Section "{section}" differs')

    lines.append("")
    lines.append("=== Summary ===")
    lines.append(f"Duration: {duration:.2f}s")
    lines.append(f"Agents compared: {len(results)}")
    lines.append(f"OK: {ok_count}")
    lines.append(f"Drift detected: {drift_count}")
    lines.append(f"No counterpart: {no_counterpart_count}")
    lines.append("")

    if drift_count > 0:
        lines.append(f"RESULT: {drift_count} agent(s) with drift detected")
    else:
        lines.append("RESULT: No significant drift detected")

    return "\n".join(lines)


def format_json(
    results: list[AgentResult],
    threshold: int,
    duration: float,
    drift_count: int,
    ok_count: int,
    no_counterpart_count: int,
) -> str:
    """Format results as JSON output."""
    output = {
        "duration": duration,
        "threshold": threshold,
        "summary": {
            "totalAgents": len(results),
            "ok": ok_count,
            "driftDetected": drift_count,
            "noCounterpart": no_counterpart_count,
        },
        "results": [
            {
                "agentName": r.agent_name,
                "overallSimilarity": r.overall_similarity,
                "status": r.status,
                "sections": [
                    {
                        "section": s.section,
                        "similarity": s.similarity,
                        "claudeHas": s.claude_has,
                        "vscodeHas": s.vscode_has,
                        "status": s.status,
                    }
                    for s in r.sections
                ],
                "driftingSections": r.drifting_sections,
            }
            for r in results
        ],
    }
    return json.dumps(output, indent=2)


def format_markdown(
    results: list[AgentResult],
    threshold: int,
    duration: float,
    drift_count: int,
    ok_count: int,
    no_counterpart_count: int,
) -> str:
    """Format results as Markdown output."""
    lines: list[str] = []
    lines.append("# Agent Drift Detection Report")
    lines.append("")
    lines.append(f"**Threshold**: {threshold}%")
    lines.append(f"**Duration**: {duration:.2f}s")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Count |")
    lines.append("|--------|-------|")
    lines.append(f"| Agents Compared | {len(results)} |")
    lines.append(f"| OK | {ok_count} |")
    lines.append(f"| Drift Detected | {drift_count} |")
    lines.append(f"| No Counterpart | {no_counterpart_count} |")
    lines.append("")
    lines.append("## Results")
    lines.append("")
    lines.append("| Agent | Status | Similarity | Drifting Sections |")
    lines.append("|-------|--------|------------|-------------------|")

    for result in sorted(results, key=lambda r: r.agent_name):
        if result.overall_similarity is not None:
            similarity = f"{result.overall_similarity}%"
        else:
            similarity = "N/A"
        drifting = ", ".join(result.drifting_sections) if result.drifting_sections else "-"
        lines.append(f"| {result.agent_name} | {result.status} | {similarity} | {drifting} |")

    return "\n".join(lines)


def run_detection(
    claude_path: Path,
    vscode_path: Path,
    threshold: int,
) -> list[AgentResult]:
    """Run drift detection and return results."""
    results: list[AgentResult] = []

    claude_files = sorted(claude_path.glob("*.md"))

    for claude_file in claude_files:
        agent_name = claude_file.stem
        vscode_file = vscode_path / f"{agent_name}.agent.md"

        if not vscode_file.exists():
            results.append(
                AgentResult(
                    agent_name=agent_name,
                    overall_similarity=None,
                    status="NO COUNTERPART",
                )
            )
            continue

        claude_content = claude_file.read_text(encoding="utf-8")
        vscode_content = vscode_file.read_text(encoding="utf-8")

        comparison = compare_agent(claude_content, vscode_content, agent_name, threshold)
        results.append(comparison)

    return results


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description="Detect semantic drift between Claude agents and VS Code/Copilot agents.",
    )
    parser.add_argument(
        "--claude-path",
        type=Path,
        default=None,
        help="Path to Claude agents directory. Defaults to src/claude.",
    )
    parser.add_argument(
        "--vscode-path",
        type=Path,
        default=None,
        help="Path to VS Code agents directory. Defaults to src/vs-code-agents.",
    )
    parser.add_argument(
        "--similarity-threshold",
        type=int,
        default=80,
        choices=range(0, 101),
        metavar="[0-100]",
        help="Minimum similarity percentage (0-100). Default: 80.",
    )
    parser.add_argument(
        "--output-format",
        choices=["text", "json", "markdown"],
        default="text",
        help="Output format: text (default), json, or markdown.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for drift detection."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # Resolve repo root: script is in build/scripts/, go up two levels
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent

    claude_path = args.claude_path or (repo_root / "src" / "claude")
    vscode_path = args.vscode_path or (repo_root / "src" / "vs-code-agents")

    if not claude_path.is_dir():
        print(f"Error: Claude agents path not found: {claude_path}", file=sys.stderr)
        return 2

    if not vscode_path.is_dir():
        print(f"Error: VS Code agents path not found: {vscode_path}", file=sys.stderr)
        return 2

    start_time = time.monotonic()
    results = run_detection(claude_path, vscode_path, args.similarity_threshold)
    duration = time.monotonic() - start_time

    drift_count = sum(1 for r in results if r.status == "DRIFT DETECTED")
    ok_count = sum(1 for r in results if r.status == "OK")
    no_counterpart_count = sum(1 for r in results if r.status == "NO COUNTERPART")

    format_args = (
        results,
        args.similarity_threshold,
        duration,
        drift_count,
        ok_count,
        no_counterpart_count,
    )

    if args.output_format == "json":
        output = format_json(*format_args)
    elif args.output_format == "markdown":
        output = format_markdown(*format_args)
    else:
        output = format_text(*format_args)

    print(output)

    return 1 if drift_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())

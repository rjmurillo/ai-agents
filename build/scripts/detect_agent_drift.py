#!/usr/bin/env python3
"""Detect semantic drift between agent copies.

Two comparisons run by default:

1. Vendored copies: Claude agents (src/claude/*.md) against VS Code agents
   (src/vs-code-agents/*.agent.md).
2. Install copies (Issue #2267): the hand-maintained Claude Code self-host
   copies (.claude/agents/*.md) against the GitHub Copilot self-host copies
   (.github/agents/*.agent.md), scoped to shared-template agents (the ones
   whose prose comes from templates/agents/*.shared.md). Pass
   ``--skip-install-comparison`` to run only the vendored comparison.

The install copies are hand-maintained: no generator writes them
(REQ-003-010 forbids generators under .claude/). validate_install_parity.py
already enforces that they move together in a diff; this script adds the
semantic-similarity check that parity enforcement omits.

Issue #4852 asks the gate to cover "all six maintained/generated surfaces or
document why a surface is not a runtime input." The six are src/claude,
src/vs-code-agents, src/copilot-cli/agents, .claude/agents, .github/agents,
and templates/agents/*.shared.md (per build/AGENTS.md, "Hand-Maintained Agent
Copies"). Two of those six (src/copilot-cli/agents and templates/agents) are
intentionally NOT drift-compared here: src/copilot-cli/agents and
src/vs-code-agents are both generated from templates/agents/*.shared.md by
``build/generate_agents.py``, whose ``--validate`` flag (see
``_handle_validate`` in that script) already holds src/copilot-cli/agents to
an exact string match (normalized only for line endings) against its
template source, not a similarity threshold; a generator bug there fails
that check outright rather than drifting silently. templates/agents itself
is the shared source both generated trees derive from, so it has no
independent counterpart to drift against. The two comparisons this script
does run (vendored src/claude vs src/vs-code-agents, and the hand-maintained
.claude/agents vs .github/agents) cover the pairs where two independently
maintained or independently editable copies can diverge without any
generator or validator catching it, which is exactly the failure mode #4852
reported.

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
    "Reviewer Asymmetry (Read First)",
    "Test Strategy Reasoning Protocol",
    "Completeness Verification (Mandatory)",
    "QA Report Length Bounds",
    "Two-Phase Verification",
    "Session Start (Blocking)",
    "Reasoning Protocol",
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

REQUIRED_AGENT_SECTIONS = {
    "qa": frozenset(
        {
            "Reviewer Asymmetry (Read First)",
            "Completeness Verification (Mandatory)",
        }
    ),
}

# Sections that legitimately exist on only one platform side.
# Key: (agent_name, section_name) -> (expected_side, rationale).
# expected_side is "claude" or "vscode": the side the section is declared to
# live on. A section listed here is reported as "declared adapter" and does
# not fail ONLY when it is actually missing from the declared side (i.e. it is
# present on the OTHER side and absent on `expected_side`). If the same
# section name shows up missing in the opposite direction instead (present on
# `expected_side`, absent from the other), that is undeclared drift and still
# fails: the exception does not cover an inverted gap. See Issue #4852 review.
_CLAUDE_TOOLS_RATIONALE = "Claude-specific runtime; no Copilot equivalent."

PLATFORM_ONLY_SECTIONS: dict[tuple[str, str], tuple[str, str]] = {
    # Claude Code Tools is Claude-specific runtime surface: declared present
    # on the Claude side, absent on the VS Code/Copilot side.
    ("implementer", "Claude Code Tools"): ("claude", _CLAUDE_TOOLS_RATIONALE),
    ("architect", "Claude Code Tools"): ("claude", _CLAUDE_TOOLS_RATIONALE),
    ("analyst", "Claude Code Tools"): ("claude", _CLAUDE_TOOLS_RATIONALE),
    ("qa", "Claude Code Tools"): ("claude", _CLAUDE_TOOLS_RATIONALE),
    ("critic", "Claude Code Tools"): ("claude", _CLAUDE_TOOLS_RATIONALE),
    ("orchestrator", "Claude Code Tools"): ("claude", _CLAUDE_TOOLS_RATIONALE),
    ("merge-resolver", "Claude Code Tools"): ("claude", _CLAUDE_TOOLS_RATIONALE),
    ("security", "Claude Code Tools"): ("claude", _CLAUDE_TOOLS_RATIONALE),
    ("retrospective", "Claude Code Tools"): ("claude", _CLAUDE_TOOLS_RATIONALE),
}

# Shared-template install-copy comparison label.
_INSTALL_COMPARISON_LABEL = ".claude/agents vs .github/agents"

# Accepted, pre-existing drift baselines (Issue #2374).
#
# A Claude agent and its VS Code/Copilot counterpart may legitimately diverge
# in content (the Claude agents are not generated from the shared templates;
# see module docstring). When that divergence is a known, accepted design
# difference rather than accidental rot, record it here with its measured
# similarity floor so the gate stops failing on a clean checkout while still
# catching NEW drift.
#
# Contract: an agent and comparison pair listed here is reported as
# "OK (baselined)" and excluded from the failing drift count ONLY while its
# overall similarity stays at or above the recorded floor. If it drifts further
# (similarity drops below the floor), it fails again, so the baseline cannot
# silently hide regressions. The comparison label is part of the key so a
# source-vendored baseline cannot hide install-copy drift.
#
# merge-resolver: src/claude/merge-resolver.md is the tier-hierarchy-enriched
# prompt (PR #1426) with Core Mission / Key Responsibilities / Execution
# Mindset / Handoff Protocol / Memory Protocol sections that the shared
# template (templates/agents/merge-resolver.shared.md), and therefore the
# generated VS Code copy, does not carry. Reconciling the two would rewrite an
# agent prompt and change agent behavior (architect review, out of scope for a
# baseline-green fix). Floor is set to the measured 20.7% so the existing
# structure is accepted but any worsening still blocks. Re-measured for issue
# #5074: the add/add rename-never-content-merge rule was added with identical
# wording to both sides, which shifted the Jaccard section scores from the
# prior 20.9% because the two shapes carry different surrounding prose.
#
# merge-resolver install copy (Issue #2715): the same tier-hierarchy enrichment
# lives only in the Claude Code self-host copy (.claude/agents/merge-resolver.md);
# the GitHub Copilot self-host copy (.github/agents/merge-resolver.agent.md)
# carries the leaner generated prose. The other ten diverged install copies were
# reconciled by resyncing .github from the generated src/copilot-cli output, but
# merge-resolver cannot be: its richness is on the .claude side by design, so a
# resync would delete substantive Claude-only instructions. Floor is the measured
# 20.7% (identical to the vendored floor because both compare the same enriched
# .claude body against the same leaner template-derived body). Any worsening still
# blocks.
KNOWN_BASELINE_DRIFT: dict[tuple[str, str], float] = {
    ("merge-resolver", "src-claude vs src-vscode"): 20.7,
    ("merge-resolver", _INSTALL_COMPARISON_LABEL): 20.7,
}

# Pre-existing missing sections at the time section inventory was added
# (Issue #4852). Each tuple is (agent_name, section_name, comparison_label).
# A missing section in this set is reported as "MISSING (baselined)" and does
# not block. Removing an entry here re-enables the gate for that section.
# New missing sections NOT in this set will fail immediately.
KNOWN_MISSING_SECTIONS: frozenset[tuple[str, str, str]] = frozenset({
    ("analyst", "Degraded Mode Protocol", ".claude/agents vs .github/agents"),
    ("analyst", "Degraded Mode Protocol", "src-claude vs src-vscode"),
    ("architect", "ADR and Design Review Length Bounds", ".claude/agents vs .github/agents"),
    ("architect", "Architecture Reasoning Protocol", ".claude/agents vs .github/agents"),
    ("architect", "Ask Before vs Proceed With Default", ".claude/agents vs .github/agents"),
    ("architect", "Degraded Mode Protocol", ".claude/agents vs .github/agents"),
    ("architect", "Degraded Mode Protocol", "src-claude vs src-vscode"),
    ("architect", "Legacy Modernization Patterns", ".claude/agents vs .github/agents"),
    ("architect", "Legacy Modernization Patterns", "src-claude vs src-vscode"),
    ("architect", "Reversibility Assessment", ".claude/agents vs .github/agents"),
    ("architect", "Reversibility Assessment", "src-claude vs src-vscode"),
    ("architect", "Strategic Architecture Principles", ".claude/agents vs .github/agents"),
    ("architect", "Strategic Architecture Principles", "src-claude vs src-vscode"),
    ("architect", "Strategic Knowledge Available", ".claude/agents vs .github/agents"),
    ("architect", "Strategic Knowledge Available", "src-claude vs src-vscode"),
    ("backlog-generator", "Claude Code Tools", ".claude/agents vs .github/agents"),
    ("backlog-generator", "Claude Code Tools", "src-claude vs src-vscode"),
    ("code-reviewer", "Claude Code Tools", ".claude/agents vs .github/agents"),
    ("code-reviewer", "Claude Code Tools", "src-claude vs src-vscode"),
    ("code-reviewer", "Tool Use", ".claude/agents vs .github/agents"),
    ("code-reviewer", "Tool Use", "src-claude vs src-vscode"),
    ("critic", "Degraded Mode Protocol", "src-claude vs src-vscode"),
    ("devops", "12-Factor App Principles for CI/CD", ".claude/agents vs .github/agents"),
    ("devops", "12-Factor App Principles for CI/CD", "src-claude vs src-vscode"),
    ("devops", "Claude Code Tools", ".claude/agents vs .github/agents"),
    ("devops", "Claude Code Tools", "src-claude vs src-vscode"),
    ("devops", "Local CI Simulation", ".claude/agents vs .github/agents"),
    ("devops", "Local CI Simulation", "src-claude vs src-vscode"),
    ("devops", "Pipeline Metrics", ".claude/agents vs .github/agents"),
    ("devops", "Pipeline Metrics", "src-claude vs src-vscode"),
    ("devops", "Script Language Priority", ".claude/agents vs .github/agents"),
    ("devops", "Script Language Priority", "src-claude vs src-vscode"),
    ("high-level-advisor", "Claude Code Tools", ".claude/agents vs .github/agents"),
    ("high-level-advisor", "Claude Code Tools", "src-claude vs src-vscode"),
    ("implementer", "Degraded Mode Protocol", ".claude/agents vs .github/agents"),
    ("implementer", "Degraded Mode Protocol", "src-claude vs src-vscode"),
    ("independent-thinker", "Claude Code Tools", ".claude/agents vs .github/agents"),
    ("independent-thinker", "Claude Code Tools", "src-claude vs src-vscode"),
    ("independent-thinker", "Output Format", ".claude/agents vs .github/agents"),
    ("independent-thinker", "Output Format", "src-claude vs src-vscode"),
    ("independent-thinker", "Persona Traits", ".claude/agents vs .github/agents"),
    ("independent-thinker", "Persona Traits", "src-claude vs src-vscode"),
    ("independent-thinker", "Verification Protocol", ".claude/agents vs .github/agents"),
    ("independent-thinker", "Verification Protocol", "src-claude vs src-vscode"),
    ("independent-thinker", "When to Use", ".claude/agents vs .github/agents"),
    ("independent-thinker", "When to Use", "src-claude vs src-vscode"),
    ("merge-resolver", "Activation Profile", ".claude/agents vs .github/agents"),
    ("merge-resolver", "Activation Profile", "src-claude vs src-vscode"),
    ("merge-resolver", "Auto-Resolution Script", ".claude/agents vs .github/agents"),
    ("merge-resolver", "Auto-Resolution Script", "src-claude vs src-vscode"),
    ("merge-resolver", "Core Mission", ".claude/agents vs .github/agents"),
    ("merge-resolver", "Core Mission", "src-claude vs src-vscode"),
    ("merge-resolver", "Execution Mindset", ".claude/agents vs .github/agents"),
    ("merge-resolver", "Execution Mindset", "src-claude vs src-vscode"),
    ("merge-resolver", "Handoff Options", ".claude/agents vs .github/agents"),
    ("merge-resolver", "Handoff Options", "src-claude vs src-vscode"),
    ("merge-resolver", "Handoff Protocol", ".claude/agents vs .github/agents"),
    ("merge-resolver", "Handoff Protocol", "src-claude vs src-vscode"),
    ("merge-resolver", "Key Responsibilities", ".claude/agents vs .github/agents"),
    ("merge-resolver", "Key Responsibilities", "src-claude vs src-vscode"),
    ("merge-resolver", "Memory Protocol", ".claude/agents vs .github/agents"),
    ("merge-resolver", "Memory Protocol", "src-claude vs src-vscode"),
    ("pr-comment-responder", "Claude Code Tools", ".claude/agents vs .github/agents"),
    ("pr-comment-responder", "Claude Code Tools", "src-claude vs src-vscode"),
    ("pr-comment-responder", "GitHub Skill", ".claude/agents vs .github/agents"),
    ("pr-comment-responder", "GitHub Skill", "src-claude vs src-vscode"),
    ("pr-comment-responder", "GitHub Skill Integration", ".claude/agents vs .github/agents"),
    ("pr-comment-responder", "GitHub Skill Integration", "src-claude vs src-vscode"),
    ("qa", "Degraded Mode Protocol", ".claude/agents vs .github/agents"),
    ("qa", "Degraded Mode Protocol", "src-claude vs src-vscode"),
    ("qa", "Test Commands", ".claude/agents vs .github/agents"),
    ("qa", "Test Commands", "src-claude vs src-vscode"),
    ("retrospective", "Handoff Routing Recommendations", ".claude/agents vs .github/agents"),
    ("retrospective", "Handoff Routing Recommendations", "src-claude vs src-vscode"),
    ("retrospective", "Structured Handoff Output (MANDATORY)", ".claude/agents vs .github/agents"),
    ("retrospective", "Structured Handoff Output (MANDATORY)", "src-claude vs src-vscode"),
    ("task-decomposer", "Claude Code Tools", ".claude/agents vs .github/agents"),
    ("task-decomposer", "Claude Code Tools", "src-claude vs src-vscode"),
    ("task-decomposer", "Handoff Options", ".claude/agents vs .github/agents"),
    ("task-decomposer", "Handoff Options", "src-claude vs src-vscode"),
    ("task-decomposer", "Output Format", ".claude/agents vs .github/agents"),
    ("task-decomposer", "Output Format", "src-claude vs src-vscode"),
    ("task-decomposer", "Task List Template", ".claude/agents vs .github/agents"),
    ("task-decomposer", "Task List Template", "src-claude vs src-vscode"),
})

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
    missing_sections: list[str] = field(default_factory=list)
    adapter_sections: list[str] = field(default_factory=list)
    comparison: str = "src-claude vs src-vscode"


def remove_yaml_frontmatter(content: str) -> str:
    """Remove YAML frontmatter from markdown content."""
    match = re.match(r"^---\r?\n[\s\S]*?\r?\n---\r?\n([\s\S]*)$", content)
    if match:
        return match.group(1)
    return content


# CommonMark fenced code block opener/closer: 0-3 leading spaces, then three
# or more of the SAME fence character (backtick or tilde). A closing fence
# must reuse the opening character and be at least as long as the opener, so
# a 4-backtick outer fence tolerates a 3-backtick line as ordinary content
# (see .github/agents/task-decomposer.agent.md for a real example) and a
# tilde fence never closes on a backtick line or vice versa.
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def get_markdown_sections(content: str) -> dict[str, str]:
    """Extract sections from markdown content based on ## headers.

    Headings inside fenced code blocks are ignored so that sample output
    templates do not pollute the section inventory. Fence detection follows
    CommonMark: backtick (```) and tilde (~~~) fences, up to 3 leading spaces
    of indentation (list-nested fences), and a closing fence must match the
    opening fence's character and be at least as long.
    """
    sections: dict[str, str] = {}
    current_section = "preamble"
    current_lines: list[str] = []
    fence_char: str | None = None
    fence_len = 0

    for line in content.splitlines():
        fence_match = _FENCE_RE.match(line)
        if fence_match:
            marker = fence_match.group(1)
            char, length = marker[0], len(marker)
            if fence_char is None:
                # Opening a new fence.
                fence_char = char
                fence_len = length
                current_lines.append(line)
                continue
            if char == fence_char and length >= fence_len:
                # Closing the open fence: same character, at least as long.
                fence_char = None
                fence_len = 0
                current_lines.append(line)
                continue
            # A different fence character, or a shorter same-character run,
            # is ordinary content inside the still-open outer fence.
            current_lines.append(line)
            continue

        if fence_char is not None:
            current_lines.append(line)
            continue

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


def _classify_overall(
    agent_name: str,
    overall: float,
    threshold: int,
    comparison: str = "src-claude vs src-vscode",
) -> str:
    """Classify an agent's overall similarity into a status string.

    Returns one of:
    - "OK": at or above the threshold.
    - "OK (baselined)": below the threshold but at or above a recorded
      baseline floor in ``KNOWN_BASELINE_DRIFT`` (accepted, tracked drift).
    - "DRIFT DETECTED": below the threshold and either not baselined or
      below its recorded floor (the drift got worse).
    """
    if overall >= threshold:
        return "OK"
    floor = KNOWN_BASELINE_DRIFT.get((agent_name, comparison))
    if floor is not None and overall >= floor:
        return "OK (baselined)"
    return "DRIFT DETECTED"


def compare_agent(
    claude_content: str,
    vscode_content: str,
    agent_name: str,
    threshold: int,
    comparison: str = "src-claude vs src-vscode",
) -> AgentResult:
    """Compare two agent files and return drift analysis.

    Two checks run:
    1. Content similarity for sections in SECTIONS_TO_COMPARE (legacy).
    2. Section inventory: any H2 section present on only one side fails
       unless listed in PLATFORM_ONLY_SECTIONS with a rationale.
    """
    claude_body = remove_yaml_frontmatter(claude_content)
    vscode_body = remove_yaml_frontmatter(vscode_content)

    claude_sections = get_markdown_sections(claude_body)
    vscode_sections = get_markdown_sections(vscode_body)
    required_sections = REQUIRED_AGENT_SECTIONS.get(agent_name, frozenset())

    section_results: list[SectionResult] = []
    total_similarity = 0.0
    compared_count = 0

    for section in SECTIONS_TO_COMPARE:
        claude_section = claude_sections.get(section)
        vscode_section = vscode_sections.get(section)

        if claude_section is None and vscode_section is None and section not in required_sections:
            continue

        claude_normalized = normalize_content(claude_section) if claude_section else ""
        vscode_normalized = normalize_content(vscode_section) if vscode_section else ""

        required_section_missing = section in required_sections and (
            not claude_normalized or not vscode_normalized
        )
        similarity = (
            0.0
            if required_section_missing
            else calculate_similarity(claude_normalized, vscode_normalized)
        )
        status = "DRIFT" if required_section_missing or similarity < threshold else "OK"

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

    # --- Section inventory: detect unlisted sections present on one side only ---
    # Exclude "preamble" (the content before the first heading).
    claude_heading_set = set(claude_sections.keys()) - {"preamble"}
    vscode_heading_set = set(vscode_sections.keys()) - {"preamble"}

    missing_sections: list[str] = []
    adapter_sections: list[str] = []

    only_in_claude = claude_heading_set - vscode_heading_set
    only_in_vscode = vscode_heading_set - claude_heading_set

    baselined_missing: list[str] = []

    for section in sorted(only_in_claude | only_in_vscode):
        key = (agent_name, section)
        baseline_key = (agent_name, section, comparison)
        adapter_entry = PLATFORM_ONLY_SECTIONS.get(key)
        actual_side = "claude" if section in only_in_claude else "vscode"
        # The exception only covers the declared side. A section that is
        # missing from its declared side but shows up unexplained on the
        # OTHER side (an inverted gap) is not exempted by this entry.
        if adapter_entry is not None and adapter_entry[0] == actual_side:
            adapter_sections.append(section)
        elif baseline_key in KNOWN_MISSING_SECTIONS:
            baselined_missing.append(section)
            section_results.append(
                SectionResult(
                    section=section,
                    similarity=0.0,
                    claude_has=section in claude_heading_set,
                    vscode_has=section in vscode_heading_set,
                    status="MISSING (baselined)",
                )
            )
        else:
            missing_sections.append(section)
            section_results.append(
                SectionResult(
                    section=section,
                    similarity=0.0,
                    claude_has=section in claude_heading_set,
                    vscode_has=section in vscode_heading_set,
                    status="MISSING",
                )
            )

    overall = round(total_similarity / compared_count, 1) if compared_count > 0 else 100.0
    drifting = [r.section for r in section_results if r.status == "DRIFT"]
    has_missing = len(missing_sections) > 0
    required_section_drift = any(section in required_sections for section in drifting)
    # A missing section (not covered by KNOWN_MISSING_SECTIONS or
    # PLATFORM_ONLY_SECTIONS above) always fails, even for an agent pair
    # baselined in KNOWN_BASELINE_DRIFT. That baseline exists to accept a
    # measured *content-similarity floor* for pre-existing structural
    # divergence; it must not silently swallow a brand-new missing section,
    # or the gate cannot catch new drift on a baselined pair (Issue #4852 AC:
    # "Existing baselines cannot suppress a newly missing section").
    overall_status = (
        "DRIFT DETECTED"
        if required_section_drift or has_missing
        else _classify_overall(agent_name, overall, threshold, comparison)
    )

    return AgentResult(
        agent_name=agent_name,
        overall_similarity=overall,
        status=overall_status,
        sections=section_results,
        drifting_sections=drifting,
        missing_sections=missing_sections,
        adapter_sections=adapter_sections,
        comparison=comparison,
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
    comparison_text = "Comparing: src/claude vs src/vs-code-agents"
    if any(result.comparison == _INSTALL_COMPARISON_LABEL for result in results):
        comparison_text += ", plus shared-template install copies"
    lines.append(comparison_text)
    lines.append(f"Similarity Threshold: {threshold}%")
    lines.append("")

    for result in sorted(results, key=lambda r: (r.comparison, r.agent_name)):
        if result.overall_similarity is not None:
            lines.append(
                f"{result.agent_name} [{result.comparison}]: "
                f"{result.status} ({result.overall_similarity}% similar)"
            )
        else:
            lines.append(f"{result.agent_name} [{result.comparison}]: {result.status}")

        for section in result.drifting_sections:
            lines.append(f'  - Section "{section}" differs (content drift)')
        for section in result.missing_sections:
            lines.append(f'  - Section "{section}" missing on one side')
        for section in result.adapter_sections:
            lines.append(f'  - Section "{section}" (declared adapter)')

    baselined_count = sum(1 for r in results if r.status == "OK (baselined)")

    lines.append("")
    lines.append("=== Summary ===")
    lines.append(f"Duration: {duration:.2f}s")
    lines.append(f"Agents compared: {len(results)}")
    lines.append(f"OK: {ok_count}")
    if baselined_count:
        lines.append(f"  (of which baselined: {baselined_count})")
    lines.append(f"Drift detected: {drift_count}")
    lines.append(f"No counterpart: {no_counterpart_count}")

    # Section-level counts
    total_missing = sum(len(r.missing_sections) for r in results)
    total_adapters = sum(len(r.adapter_sections) for r in results)
    total_content_drift = sum(
        1 for r in results for s in r.sections if s.status == "DRIFT"
    )
    lines.append(f"Missing sections: {total_missing}")
    lines.append(f"Content drift sections: {total_content_drift}")
    lines.append(f"Declared adapters: {total_adapters}")
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
    """Format results as JSON output.

    Carries the same three separated counts as ``format_text``: missing
    sections, content-drift sections, and declared adapters, both per-agent
    (``missingSections``/``adapterSections`` lists) and totalled in
    ``summary`` (``missingSections``/``contentDriftSections``/``adapterSections``).
    Consumers of this JSON (``scripts/ci/parse_drift_results.py``) read these
    fields to name a missing heading in the drift alert, not only content drift.
    """
    total_missing = sum(len(r.missing_sections) for r in results)
    total_adapters = sum(len(r.adapter_sections) for r in results)
    total_content_drift = sum(1 for r in results for s in r.sections if s.status == "DRIFT")

    output = {
        "duration": duration,
        "threshold": threshold,
        "summary": {
            "totalAgents": len(results),
            "ok": ok_count,
            "driftDetected": drift_count,
            "noCounterpart": no_counterpart_count,
            "missingSections": total_missing,
            "contentDriftSections": total_content_drift,
            "adapterSections": total_adapters,
        },
        "results": [
            {
                "agentName": r.agent_name,
                "comparison": r.comparison,
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
                "missingSections": r.missing_sections,
                "adapterSections": r.adapter_sections,
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
    total_missing = sum(len(r.missing_sections) for r in results)
    total_adapters = sum(len(r.adapter_sections) for r in results)
    total_content_drift = sum(1 for r in results for s in r.sections if s.status == "DRIFT")

    lines.append("| Metric | Count |")
    lines.append("|--------|-------|")
    lines.append(f"| Agents Compared | {len(results)} |")
    lines.append(f"| OK | {ok_count} |")
    lines.append(f"| Drift Detected | {drift_count} |")
    lines.append(f"| No Counterpart | {no_counterpart_count} |")
    lines.append(f"| Missing Sections | {total_missing} |")
    lines.append(f"| Content Drift Sections | {total_content_drift} |")
    lines.append(f"| Declared Adapters | {total_adapters} |")
    lines.append("")
    lines.append("## Results")
    lines.append("")
    lines.append(
        "| Agent | Comparison | Status | Similarity | Drifting Sections | Missing Sections |"
    )
    lines.append("|-------|------------|--------|------------|-------------------|-------------------|")

    for result in sorted(results, key=lambda r: (r.comparison, r.agent_name)):
        if result.overall_similarity is not None:
            similarity = f"{result.overall_similarity}%"
        else:
            similarity = "N/A"
        drifting = ", ".join(result.drifting_sections) if result.drifting_sections else "-"
        missing = ", ".join(result.missing_sections) if result.missing_sections else "-"
        lines.append(
            f"| {result.agent_name} | {result.comparison} | {result.status} "
            f"| {similarity} | {drifting} | {missing} |"
        )

    return "\n".join(lines)


# Directory-metadata files that live alongside agents but are not agents.
# Skipped in every comparison so they never count as NO COUNTERPART drift.
_NON_AGENT_FILENAMES: frozenset[str] = frozenset({"AGENTS", "CLAUDE"})


# Agent path roots (Issue #2423). Each entry maps a directory prefix to the
# filename suffix the agent files in that root use. The path-to-family helper
# strips the prefix to get the file's relative path, then strips the suffix to
# get the family (agent) name. Order does not matter; longer prefixes are
# matched first so ``src/copilot-cli/agents/`` wins over a hypothetical
# ``src/`` entry.
_AGENT_PATH_ROOTS: tuple[tuple[str, str], ...] = (
    (".claude/agents/", ".md"),
    (".github/agents/", ".agent.md"),
    ("src/claude/", ".md"),
    ("src/vs-code-agents/", ".agent.md"),
    ("src/copilot-cli/agents/", ".agent.md"),
    ("templates/agents/", ".shared.md"),
)


def _normalize_repo_relative(path: str, repo_root: Path | None) -> str:
    """Return ``path`` as a forward-slash repo-relative string.

    Accepts absolute paths (only when ``repo_root`` is supplied and the path
    sits inside it), repo-relative POSIX strings, and Windows-style backslash
    paths. Paths outside the repo and unparseable inputs return an empty
    string -- caller treats that as "no family".
    """
    if not path:
        return ""
    normalized = path.replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    if repo_root is not None:
        resolved_root = repo_root.resolve()
        candidate = Path(normalized)
        if not candidate.is_absolute():
            candidate = resolved_root / candidate
        try:
            return candidate.resolve().relative_to(resolved_root).as_posix()
        except ValueError:
            return ""
    return normalized.lstrip("/")


def families_from_paths(paths: Sequence[str], repo_root: Path | None = None) -> frozenset[str]:
    """Return the set of agent family names touched by ``paths`` (Issue #2423).

    A "family" is an agent's stem (e.g. ``analyst``, ``critic``), the unit the
    drift detector compares across platforms. ``paths`` may include any file in
    the diff -- non-agent paths are ignored. Paths under any of the known agent
    roots (``.claude/agents/``, ``.github/agents/``, ``src/claude/``,
    ``src/vs-code-agents/``, ``src/copilot-cli/agents/``, ``templates/agents/``)
    contribute their family. Directory metadata files (AGENTS.md, CLAUDE.md)
    and nested subdirectories (e.g. ``.claude/agents/security/foo.md`` -> foo)
    are handled correctly.

    Used by the pre-push hook to scope drift detection to the agent families
    actually touched by the push, instead of repo-wide.
    """
    families: set[str] = set()
    for raw in paths:
        rel = _normalize_repo_relative(raw, repo_root)
        if not rel:
            continue
        for prefix, suffix in _AGENT_PATH_ROOTS:
            if not rel.startswith(prefix):
                continue
            tail = rel[len(prefix) :]
            stem = Path(tail).name
            if not stem.endswith(suffix):
                continue
            family = stem[: -len(suffix)]
            if not family or family in _NON_AGENT_FILENAMES:
                continue
            families.add(family)
            break
    return frozenset(families)


def shared_template_names(templates_path: Path) -> frozenset[str]:
    """Return the stems of every ``templates/agents/{name}.shared.md`` source.

    These are the shared-template agents: the ones whose prose is meant to be
    the same across all install copies. Freestanding agents (no template) are
    excluded so a Claude-only or GitHub-only agent is not flagged as drift just
    because it lacks a counterpart.
    """
    return frozenset(p.name.removesuffix(".shared.md") for p in templates_path.glob("*.shared.md"))


def run_detection(
    claude_path: Path,
    vscode_path: Path,
    threshold: int,
    restrict_to: frozenset[str] | None = None,
    comparison: str = "src-claude vs src-vscode",
) -> list[AgentResult]:
    """Run drift detection and return results.

    Compares each ``claude_path/{name}.md`` against
    ``vscode_path/{name}.agent.md``. When ``restrict_to`` is given, only agents
    whose stem is in that set are compared, even when one side is missing.
    This scopes the install-copy comparison (``.claude/agents`` vs
    ``.github/agents``) to shared-template agents so freestanding agents are not
    flagged as missing a counterpart. ``comparison`` labels which pair the
    results came from.
    """
    results: list[AgentResult] = []

    if restrict_to is None:
        agent_names = sorted(p.stem for p in claude_path.glob("*.md"))
    else:
        agent_names = sorted(restrict_to)

    for agent_name in agent_names:
        if agent_name in _NON_AGENT_FILENAMES:
            continue
        claude_file = claude_path / f"{agent_name}.md"
        vscode_file = vscode_path / f"{agent_name}.agent.md"

        if not claude_file.exists() or not vscode_file.exists():
            results.append(
                AgentResult(
                    agent_name=agent_name,
                    overall_similarity=None,
                    status="NO COUNTERPART",
                    comparison=comparison,
                )
            )
            continue

        claude_content = claude_file.read_text(encoding="utf-8")
        vscode_content = vscode_file.read_text(encoding="utf-8")

        result = compare_agent(claude_content, vscode_content, agent_name, threshold, comparison)
        results.append(result)

    return results


# `src/claude/merge-resolver.md` carries Claude-specific conflict workflow
# detail that the generated VS Code/Copilot prompts intentionally keep shorter.
_ADVISORY_VENDORED_DRIFT: frozenset[str] = frozenset({"merge-resolver"})


def run_install_detection(
    templates_path: Path,
    claude_install_path: Path,
    github_install_path: Path,
    threshold: int,
    restrict_to: frozenset[str] | None = None,
) -> list[AgentResult]:
    """Compare hand-maintained install copies for shared-template agents.

    Issue #2267: ``.claude/agents``, ``.github/agents``, and ``src/claude`` are
    hand-maintained (no generator writes them; REQ-003-010 forbids generators
    under ``.claude/``). ``validate_install_parity.py`` already enforces that
    the install copies move together in a diff, but it does not check semantic
    similarity. This pass adds that check for shared-template agents: agents
    whose prose comes from ``templates/agents/{name}.shared.md``. Freestanding
    Claude-only or GitHub-only agents are skipped via ``restrict_to``.

    When ``restrict_to`` is supplied (Issue #2423 scoped-mode), the install
    comparison is further narrowed to the intersection of the changed families
    and the shared-template set, so a changed-files push cannot accidentally
    drag in pre-existing drift from an unrelated shared agent.
    """
    if not templates_path.is_dir():
        return []
    if not claude_install_path.is_dir() or not github_install_path.is_dir():
        return []

    shared_names = shared_template_names(templates_path)
    if not shared_names:
        return []

    effective = shared_names if restrict_to is None else shared_names & restrict_to
    if not effective:
        return []

    return run_detection(
        claude_install_path,
        github_install_path,
        threshold,
        restrict_to=effective,
        comparison=_INSTALL_COMPARISON_LABEL,
    )


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
    parser.add_argument(
        "--skip-install-comparison",
        action="store_true",
        help=(
            "Skip the .claude/agents vs .github/agents install-copy comparison "
            "(shared-template agents only). By default both comparisons run."
        ),
    )
    parser.add_argument(
        "--templates-path",
        type=Path,
        default=None,
        help=(
            "Path to the shared agent templates directory. Defaults to "
            "templates/agents. Used to scope the install-copy comparison to "
            "shared-template agents."
        ),
    )
    parser.add_argument(
        "--claude-install-path",
        type=Path,
        default=None,
        help="Path to the Claude Code install agents. Defaults to .claude/agents.",
    )
    parser.add_argument(
        "--github-install-path",
        type=Path,
        default=None,
        help="Path to the GitHub Copilot install agents. Defaults to .github/agents.",
    )
    parser.add_argument(
        "--fail-on-install-drift",
        action="store_true",
        help=(
            "Exit non-zero when the .claude/agents vs .github/agents install "
            "comparison finds CONTENT drift (an existing shared section whose "
            "text diverged). Default: install content drift is advisory "
            "(reported but does not change the exit code), because the two "
            "self-host copies have large pre-existing structural differences "
            "(Issue #2267). A MISSING section (an H2 present on only one "
            "side) always fails the install comparison too, with or without "
            "this flag. The vendored src comparison always affects the exit "
            "code."
        ),
    )
    parser.add_argument(
        "--changed",
        action="append",
        default=None,
        metavar="PATH",
        help=(
            "Repeatable. Restrict the comparison to the agent families touched "
            "by these paths (Issue #2423). Paths outside the known agent roots "
            "are ignored. When supplied without --all, the gate compares only "
            "those families, so unrelated pre-existing drift does not block a "
            "scoped push. If no path resolves to an agent family, the gate "
            "exits 0 -- nothing to check."
        ),
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help=(
            "Force repo-wide audit even when --changed is supplied. Use this "
            "for the weekly drift-detection workflow, the pre_pr.py audit, and "
            "any manual whole-repo invocation. With no scoping args, the gate "
            "already audits repo-wide (cron/manual default)."
        ),
    )
    return parser


def _resolve_scope(args: argparse.Namespace, repo_root: Path) -> tuple[frozenset[str] | None, bool]:
    """Resolve the family scope and whether the run is a no-op.

    Returns (restrict_to, no_op):
    - restrict_to=None -> repo-wide audit.
    - restrict_to=frozenset(...) -> scoped to those families.
    - no_op=True -> --changed was supplied but no path resolved to an agent
      family; caller should print a brief skip line and exit 0.
    """
    if args.all or not args.changed:
        return None, False
    families = families_from_paths(args.changed, repo_root=repo_root)
    if not families:
        return frozenset(), True
    return families, False


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

    templates_path = args.templates_path or (repo_root / "templates" / "agents")
    claude_install_path = args.claude_install_path or (repo_root / ".claude" / "agents")
    github_install_path = args.github_install_path or (repo_root / ".github" / "agents")

    if not args.skip_install_comparison:
        install_paths = (
            ("shared templates", templates_path),
            ("Claude install agents", claude_install_path),
            ("GitHub install agents", github_install_path),
        )
        missing_install_paths = [
            f"{label}: {path}" for label, path in install_paths if not path.is_dir()
        ]
        if missing_install_paths:
            print(
                "Error: install comparison path(s) not found:\n"
                + "\n".join(f"  - {path}" for path in missing_install_paths),
                file=sys.stderr,
            )
            return 2

    restrict_to, no_op = _resolve_scope(args, repo_root)
    if no_op:
        print(
            "Agent drift detection: --changed supplied but no path resolved "
            "to an agent family; skipping.",
        )
        return 0

    start_time = time.monotonic()
    results = run_detection(
        claude_path, vscode_path, args.similarity_threshold, restrict_to=restrict_to
    )
    install_results: list[AgentResult] = []
    if not args.skip_install_comparison:
        install_results = run_install_detection(
            templates_path,
            claude_install_path,
            github_install_path,
            args.similarity_threshold,
            restrict_to=restrict_to,
        )
        results.extend(install_results)
    duration = time.monotonic() - start_time

    drift_count = sum(1 for r in results if r.status == "DRIFT DETECTED")
    ok_count = sum(1 for r in results if r.status in ("OK", "OK (baselined)"))
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

    return _exit_code(results, fail_on_install=args.fail_on_install_drift)


def _exit_code(
    results: list[AgentResult],
    fail_on_install: bool,
) -> int:
    """Return 1 when blocking drift exists, else 0.

    Vendored (src) drift blocks except for agents listed in
    ``_ADVISORY_VENDORED_DRIFT``. Install (.claude/agents vs .github/agents)
    CONTENT drift (an existing shared section whose text diverged) is
    advisory by default, because the two self-host copies carry large
    pre-existing structural differences (Issue #2267); ``--fail-on-install-drift``
    promotes it to blocking once those are reconciled.

    A MISSING section (an H2 present on only one side, not covered by
    ``PLATFORM_ONLY_SECTIONS`` or ``KNOWN_MISSING_SECTIONS``) is always
    blocking in both comparisons, install included, and does not need
    ``--fail-on-install-drift``. Issue #4852's acceptance criterion is "a
    missing H2 section fails by default"; it names no install-copy carve-out,
    and the local pre-PR caller (``validate_agent_drift`` in
    ``scripts/validation/checks_tooling.py``) never passes
    ``--fail-on-install-drift``, so gating a new install-side missing section
    behind that flag would make it invisible to the local gate that everyone
    actually runs. Required agent sections are always blocking too, in both
    comparisons.
    """
    blocking_drift = any(
        (
            r.status == "DRIFT DETECTED"
            and (
                bool(
                    REQUIRED_AGENT_SECTIONS.get(r.agent_name, frozenset())
                    & set(r.drifting_sections)
                )
                or bool(r.missing_sections)
                or fail_on_install
                or r.comparison != _INSTALL_COMPARISON_LABEL
            )
            and not (
                r.comparison != _INSTALL_COMPARISON_LABEL
                and r.agent_name in _ADVISORY_VENDORED_DRIFT
                and not r.missing_sections
            )
        )
        or (
            fail_on_install
            and r.status == "NO COUNTERPART"
            and r.comparison == _INSTALL_COMPARISON_LABEL
        )
        for r in results
    )
    return 1 if blocking_drift else 0


if __name__ == "__main__":
    sys.exit(main())

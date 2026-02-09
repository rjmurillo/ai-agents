#!/usr/bin/env python3
"""Analyze skill content for optimal placement (Skill vs Passive Context vs Hybrid).

This script evaluates a skill's SKILL.md content or directory to classify whether
it should be:
- Skill: Action-heavy, tool execution, user-triggered workflows
- Passive Context: Knowledge-heavy, reference data, always-needed information
- Hybrid: Both knowledge (passive) and actions (skill)

Classification is based on Vercel research showing passive context achieves 100%
pass rates versus 53-79% for skills due to elimination of decision points.

Exit Codes:
    0: Success - Analysis complete
    1: Error - Invalid input or analysis failure

Based on:
    - .agents/analysis/vercel-passive-context-vs-skills-research.md
    - SKILL-QUICK-REF.md lines 152-203

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict


class Metrics(TypedDict):
    """Metrics for skill analysis."""

    tool_calls: int
    action_verbs: int
    reference_content_ratio: float
    user_triggers: int
    always_needed: int


class Recommendations(TypedDict):
    """Recommendations for hybrid content."""

    Passive: list[str]
    Skill: list[str]


class AnalysisResult(TypedDict):
    """Result of skill placement analysis."""

    classification: str
    confidence: int
    reasoning: str
    metrics: Metrics | None
    recommendations: Recommendations | None


@dataclass
class ClassificationScore:
    """Classification scoring data."""

    skill_score: int = 0
    passive_score: int = 0
    reasons: list[str] = field(default_factory=list)


def get_skill_content(path: Path) -> str:
    """Get content from skill directory or SKILL.md file.

    Args:
        path: Path to skill directory or SKILL.md file

    Returns:
        Content of SKILL.md file

    Raises:
        FileNotFoundError: If SKILL.md not found or path invalid
        ValueError: If path is not directory or .md file
        PermissionError: If path contains traversal sequences
    """
    # Prevent path traversal (CWE-22): detect malicious relative paths
    if ".." in path.parts:
        raise PermissionError(f"Path traversal attempt detected: {path}")

    # Resolve to absolute path for safe access
    resolved_path = path.resolve()

    if resolved_path.is_dir():
        skill_md = resolved_path / "SKILL.md"
        if not skill_md.exists():
            raise FileNotFoundError(f"SKILL.md not found in directory: {resolved_path}")
        return skill_md.read_text(encoding="utf-8")

    if not str(resolved_path).endswith(".md"):
        raise ValueError("Path must be a directory or .md file")

    return resolved_path.read_text(encoding="utf-8")


def measure_tool_calls(text: str) -> int:
    """Count tool execution calls in text.

    Args:
        text: Content to analyze

    Returns:
        Number of tool calls detected
    """
    tool_patterns = [
        r"\bBash\s*\(",
        r"\bRead\b",
        r"\bWrite\b",
        r"\bEdit\b",
        r"\bGrep\s*\(",
        r"\bGlob\s*\(",
        r"\bWebFetch\s*\(",
        r"\bWebSearch\s*\(",
        r"\bgh\s+\w+",
        r"\bgit\s+\w+",
        r"\bpwsh\s+",
        r"\bpython\s+",
        r"\bInvoke-\w+",
        r"\bSet-\w+",
        r"\bNew-\w+",
    ]

    count = 0
    for pattern in tool_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        count += len(matches)

    return count


def measure_action_verbs(text: str) -> int:
    """Count action verbs in text.

    Args:
        text: Content to analyze

    Returns:
        Number of action verbs detected
    """
    action_verbs = [
        r"\bcreate\b",
        r"\bupdate\b",
        r"\bdelete\b",
        r"\bexecute\b",
        r"\brun\b",
        r"\bmodify\b",
        r"\badd\b",
        r"\bremove\b",
        r"\bcommit\b",
        r"\bpush\b",
        r"\bmerge\b",
        r"\bclose\b",
        r"\bopen\b",
        r"\btrigger\b",
        r"\bgenerate\b",
        r"\bvalidate\b",
        r"\bpost\b",
        r"\bsend\b",
    ]

    count = 0
    for verb in action_verbs:
        matches = re.findall(verb, text, re.IGNORECASE)
        count += len(matches)

    return count


def measure_reference_content(text: str) -> float:
    """Calculate ratio of reference content to procedural content.

    Args:
        text: Content to analyze

    Returns:
        Ratio (0.0 to 1.0) where higher means more reference content
    """
    # Count reference indicators
    reference_indicators = 0
    reference_indicators += len(re.findall(r"^\|.*\|", text, re.MULTILINE))
    reference_indicators += len(re.findall(r"^[-*]\s+", text, re.MULTILINE))
    reference_indicators += len(re.findall(r"```", text, re.MULTILINE))

    # Count procedural indicators
    procedural_indicators = 0
    procedural_indicators += len(re.findall(r"^\d+\.\s+", text, re.MULTILINE))
    procedural_indicators += len(
        re.findall(r"(?:Phase|Step|Stage)\s+\d+", text, re.IGNORECASE)
    )

    total = reference_indicators + procedural_indicators
    if total == 0:
        return 0.5  # Neutral

    return reference_indicators / total


def detect_user_trigger_patterns(text: str) -> int:
    """Count user trigger patterns in text.

    Args:
        text: Content to analyze

    Returns:
        Number of user trigger patterns detected
    """
    trigger_patterns = [
        r"(?:when|if)\s+user",
        r"triggered\s+by",
        r"explicit\w*\s+request",
        r"slash\s*command",
        r"/\w+",
        r"invok\w+\s+(?:by|when)",
        r"user\s+asks?",
    ]

    count = 0
    for pattern in trigger_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        count += len(matches)

    return count


def detect_always_needed_patterns(text: str) -> int:
    """Count always-needed patterns in text.

    Args:
        text: Content to analyze

    Returns:
        Number of always-needed patterns detected
    """
    always_needed_patterns = [
        r"\balways\b",
        r"every\s+(?:turn|session)",
        r"required\s+(?:for|in)\s+all",
        r"\bmandatory\b",
        r"constant(?:ly)?",
        r"persistent",
        r"framework\s+knowledge",
        r"reference\s+data",
        r"decision\s+framework",
        r"routing\s+rules",
    ]

    count = 0
    for pattern in always_needed_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        count += len(matches)

    return count


def get_classification(
    tool_calls: int,
    action_verbs: int,
    reference_ratio: float,
    user_triggers: int,
    always_needed: int,
) -> tuple[str, int, list[str]]:
    """Determine classification based on metrics.

    Args:
        tool_calls: Number of tool calls
        action_verbs: Number of action verbs
        reference_ratio: Reference content ratio
        user_triggers: Number of user triggers
        always_needed: Number of always-needed patterns

    Returns:
        Tuple of (classification, confidence, reasons)
    """
    score = ClassificationScore()

    # Tool calls strongly indicate skill
    if tool_calls > 5:
        score.skill_score += 3
        score.reasons.append(f"High tool execution ({tool_calls} calls)")
    elif tool_calls > 0:
        score.skill_score += 1
        score.reasons.append(f"Some tool execution ({tool_calls} calls)")

    # Action verbs indicate skill
    if action_verbs > 10:
        score.skill_score += 2
        score.reasons.append(f"Many action verbs ({action_verbs})")
    elif action_verbs > 5:
        score.skill_score += 1
        score.reasons.append(f"Moderate action verbs ({action_verbs})")

    # Reference content indicates passive
    if reference_ratio > 0.7:
        score.passive_score += 3
        score.reasons.append(
            f"High reference content ratio ({reference_ratio:.2f})"
        )
    elif reference_ratio > 0.5:
        score.passive_score += 1
        score.reasons.append(
            f"Moderate reference content ({reference_ratio:.2f})"
        )

    # User triggers indicate skill
    if user_triggers > 3:
        score.skill_score += 2
        score.reasons.append(f"User-triggered workflow ({user_triggers} triggers)")

    # Always-needed patterns indicate passive
    if always_needed > 3:
        score.passive_score += 2
        score.reasons.append(f"Always-needed information ({always_needed} indicators)")

    # Determine classification
    diff = score.skill_score - score.passive_score

    if diff >= 3:
        classification = "Skill"
        confidence = min(90, 50 + diff * 10)
    elif diff <= -3:
        classification = "PassiveContext"
        confidence = min(90, 50 + abs(diff) * 10)
    else:
        classification = "Hybrid"
        confidence = 60
        score.reasons.append("Mixed indicators suggest hybrid approach")

    return classification, confidence, score.reasons


def get_hybrid_recommendations(
    text: str, classification: str
) -> Recommendations | None:
    """Get recommendations for hybrid content.

    Args:
        text: Content to analyze
        classification: Classification result

    Returns:
        Recommendations dict or None if not hybrid
    """
    if classification != "Hybrid":
        return None

    recommendations: Recommendations = {"Passive": [], "Skill": []}

    # Extract headings
    headings = re.findall(r"^#{1,3}\s+(.+)$", text, re.MULTILINE)

    for heading in headings:
        heading = heading.strip()

        # Classify heading content
        if re.search(
            r"routing|classification|framework|reference|index|hierarchy|decision",
            heading,
            re.IGNORECASE,
        ):
            recommendations["Passive"].append(heading)
        elif re.search(
            r"process|workflow|steps|execution|script|procedure",
            heading,
            re.IGNORECASE,
        ):
            recommendations["Skill"].append(heading)

    # Script references go to skill
    script_refs = re.findall(r"[\w-]+\.ps1", text)
    for script in script_refs:
        if script not in recommendations["Skill"]:
            recommendations["Skill"].append(script)

    return recommendations


def analyze_content(
    content: str, detailed: bool = False
) -> AnalysisResult:
    """Analyze content and classify placement.

    Args:
        content: Content to analyze
        detailed: Include detailed metrics in output

    Returns:
        Analysis result dict
    """
    # Calculate metrics
    tool_calls = measure_tool_calls(content)
    action_verbs = measure_action_verbs(content)
    reference_ratio = measure_reference_content(content)
    user_triggers = detect_user_trigger_patterns(content)
    always_needed = detect_always_needed_patterns(content)

    # Get classification
    classification, confidence, reasons = get_classification(
        tool_calls, action_verbs, reference_ratio, user_triggers, always_needed
    )

    # Build result
    result: AnalysisResult = {
        "classification": classification,
        "confidence": confidence,
        "reasoning": "; ".join(reasons),
        "metrics": None,
        "recommendations": None,
    }

    # Add metrics if detailed
    if detailed:
        result["metrics"] = {
            "tool_calls": tool_calls,
            "action_verbs": action_verbs,
            "reference_content_ratio": round(reference_ratio, 2),
            "user_triggers": user_triggers,
            "always_needed": always_needed,
        }

    # Add hybrid recommendations
    recommendations = get_hybrid_recommendations(content, classification)
    if recommendations:
        result["recommendations"] = recommendations

    return result


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 success, 1 error)
    """
    parser = argparse.ArgumentParser(
        description="Analyze skill content for optimal placement"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "-p",
        "--path",
        type=Path,
        help="Path to skill directory or SKILL.md file",
    )
    group.add_argument(
        "-c",
        "--content",
        type=str,
        help="Direct content string to analyze",
    )
    parser.add_argument(
        "-d",
        "--detailed",
        action="store_true",
        help="Include detailed metrics in output",
    )

    args = parser.parse_args()

    try:
        # Get content
        if args.path:
            content = get_skill_content(args.path)
        else:
            content = args.content

        # Analyze
        result = analyze_content(content, args.detailed)

        # Output JSON
        print(json.dumps(result, indent=2))

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

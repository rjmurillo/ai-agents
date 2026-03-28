#!/usr/bin/env python3
"""Inject research-before-implementation guidance for complex tasks.

Claude Code UserPromptSubmit hook that detects prompts describing
complex work (new subsystems, architectural changes, unfamiliar domains,
security-sensitive changes) and injects advisory guidance to research
constraints and prior art before writing code.

Hook Type: UserPromptSubmit
Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Always (educational injection, not blocking)
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root:
    _lib_dir = str(Path(_plugin_root).resolve() / "lib")
else:
    _lib_dir = str(Path(__file__).resolve().parents[2] / "lib")
if os.path.isdir(_lib_dir) and _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

try:
    from hook_utilities.guards import skip_if_consumer_repo  # noqa: E402
except ImportError:

    def skip_if_consumer_repo(hook_name: str) -> bool:  # type: ignore[misc]
        """Fallback: skip when .agents/ directory is absent."""
        project_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip() or str(Path.cwd())
        if not Path(project_dir, ".agents").is_dir():
            print(f"[SKIP] {hook_name}: .agents/ not found", file=sys.stderr)
            return True
        return False


# Patterns indicating complex work that benefits from research first.
# Each tuple: (compiled regex, short reason for the match).
COMPLEXITY_SIGNALS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"\b(?:new\s+subsystem|new\s+service|new\s+module|new\s+package)\b",
            re.IGNORECASE,
        ),
        "new subsystem",
    ),
    (
        re.compile(
            r"\b(?:architect(?:ure)?|redesign|rearchitect)\b",
            re.IGNORECASE,
        ),
        "architectural change",
    ),
    (
        re.compile(
            r"\b(?:cross[- ]repo|multi[- ]repo|monorepo\s+migration)\b",
            re.IGNORECASE,
        ),
        "cross-repo change",
    ),
    (
        re.compile(
            r"\b(?:auth(?:entication|orization)?|oauth|mfa|saml|jwt|credential)\b",
            re.IGNORECASE,
        ),
        "security-sensitive",
    ),
    (
        re.compile(
            r"\b(?:migration|migrate)\b",
            re.IGNORECASE,
        ),
        "migration",
    ),
    (
        re.compile(
            r"\b(?:breaking\s+change|deprecat(?:e|ion|ing))\b",
            re.IGNORECASE,
        ),
        "breaking change",
    ),
    (
        re.compile(
            r"\b(?:multiple\s+(?:approaches|options|ways)|trade[- ]?off)\b",
            re.IGNORECASE,
        ),
        "multiple approaches",
    ),
    (
        re.compile(
            r"\b(?:unfamiliar|first\s+time|never\s+(?:used|done|worked))\b",
            re.IGNORECASE,
        ),
        "unfamiliar domain",
    ),
]

# Patterns that indicate simple work where research is unnecessary.
SKIP_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(?:fix\s+(?:bug|typo|lint|test))\b", re.IGNORECASE),
    re.compile(r"\b(?:update\s+(?:docs?|readme|changelog))\b", re.IGNORECASE),
    re.compile(r"\b(?:bump\s+version|version\s+bump)\b", re.IGNORECASE),
    re.compile(r"\b(?:rename|reformat|lint)\b", re.IGNORECASE),
]

# Minimum prompt length to evaluate. Short prompts are unlikely to describe
# complex work worth researching.
MIN_PROMPT_LENGTH = 20


def detect_complexity(prompt: str) -> list[str]:
    """Return list of matched complexity reasons, empty if none."""
    if not prompt or len(prompt.strip()) < MIN_PROMPT_LENGTH:
        return []

    reasons: list[str] = []
    for pattern, reason in COMPLEXITY_SIGNALS:
        if pattern.search(prompt):
            reasons.append(reason)

    if reasons:
        return reasons

    for skip in SKIP_PATTERNS:
        if skip.search(prompt):
            return []

    return reasons


def build_research_guidance(reasons: list[str]) -> str:
    """Build the advisory message injected into context."""
    signals = ", ".join(reasons)
    return (
        f"\nResearch-then-Implement advisory (signals: {signals}). "
        "Before writing code, consider:\n"
        "1. Search Serena memories and ADRs for prior art on this topic.\n"
        "2. Identify constraints, dependencies, and affected consumers.\n"
        "3. Evaluate multiple approaches if applicable.\n"
        "4. Create a brief plan or spec before implementation.\n"
        "Use the brainstorming or planner skill if the task is non-trivial.\n"
    )


def extract_prompt(hook_input: dict[str, object]) -> str | None:
    """Extract user prompt from hook input with fallback for schema variations."""
    for key in ("prompt", "user_message_text", "message"):
        value = hook_input.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def main() -> int:
    """Main hook entry point. Returns exit code."""
    if skip_if_consumer_repo("research-then-implement"):
        return 0

    try:
        if sys.stdin.isatty():
            return 0

        input_json = sys.stdin.read()
        if not input_json.strip():
            return 0

        hook_input = json.loads(input_json)
    except (json.JSONDecodeError, ValueError) as exc:
        print(
            f"research_then_implement: Failed to parse input JSON: {exc}",
            file=sys.stderr,
        )
        return 0

    user_prompt = extract_prompt(hook_input)
    if not user_prompt:
        return 0

    reasons = detect_complexity(user_prompt)
    if reasons:
        print(build_research_guidance(reasons))

    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Enforce ADR-007 Memory-First Architecture and pre-PR validation on user prompts.

Claude Code UserPromptSubmit hook that:
1. Checks user prompts for planning/implementation keywords and injects memory-first reminder
2. Detects PR creation requests and injects pre-PR validation checklist
3. Detects GitHub CLI commands and injects skill-first reminders

Hook Type: UserPromptSubmit
Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Success, stdout added to Claude's context
    2 = Block prompt (not used here)
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# Keywords that suggest planning or implementation work
PLANNING_KEYWORDS: list[str] = [
    "plan",
    "implement",
    "design",
    "architect",
    "build",
    "create",
    "refactor",
    "fix",
    "add",
    "update",
    "feature",
    "issue",
    "pr",
]

# PR creation patterns
PR_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"create pr", re.IGNORECASE),
    re.compile(r"open pr", re.IGNORECASE),
    re.compile(r"submit pr", re.IGNORECASE),
    re.compile(r"make pr", re.IGNORECASE),
    re.compile(r"create pull request", re.IGNORECASE),
    re.compile(r"open pull request", re.IGNORECASE),
    re.compile(r"gh pr create", re.IGNORECASE),
    re.compile(r"push.*pr", re.IGNORECASE),
]

# GitHub CLI commands that should use skills instead
GH_CLI_PATTERNS: list[str] = [
    "gh pr create",
    "gh pr list",
    "gh pr view",
    "gh pr merge",
    "gh pr close",
    "gh pr checks",
    "gh pr review",
    "gh pr comment",
    "gh pr diff",
    "gh pr ready",
    "gh pr status",
    "gh issue create",
    "gh issue list",
    "gh issue view",
    "gh issue close",
    "gh issue comment",
    "gh issue edit",
    "gh api",
    "gh run",
    "gh workflow",
]


def is_valid_project_root(cwd: str) -> bool:
    """Check if the working directory is a valid project root."""
    indicators = [".claude/settings.json", ".git"]
    for indicator in indicators:
        if Path(os.path.join(cwd, indicator)).exists():
            return True
    return False


def check_planning_keywords(prompt: str) -> str | None:
    """Check for planning/implementation keywords and return reminder if found."""
    for keyword in PLANNING_KEYWORDS:
        pattern = re.compile(rf"\b{re.escape(keyword)}\b", re.IGNORECASE)
        if pattern.search(prompt):
            return "**ADR-007**: Query `memory-index` before proceeding. Evidence in session log."
    return None


def check_pr_keywords(prompt: str) -> str | None:
    """Check for PR creation keywords and return reminder if found."""
    for pattern in PR_PATTERNS:
        if pattern.search(prompt):
            return (
                "**Pre-PR gate**: Run tests, validate syntax, "
                "check memory naming (no `skill-` prefix). "
                "Read `validation-pre-pr-checklist` memory."
            )
    return None


def check_gh_cli_patterns(prompt: str) -> str | None:
    """Check for GitHub CLI commands and return skill-first reminder if found."""
    for cmd in GH_CLI_PATTERNS:
        pattern = re.compile(re.escape(cmd), re.IGNORECASE)
        if pattern.search(prompt):
            return (
                f"**Skill-first**: `{cmd}` detected. "
                "Read `.claude/skills/github/SKILL.md` for skill alternative."
            )
    return None


def main() -> int:
    """Main hook entry point. Returns exit code."""
    cwd = os.getcwd()
    if not is_valid_project_root(cwd):
        print(
            f"WARNING: Invoke-UserPromptMemoryCheck: CWD '{cwd}' does not appear "
            "to be a project root (missing .claude/settings.json or .git). "
            "Failing open.",
            file=sys.stderr,
        )
        return 0

    try:
        if sys.stdin.isatty():
            return 0

        input_json = sys.stdin.read()
        if not input_json.strip():
            return 0
    except (OSError, ValueError) as exc:
        print(
            f"WARNING: User prompt memory check: stdin read error: {exc}",
            file=sys.stderr,
        )
        return 0

    # Extract prompt text from JSON
    prompt_text = ""
    try:
        input_data = json.loads(input_json)
        prompt_value = input_data.get("prompt")
        if isinstance(prompt_value, str):
            prompt_text = prompt_value
    except (json.JSONDecodeError, ValueError):
        # If JSON parsing fails, use raw input as fallback
        prompt_text = input_json

    if not prompt_text.strip():
        return 0

    # Check for planning keywords
    planning_msg = check_planning_keywords(prompt_text)
    if planning_msg:
        print(planning_msg)

    # Check for PR creation keywords
    pr_msg = check_pr_keywords(prompt_text)
    if pr_msg:
        print(pr_msg)

    # Check for GitHub CLI commands
    gh_msg = check_gh_cli_patterns(prompt_text)
    if gh_msg:
        print(gh_msg)

    return 0


if __name__ == "__main__":
    sys.exit(main())

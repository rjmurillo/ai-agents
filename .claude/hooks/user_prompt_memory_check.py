#!/usr/bin/env python3
"""Enforces ADR-007 Memory-First Architecture and pre-PR validation on user prompts.

Claude Code hook that:
1. Checks user prompts for planning/implementation keywords and injects memory-first reminder
2. Detects PR creation requests and injects pre-PR validation checklist
3. Detects GitHub CLI commands and suggests skill alternatives

Receives JSON input via stdin containing the prompt text.
Part of the ADR-007 enforcement mechanism (Issue #729).

Hook Type: UserPromptSubmit
Exit Codes:
    0 = Success, stdout added to Claude's context
    2 = Block prompt (not used here)
"""

import json
import os
import re
import sys


def _is_valid_project_root(cwd: str) -> bool:
    """Check if cwd has .claude/settings.json or .git."""
    indicators = [".claude/settings.json", ".git"]
    for indicator in indicators:
        if os.path.exists(os.path.join(cwd, indicator)):
            return True
    return False


PLANNING_KEYWORDS = [
    "plan", "implement", "design", "architect", "build",
    "create", "refactor", "fix", "add", "update",
    "feature", "issue", "pr",
]

PR_KEYWORDS = [
    r"create pr", r"open pr", r"submit pr", r"make pr",
    r"create pull request", r"open pull request",
    r"gh pr create", r"push.*pr",
]

GH_CLI_PATTERNS = [
    "gh pr create", "gh pr list", "gh pr view", "gh pr merge",
    "gh pr close", "gh pr checks", "gh pr review", "gh pr comment",
    "gh pr diff", "gh pr ready", "gh pr status",
    "gh issue create", "gh issue list", "gh issue view",
    "gh issue close", "gh issue comment", "gh issue edit",
    "gh api", "gh run", "gh workflow",
]


def main() -> int:
    """Main hook entry point. Returns exit code."""
    cwd = os.getcwd()

    if not _is_valid_project_root(cwd):
        print(
            f"Invoke-UserPromptMemoryCheck: CWD '{cwd}' does not appear to be "
            "a project root. Failing open.",
            file=sys.stderr,
        )
        return 0

    input_text = sys.stdin.read()
    prompt_text = ""

    try:
        input_data = json.loads(input_text)
        if isinstance(input_data, dict):
            prompt_text = input_data.get("prompt", "")
    except (json.JSONDecodeError, TypeError, AttributeError):
        # If JSON parsing fails, use raw input as fallback
        prompt_text = input_text

    # Check for planning/implementation keywords
    match_found = False
    for keyword in PLANNING_KEYWORDS:
        if re.search(rf"(?i)\b{keyword}\b", prompt_text):
            match_found = True
            break

    if match_found:
        print(
            "\n**ADR-007 Memory Check**: Before proceeding with this task:\n\n"
            "- Query ``memory-index`` for task-relevant memories\n"
            "- Check Forgetful for cross-project patterns if applicable\n"
            "- Evidence memory retrieval in session log\n"
        )

    # Check for PR creation keywords
    pr_match_found = False
    for pattern in PR_KEYWORDS:
        if re.search(rf"(?i){pattern}", prompt_text):
            pr_match_found = True
            break

    if pr_match_found:
        print(
            "\n**Pre-PR Validation Gate**: Before creating a PR, complete "
            "these checks:\n\n"
            "1. **Run local tests**: "
            "``Invoke-Pester -Path 'tests/*.Tests.ps1'``\n"
            "2. **Validate script syntax**: "
            "All .ps1 files must parse without errors\n"
            "3. **Check memory naming**: "
            "No ``skill-`` prefix in ``.serena/memories/`` (ADR-017)\n"
            "4. **Read validation memory**: "
            "``mcp__serena__read_memory`` with "
            '``memory_file_name="validation-pre-pr-checklist"``\n\n'
            "**Do NOT run markdownlint on .ps1 files** - "
            "it corrupts PowerShell comment terminators\n"
        )

    # Check for GitHub CLI usage
    gh_cli_match_found = False
    matched_command = ""
    for pattern in GH_CLI_PATTERNS:
        if re.search(rf"(?i){re.escape(pattern)}", prompt_text):
            gh_cli_match_found = True
            matched_command = pattern
            break

    if gh_cli_match_found:
        print(
            f"\n**Skill Usage Check**: Detected potential "
            f"``{matched_command}`` usage.\n\n"
            "Before using raw ``gh`` CLI, read the GitHub skills "
            "documentation:\n\n"
            "``Read .claude/skills/github/SKILL.md``\n\n"
            "**Available skill categories**:\n"
            "- PR operations: get_pr_context.py, get_pr_checks.py, "
            "post_pr_comment_reply.py, etc.\n"
            "- Issue operations: New-Issue, Post-IssueComment, "
            "Set-IssueLabels, etc.\n"
            "- Reactions: Add-CommentReaction\n\n"
            "Using skills ensures consistent error handling "
            "and audit logging.\n"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Auto-approve test execution commands to reduce permission fatigue.

Claude Code PermissionRequest hook that automatically approves safe test
execution commands (pytest, npm test, dotnet test, etc.) without user
intervention. Eliminates repetitive permission prompts for known-safe
operations.

Hook Type: PermissionRequest
Matcher: Bash(pwsh*Invoke-Pester*|npm test*|npm run test*|pnpm test*|
         yarn test*|pytest*|python*pytest*|dotnet test*|mvn test*|
         gradle test*|cargo test*|go test*)
Exit Codes:
    0 = Always (non-blocking hook, all errors are warnings)

Related:
    .agents/analysis/claude-code-hooks-opportunity-analysis.md
"""

import json
import re
import sys


DANGEROUS_METACHARS = (";", "|", "&", "<", ">", "$", "`", "\n", "\r")

SAFE_TEST_PATTERNS = [
    r"^pwsh\s+.*Invoke-Pester",
    r"^npm\s+test",
    r"^npm\s+run\s+test",
    r"^pnpm\s+test",
    r"^yarn\s+test",
    r"^pytest(\s|$)",
    r"^python\s+.*pytest",
    r"^dotnet\s+test",
    r"^mvn\s+test",
    r"^gradle\s+test",
    r"^cargo\s+test",
    r"^go\s+test",
]


def get_command_from_input(hook_input: dict) -> str | None:
    """Extract command string from hook input."""
    tool_input = hook_input.get("tool_input")
    if isinstance(tool_input, dict):
        command = tool_input.get("command")
        if isinstance(command, str):
            return command
    return None


def is_safe_test_command(command: str) -> bool:
    """Check if command matches a known safe test pattern.

    Rejects commands with dangerous shell metacharacters first,
    then checks against known safe test framework patterns.
    """
    for char in DANGEROUS_METACHARS:
        if char in command:
            print(
                f"Test auto-approval: Rejected command containing "
                f"dangerous metacharacter '{repr(char)}': {command}",
                file=sys.stderr,
            )
            return False

    for pattern in SAFE_TEST_PATTERNS:
        try:
            if re.search(pattern, command):
                return True
        except re.error:
            print(
                f"Test auto-approval: Invalid regex pattern '{pattern}'",
                file=sys.stderr,
            )
            continue

    return False


def main() -> None:
    """Entry point for the test auto-approval hook."""
    try:
        if sys.stdin.isatty():
            sys.exit(0)

        input_text = sys.stdin.read()
        if not input_text or not input_text.strip():
            sys.exit(0)

        hook_input = json.loads(input_text)
        command = get_command_from_input(hook_input)

        if not command:
            sys.exit(0)

        if is_safe_test_command(command):
            response = json.dumps({
                "decision": "approve",
                "reason": "Auto-approved test execution (safe read-only operation)",
            })
            print(response)

        sys.exit(0)

    except Exception as exc:
        print(
            f"Test auto-approval check failed: {type(exc).__name__} - {exc}",
            file=sys.stderr,
        )
        print(
            f"\n**Test Auto-Approval Hook ERROR**: Auto-approval failed. "
            f"You'll see standard permission prompts. Error: {exc}\n"
        )
        sys.exit(0)


if __name__ == "__main__":
    main()

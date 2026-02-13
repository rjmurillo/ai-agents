#!/usr/bin/env python3
"""Auto-approve test execution commands to reduce permission fatigue.

Claude Code PermissionRequest hook that automatically approves safe test
execution commands (Invoke-Pester, npm test, pytest, etc.) without user
intervention.

Hook Type: PermissionRequest
Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Always (non-blocking hook, all errors are warnings)
"""

from __future__ import annotations

import json
import re
import sys

# Shell metacharacters that indicate compound/dangerous commands
DANGEROUS_METACHARACTERS: tuple[str, ...] = (
    ";",
    "|",
    "&",
    "<",
    ">",
    "$",
    "`",
    "\n",
    "\r",
)

# Safe test command patterns (anchored to start of command)
SAFE_TEST_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^pwsh\s+.*Invoke-Pester"),
    re.compile(r"^npm\s+test"),
    re.compile(r"^npm\s+run\s+test"),
    re.compile(r"^pnpm\s+test"),
    re.compile(r"^yarn\s+test"),
    re.compile(r"^pytest(\s|$)"),
    re.compile(r"^python\s+.*pytest"),
    re.compile(r"^dotnet\s+test"),
    re.compile(r"^mvn\s+test"),
    re.compile(r"^gradle\s+test"),
    re.compile(r"^cargo\s+test"),
    re.compile(r"^go\s+test"),
]


def get_command_from_input(hook_input: dict[str, object]) -> str | None:
    """Extract command from hook input's tool_input."""
    tool_input = hook_input.get("tool_input")
    if isinstance(tool_input, dict):
        command = tool_input.get("command")
        if isinstance(command, str) and command.strip():
            return command.strip()
    return None


def is_safe_test_command(command: str) -> bool:
    """Check if the command is a safe test execution command.

    Rejects commands containing shell metacharacters to prevent injection.
    Only approves commands matching known test framework patterns.
    """
    for char in DANGEROUS_METACHARACTERS:
        if char in command:
            print(
                f"WARNING: Test auto-approval: Rejected command containing "
                f"dangerous metacharacter {char!r}: {command}",
                file=sys.stderr,
            )
            return False

    for pattern in SAFE_TEST_PATTERNS:
        if pattern.search(command):
            return True

    return False


def main() -> int:
    """Main hook entry point. Returns exit code."""
    try:
        if sys.stdin.isatty():
            return 0

        input_json = sys.stdin.read()
        if not input_json.strip():
            return 0

        hook_input = json.loads(input_json)
    except (json.JSONDecodeError, ValueError):
        return 0

    command = get_command_from_input(hook_input)
    if not command:
        return 0

    if is_safe_test_command(command):
        response = json.dumps(
            {
                "decision": "approve",
                "reason": "Auto-approved test execution (safe read-only operation)",
            }
        )
        print(response)

    return 0


if __name__ == "__main__":
    sys.exit(main())

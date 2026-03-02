#!/usr/bin/env python3
"""UserPromptSubmit hook that detects keywords signaling autonomous execution.

When autonomy keywords are detected, injects stricter protocol guards into context:
- Requires explicit session log evidence
- Enforces multi-agent consensus gates
- Injects audit trail requirements
- Warns about blocked high-risk operations (merge, delete)

Prevents accidental autonomous failures by making protocol requirements explicit
before execution begins.

Part of Tier 2 enforcement hooks (Issue #773, Autonomous safety).

Hook Type: UserPromptSubmit
Exit Codes:
    0 = Success (context injected or keywords not detected)

See: .agents/SESSION-PROTOCOL.md, .agents/governance/PROJECT-CONSTRAINTS.md
"""

import json
import re
import sys
from datetime import date


# Keywords signaling autonomous/unattended execution
AUTONOMY_PATTERNS: list[str] = [
    r"\bautonomous\b",
    r"\bhands-off\b",
    r"\bwithout asking\b",
    r"\bwithout confirmation\b",
    r"\bauto-\w+",
    r"\bunattended\b",
    r"\brun autonomously\b",
    r"\bfull autonomy\b",
    r"\bno human\b",
    r"\bno verification\b",
    r"\bblindly\b",
]


def has_autonomy_keywords(prompt: str) -> bool:
    """Test if prompt contains autonomy-signaling keywords.

    Returns True if any autonomy keyword pattern matches.
    """
    if not prompt or not prompt.strip():
        return False

    for pattern in AUTONOMY_PATTERNS:
        if re.search(pattern, prompt, re.IGNORECASE):
            return True

    return False


def extract_user_prompt(hook_input: dict) -> str | None:
    """Extract user prompt with fallback for schema variations."""
    for key in ("prompt", "user_message_text", "message"):
        value = hook_input.get(key)
        if value and isinstance(value, str) and value.strip():
            return value
    return None


def format_autonomous_warning() -> str:
    """Format the autonomous execution warning message."""
    today = date.today().isoformat()
    return f"""
## AUTONOMOUS EXECUTION DETECTED

You have signaled autonomous/unattended execution. This mode enforces STRICTER protocol:

### Session Log Requirement (MANDATORY)
- Must have session log for today (`.agents/sessions/{today}-session-NN.json`)
- Session log must evidence memory retrieval (Serena activation, HANDOFF.md read)
- Session log must evidence all major decisions

### Multi-Agent Consensus Gates
High-risk operations REQUIRE multi-agent review BEFORE execution:
- PR merge, force push, branch delete
- Database migrations
- Infrastructure changes
- Config changes affecting production

Use `/orchestrator` to engage consensus gates.

### Audit Trail Requirements
Autonomous execution MUST log:
- Reason for autonomy request
- Decision rationale (from session log)
- Review gates passed/bypassed
- Exact commands executed
- Outcomes and any failures

### Blocked Operations in Autonomous Mode
These operations are BLOCKED in autonomous execution:
- `git push --force`
- `git branch -D <branch>`
- `gh pr merge --delete-branch`
- Any operation on `main` branch
- Any operation affecting CI/CD workflows

### Proceed Only If:
1. Session log exists with full evidence
2. All decisions logged in session
3. High-risk operations will use consensus gates
4. You understand audit trail requirements

**This is not a block - proceed at your own risk if requirements aren't met.**

See: `.agents/SESSION-PROTOCOL.md` for full autonomous execution protocol.
"""


def main() -> int:
    """Main hook execution. Always returns 0."""
    try:
        # Read JSON input from stdin
        if sys.stdin.isatty():
            return 0

        input_text = sys.stdin.read()
        if not input_text or not input_text.strip():
            return 0

        hook_input = json.loads(input_text)
        user_prompt = extract_user_prompt(hook_input)

        if not user_prompt:
            return 0

        if not has_autonomy_keywords(user_prompt):
            return 0

        # Autonomy keywords detected, inject stricter protocol
        print(format_autonomous_warning())
        return 0

    except Exception as exc:
        # Fail-open on errors
        print(f"Autonomous execution detector error: {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())

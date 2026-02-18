#!/usr/bin/env python3
"""Post-response hook for stuck detection.

Checks agent responses for repetitive topic loops and injects nudges.
"""

import json
import sys

from semantic_hooks.guards import StuckDetectionGuard, create_stuck_guard_from_config


def main() -> int:
    """Run post-response stuck detection check."""
    # Read response from stdin
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        # No valid JSON input
        return 0

    response_text = data.get("response", "") or data.get("tool_result", "") or ""
    if not response_text:
        return 0

    # Create guard from config
    guard = create_stuck_guard_from_config()

    # Build a minimal context for checking
    from semantic_hooks.core import HookContext, HookEvent

    context = HookContext(
        event=HookEvent.POST_TOOL_USE,
        tool_result=response_text,
        session_id=data.get("session_id", ""),
    )

    result = guard.check(context)

    # Output result if there's a message or context to inject
    if result.message or result.additional_context:
        output = result.to_stdout_json()
        print(json.dumps(output))

    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())

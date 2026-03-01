#!/usr/bin/env python3
"""Post-response hook for stuck detection.

Checks agent responses for repetitive topic loops and injects nudges.
"""

import os
import sys

# Resolve package path: works as both a .claude/ repo skill and a marketplace plugin
_plugin_root = os.environ.get('CLAUDE_PLUGIN_ROOT', '')
if _plugin_root:
    _src = os.path.join(_plugin_root, 'src')
else:
    _src = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src')
_src = os.path.normpath(_src)
if _src not in sys.path:
    sys.path.insert(0, _src)

import json  # noqa: E402

from semantic_hooks.guards import create_stuck_guard_from_config  # noqa: E402
from semantic_hooks.logging import log  # noqa: E402


def main() -> int:
    """Run post-response stuck detection check."""
    try:
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
            event=HookEvent.POST_RESPONSE,
            tool_result=response_text,
            session_id=data.get("session_id", ""),
        )

        result = guard.check(context)

        # Output result if there's a message or context to inject
        if result.message or result.additional_context:
            output = result.to_stdout_json()
            print(json.dumps(output))

        return result.exit_code

    except Exception as e:
        log(f"PostResponse ERROR: {e}")
        # Fail closed: security-relevant hooks should not silently pass on error
        return 2

if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Claude Code PostToolUse hook - semantic node recorder."""

import json
import sys

from semantic_hooks.core import HookContext, HookEvent
from semantic_hooks.recorder import create_recorder_from_config
from semantic_hooks.logging import log


def main() -> int:
    """Main entry point for PostToolUse hook."""
    try:
        # Read input from Claude
        input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {}

        # Create context
        context = HookContext.from_stdin_json(input_data, HookEvent.POST_TOOL_USE)

        # Run recorder
        recorder = create_recorder_from_config()
        result = recorder.record(context)

        # Output response
        output = result.to_stdout_json()
        if output:
            print(json.dumps(output))

        # Log
        if result.node:
            log(f"PostToolUse: recorded node topic={result.node.topic}")
        else:
            log(f"PostToolUse: tool={context.tool_name} (not recorded)")

        return result.exit_code

    except Exception as e:
        log(f"PostToolUse ERROR: {e}")
        return 0


if __name__ == "__main__":
    sys.exit(main())

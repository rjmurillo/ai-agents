#!/usr/bin/env python3
"""Claude Code PostToolUse hook - semantic node recorder."""

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

from semantic_hooks.core import HookContext, HookEvent  # noqa: E402
from semantic_hooks.logging import log  # noqa: E402
from semantic_hooks.recorder import create_recorder_from_config  # noqa: E402


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

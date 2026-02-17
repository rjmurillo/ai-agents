#!/usr/bin/env python3
"""Claude Code PostToolUse hook - semantic node recorder."""

import json
import sys
from pathlib import Path

# Add parent to path for imports when running as script
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from semantic_hooks.core import HookContext, HookEvent
from semantic_hooks.recorder import create_recorder_from_config


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
            _log(f"PostToolUse: recorded node topic={result.node.topic}")
        else:
            _log(f"PostToolUse: tool={context.tool_name} (not recorded)")

        return result.exit_code

    except Exception as e:
        _log(f"PostToolUse ERROR: {e}")
        return 0


def _log(message: str) -> None:
    """Log to hooks log file."""
    log_file = Path.home() / ".semantic-hooks" / "hooks.log"
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, "a") as f:
            from datetime import datetime
            f.write(f"{datetime.now().isoformat()} {message}\n")
    except Exception:
        pass


if __name__ == "__main__":
    sys.exit(main())

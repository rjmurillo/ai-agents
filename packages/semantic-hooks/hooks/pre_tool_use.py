#!/usr/bin/env python3
"""Claude Code PreToolUse hook - semantic tension guard."""

import json
import sys
from pathlib import Path

# Add parent to path for imports when running as script
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from semantic_hooks.core import HookContext, HookEvent
from semantic_hooks.guards import create_guard_from_config


def main() -> int:
    """Main entry point for PreToolUse hook."""
    try:
        # Read input from Claude
        input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {}

        # Create context
        context = HookContext.from_stdin_json(input_data, HookEvent.PRE_TOOL_USE)

        # Run guard
        guard = create_guard_from_config()
        result = guard.check(context)

        # Output response
        output = result.to_stdout_json()
        if output:
            print(json.dumps(output))

        # Log if configured
        _log(f"PreToolUse: tool={context.tool_name} ΔS check -> exit={result.exit_code}")

        return result.exit_code

    except Exception as e:
        _log(f"PreToolUse ERROR: {e}")
        # Don't block on errors - fail open
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

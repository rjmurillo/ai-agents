#!/usr/bin/env python3
"""Claude Code SessionEnd hook - persist and summarize session."""

import json
import sys
from datetime import datetime
from pathlib import Path

from semantic_hooks.logging import log
from semantic_hooks.memory import SemanticMemory


def main() -> int:
    """Main entry point for SessionEnd hook."""
    try:
        # Read input from Claude
        input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {}

        # Use empty string default to match recording hooks (HookContext.from_stdin_json)
        session_id = input_data.get("session_id", "")

        # Export session tree
        memory = SemanticMemory()
        tree = memory.export_tree(session_id=session_id if session_id else None)

        # Save session summary
        summary_dir = Path.home() / ".semantic-hooks" / "sessions"
        summary_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_suffix = session_id[:8] if session_id else "unknown"
        summary_file = summary_dir / f"{timestamp}_{session_suffix}.json"

        summary_file.write_text(json.dumps(tree, indent=2))

        log(f"SessionEnd: session={session_id}, nodes={tree['node_count']}, saved={summary_file}")

        # Report zone summary
        zones = tree.get("zone_summary", {})
        if zones.get("danger", 0) > 0:
            log(f"SessionEnd WARNING: {zones['danger']} nodes in danger zone")

        return 0

    except Exception as e:
        log(f"SessionEnd ERROR: {e}")
        return 0


if __name__ == "__main__":
    sys.exit(main())

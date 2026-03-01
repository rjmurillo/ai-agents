#!/usr/bin/env python3
"""Claude Code SessionEnd hook - persist and summarize session."""

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
from datetime import datetime  # noqa: E402
from pathlib import Path  # noqa: E402

from semantic_hooks.logging import log  # noqa: E402
from semantic_hooks.memory import SemanticMemory  # noqa: E402


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

#!/usr/bin/env python3
"""Claude Code PreCompact hook - checkpoint before context compaction."""

import json
import sys
from datetime import datetime
from pathlib import Path

from semantic_hooks.logging import log
from semantic_hooks.memory import SemanticMemory


def main() -> int:
    """Main entry point for PreCompact hook."""
    try:
        # Read input from Claude
        input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {}

        # Use empty string default to match recording hooks (HookContext.from_stdin_json)
        session_id = input_data.get("session_id", "")

        # Force checkpoint - export current tree state
        memory = SemanticMemory()
        tree = memory.export_tree(session_id=session_id if session_id else None)

        # Save checkpoint
        checkpoint_dir = Path.home() / ".semantic-hooks" / "checkpoints"
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_suffix = session_id[:8] if session_id else "unknown"
        checkpoint_file = checkpoint_dir / f"precompact_{timestamp}_{session_suffix}.json"

        checkpoint_file.write_text(json.dumps(tree, indent=2))

        log(f"PreCompact: session={session_id}, nodes={tree['node_count']}, checkpoint={checkpoint_file}")

        # Inject summary into context before compaction
        recent = memory.get_recent(n=10, session_id=session_id if session_id else None, include_embeddings=False)
        if recent:
            summary_lines = []
            for node in recent:
                zone_marker = {"safe": "✓", "transitional": "~", "risk": "!", "danger": "!!"}
                marker = zone_marker.get(node.zone.value, "?")
                summary_lines.append(f"{marker} {node.topic}: {node.insight[:50]}")

            summary = "Semantic context before compaction:\n" + "\n".join(summary_lines)
            print(json.dumps({"additionalContext": summary}))

        return 0

    except Exception as e:
        log(f"PreCompact ERROR: {e}")
        return 0


if __name__ == "__main__":
    sys.exit(main())

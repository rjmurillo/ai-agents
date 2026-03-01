#!/usr/bin/env python3
"""Claude Code PreCompact hook - checkpoint before context compaction."""

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

        log(
            f"PreCompact: session={session_id}, "
            f"nodes={tree['node_count']}, checkpoint={checkpoint_file}"
        )

        # Inject summary into context before compaction
        recent = memory.get_recent(
            n=10,
            session_id=session_id if session_id else None,
            include_embeddings=False,
        )
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

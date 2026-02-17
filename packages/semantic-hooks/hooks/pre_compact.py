#!/usr/bin/env python3
"""Claude Code PreCompact hook - checkpoint before context compaction."""

import json
import sys
from pathlib import Path

# Add parent to path for imports when running as script
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def main() -> int:
    """Main entry point for PreCompact hook."""
    try:
        # Read input from Claude
        input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {}

        session_id = input_data.get("session_id", "unknown")

        # Force checkpoint - export current tree state
        from semantic_hooks.memory import SemanticMemory
        memory = SemanticMemory()
        tree = memory.export_tree(session_id=session_id)

        # Save checkpoint
        checkpoint_dir = Path.home() / ".semantic-hooks" / "checkpoints"
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        checkpoint_file = checkpoint_dir / f"precompact_{timestamp}_{session_id[:8]}.json"

        checkpoint_file.write_text(json.dumps(tree, indent=2))

        _log(f"PreCompact: session={session_id}, nodes={tree['node_count']}, checkpoint={checkpoint_file}")

        # Inject summary into context before compaction
        recent = memory.get_recent(n=10, session_id=session_id, include_embeddings=False)
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
        _log(f"PreCompact ERROR: {e}")
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

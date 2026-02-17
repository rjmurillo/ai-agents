#!/usr/bin/env python3
"""Claude Code SessionEnd hook - persist and summarize session."""

import json
import sys
from pathlib import Path

# Add parent to path for imports when running as script
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def main() -> int:
    """Main entry point for SessionEnd hook."""
    try:
        # Read input from Claude
        input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {}

        session_id = input_data.get("session_id", "unknown")

        # Export session tree
        from semantic_hooks.memory import SemanticMemory
        memory = SemanticMemory()
        tree = memory.export_tree(session_id=session_id)

        # Save session summary
        summary_dir = Path.home() / ".semantic-hooks" / "sessions"
        summary_dir.mkdir(parents=True, exist_ok=True)

        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        summary_file = summary_dir / f"{timestamp}_{session_id[:8]}.json"

        summary_file.write_text(json.dumps(tree, indent=2))

        _log(f"SessionEnd: session={session_id}, nodes={tree['node_count']}, saved={summary_file}")

        # Report zone summary
        zones = tree.get("zone_summary", {})
        if zones.get("danger", 0) > 0:
            _log(f"SessionEnd WARNING: {zones['danger']} nodes in danger zone")

        return 0

    except Exception as e:
        _log(f"SessionEnd ERROR: {e}")
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

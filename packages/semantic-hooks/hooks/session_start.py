#!/usr/bin/env python3
"""Claude Code SessionStart hook - initialize semantic memory."""

import json
import sys
from pathlib import Path

# Add parent to path for imports when running as script
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def main() -> int:
    """Main entry point for SessionStart hook."""
    try:
        # Read input from Claude
        input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {}

        session_id = input_data.get("session_id", "unknown")

        # Initialize memory (creates DB if needed)
        from semantic_hooks.memory import SemanticMemory
        memory = SemanticMemory()

        # Import from Serena if available
        imported = memory.import_from_serena()

        # Log session start
        _log(f"SessionStart: session={session_id}, serena_imported={imported}")

        # Could inject context about previous sessions here
        recent = memory.get_recent(n=5, include_embeddings=False)
        if recent:
            topics = [n.topic for n in recent[:3]]
            context = f"Recent context: {', '.join(topics)}"
            print(json.dumps({"additionalContext": context}))

        return 0

    except Exception as e:
        _log(f"SessionStart ERROR: {e}")
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

#!/usr/bin/env python3
"""Claude Code SessionStart hook - initialize semantic memory."""

import json
import sys

from semantic_hooks.logging import log
from semantic_hooks.memory import SemanticMemory


def main() -> int:
    """Main entry point for SessionStart hook."""
    try:
        # Read input from Claude
        input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {}

        # Use empty string default to match recording hooks (HookContext.from_stdin_json)
        session_id = input_data.get("session_id", "")

        # Initialize memory (creates DB if needed)
        memory = SemanticMemory()

        # Import from Serena if available
        imported = memory.import_from_serena()

        # Log session start
        log(f"SessionStart: session={session_id}, serena_imported={imported}")

        # Could inject context about previous sessions here
        recent = memory.get_recent(n=5, include_embeddings=False)
        if recent:
            topics = [n.topic for n in recent[:3]]
            context = f"Recent context: {', '.join(topics)}"
            print(json.dumps({"additionalContext": context}))

        return 0

    except Exception as e:
        log(f"SessionStart ERROR: {e}")
        return 0


if __name__ == "__main__":
    sys.exit(main())

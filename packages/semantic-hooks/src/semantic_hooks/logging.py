"""Shared logging utilities for semantic-hooks."""

from datetime import datetime
from pathlib import Path


def log(message: str) -> None:
    """Log a message to the hooks log file.

    Writes timestamped messages to ~/.semantic-hooks/hooks.log.

    Args:
        message: The message to log.
    """
    log_file = Path.home() / ".semantic-hooks" / "hooks.log"
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, "a") as f:
            f.write(f"{datetime.now().isoformat()} {message}\n")
    except Exception as e:
        # Last resort: write to stderr so failures are diagnosable
        import sys
        print(f"Failed to write to log file: {e}", file=sys.stderr)

"""Environment defaults shared by GitHub skill entrypoints."""

import os


def env_timeout_seconds(default: int = 30) -> int:
    """Retain the documented integer override and fallback for invalid values."""
    try:
        return int(os.environ.get("GH_TIMEOUT_SECONDS", str(default)))
    except ValueError:
        return default

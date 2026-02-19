"""Canonical: scripts/hook_utilities/guards.py. Sync via scripts/sync_plugin_lib.py."""

import sys
from pathlib import Path


def is_project_repo() -> bool:
    """Check if running in ai-agents project (has .agents/ directory)."""
    agents_path = Path(".agents")
    if agents_path.exists() and not agents_path.is_dir():
        print(
            "[WARNING] .agents exists but is not a directory. "
            "Guards will treat this as a consumer repo.",
            file=sys.stderr,
        )
    return agents_path.is_dir()


def skip_if_consumer_repo(hook_name: str) -> bool:
    """Print skip message and return True if this is a consumer repo."""
    if not is_project_repo():
        print(f"[SKIP] {hook_name}: .agents/ not found (consumer repo)", file=sys.stderr)
        return True
    return False

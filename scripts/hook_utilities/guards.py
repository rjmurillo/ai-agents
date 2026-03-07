"""Plugin-mode guards for hook scripts."""

import sys
from pathlib import Path

from scripts.hook_utilities.utilities import get_project_directory


def is_project_repo() -> bool:
    """Check if running in ai-agents project (has .agents/ directory).

    Uses get_project_directory() to find the repo root, so this works
    correctly even when CWD is a subdirectory.
    """
    project_root = get_project_directory()
    agents_path = Path(project_root) / ".agents"
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

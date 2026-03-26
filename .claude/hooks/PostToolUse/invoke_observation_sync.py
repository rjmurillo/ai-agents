#!/usr/bin/env python3
"""Sync observation memories to Forgetful after Serena write_memory.

Claude Code PostToolUse hook that fires after mcp__serena__write_memory.
When an observation file is written, triggers import to Forgetful for
semantic search availability.

Hook Type: PostToolUse
Matcher: mcp__serena__write_memory
Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Always (non-blocking hook, all errors are warnings)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root:
    _lib_dir = str(Path(_plugin_root).resolve() / "lib")
else:
    _lib_dir = str(Path(__file__).resolve().parents[2] / "lib")
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
    sys.exit(0)  # Non-blocking: fail open
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from hook_utilities.guards import skip_if_consumer_repo  # noqa: E402


def _get_repo_root() -> str:
    """Resolve the repository root from environment or git."""
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    if env_dir:
        return env_dir
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return os.getcwd()


def _is_observation_memory(tool_input: dict[str, object]) -> str | None:
    """Check if the written memory is an observation file.

    Returns the memory name if it matches *-observations, else None.
    """
    name = tool_input.get("name", "")
    if not isinstance(name, str):
        return None
    if name.endswith("-observations"):
        return name
    # Also check the content/path for observation patterns
    content = str(tool_input.get("content", ""))
    if "observations" in name.lower() and (
        "HIGH confidence" in content
        or "MED confidence" in content
        or "LOW confidence" in content
    ):
        return name
    return None


def _find_observation_file(repo_root: str, memory_name: str) -> Path | None:
    """Locate the observation markdown file in .serena/memories/."""
    memories_dir = Path(repo_root) / ".serena" / "memories"
    if not memories_dir.is_dir():
        return None
    # Try exact match first
    candidate = memories_dir / f"{memory_name}.md"
    if candidate.is_file():
        return candidate
    # Try glob match
    for f in memories_dir.glob("*-observations.md"):
        if memory_name in f.stem:
            return f
    return None


def _run_import(repo_root: str, observation_file: Path) -> None:
    """Run the import script for a single observation file."""
    import_script = (
        Path(repo_root) / ".serena" / "scripts" / "import_observations_to_forgetful.py"
    )
    if not import_script.is_file():
        print(
            f"WARNING: Import script not found: {import_script}",
            file=sys.stderr,
        )
        return

    result = subprocess.run(
        [
            sys.executable,
            str(import_script),
            "--observation-file",
            str(observation_file),
            "--confidence-levels",
            "HIGH",
            "MED",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
        cwd=repo_root,
    )
    if result.returncode == 0:
        print(f"Observation sync complete: {observation_file.name}")
        if result.stdout.strip():
            # Show summary line only
            for line in result.stdout.strip().splitlines():
                if line.startswith("Imported:") or line.startswith("Total learnings:"):
                    print(f"  {line.strip()}")
    else:
        print(
            f"WARNING: Observation sync failed for {observation_file.name}: "
            f"{result.stderr.strip()[:200]}",
            file=sys.stderr,
        )


def main() -> int:
    """Main hook entry point."""
    if skip_if_consumer_repo("observation-sync"):
        return 0

    raw = ""
    try:
        if sys.stdin.isatty():
            return 0

        raw = sys.stdin.read()
        if not raw.strip():
            return 0

        hook_input = json.loads(raw)
        tool_input = hook_input.get("tool_input", {})

        if not isinstance(tool_input, dict):
            return 0

        memory_name = _is_observation_memory(tool_input)
        if not memory_name:
            return 0

        repo_root = _get_repo_root()
        observation_file = _find_observation_file(repo_root, memory_name)
        if not observation_file:
            print(
                f"WARNING: Observation file not found for memory '{memory_name}'",
                file=sys.stderr,
            )
            return 0

        _run_import(repo_root, observation_file)

    except Exception as exc:
        input_size = len(raw) if raw else 0
        print(
            f"Observation sync hook error (input_size={input_size}): {exc}",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())

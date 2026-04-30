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
    # Walk up from this hook looking for .claude-plugin/plugin.json
    # (the plugin manifest marker). The sibling lib/ is the plugin's
    # lib dir. Works regardless of source vs install layout depth;
    # robust to the M5 generator copying this file to a different
    # directory level under src/<provider>/hooks/<event>/.
    _cur = Path(__file__).resolve().parent
    _lib_dir = None
    while True:
        if (_cur / ".claude-plugin" / "plugin.json").is_file():
            _lib_dir = str(_cur / "lib")
            break
        if _cur.parent == _cur:
            break
        _cur = _cur.parent
if _lib_dir is None or not os.path.isdir(_lib_dir):
    print("Plugin lib directory not found", file=sys.stderr)
    sys.exit(0)  # Non-blocking: fail open
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from hook_utilities.guards import skip_if_consumer_repo  # noqa: E402


def _get_repo_root() -> str | None:
    """Resolve the repository root from environment or git, with traversal guard.

    Returns ``None`` when ``CLAUDE_PROJECT_DIR`` is set but does not contain
    this hook script. Without that guard, an attacker who can set the env
    var could redirect downstream subprocess calls (line 113 -- launches
    ``$repo_root/.serena/scripts/import_observations_to_forgetful.py``) at
    any directory they control. The list-form ``subprocess.run`` blocks
    CWE-78 shell injection; the containment check here blocks CWE-22 by
    refusing to honor a project root that does not contain the live hook
    file. Mirrors the pattern in ``invoke_adr_change_detection.get_project_root``.
    """
    script_dir = str(Path(__file__).resolve().parent)
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    if env_dir:
        resolved_script = os.path.realpath(script_dir)
        resolved_root = os.path.realpath(env_dir)
        if not resolved_script.startswith(resolved_root + os.sep):
            print(
                f"observation-sync: CLAUDE_PROJECT_DIR='{env_dir}' does not "
                f"contain script '{script_dir}' -- refusing (CWE-22)",
                file=sys.stderr,
            )
            return None
        return env_dir
    # Fixed argv, no user data. Safe.
    result = subprocess.run(  # nosemgrep: dangerous-subprocess-use-tainted-env-args
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
    """Locate the observation markdown file in .serena/memories/.

    Validates that resolved paths stay within the memories directory
    to prevent path traversal (CWE-22).
    """
    memories_dir = Path(repo_root) / ".serena" / "memories"
    if not memories_dir.is_dir():
        return None
    # Reject names containing path separators or parent references
    if "/" in memory_name or "\\" in memory_name or ".." in memory_name:
        return None
    # Try exact match first
    candidate = (memories_dir / f"{memory_name}.md").resolve()
    if not candidate.is_relative_to(memories_dir.resolve()):
        return None
    if candidate.is_file():
        return candidate
    # Try glob match
    memories_resolved = memories_dir.resolve()
    for f in memories_dir.glob("*-observations.md"):
        if memory_name in f.stem:
            if not f.resolve().is_relative_to(memories_resolved):
                continue
            return f
    return None


def _run_import(repo_root: str, observation_file: Path) -> None:
    """Run the import script for a single observation file.

    Caller MUST pass a ``repo_root`` returned by :func:`_get_repo_root`,
    which enforces a CWE-22 containment guard (env-supplied root must
    contain this script). Combined with list-form ``subprocess.run``
    (CWE-78 shell injection blocked) and the ``observation_file``
    validation in :func:`_find_observation_file` (path traversal blocked
    via ``is_relative_to``), the tainted env source is fully neutralized
    before reaching the subprocess invocation below.
    """
    import_script = (
        Path(repo_root) / ".serena" / "scripts" / "import_observations_to_forgetful.py"
    )
    if not import_script.is_file():
        print(
            f"WARNING: Import script not found: {import_script}",
            file=sys.stderr,
        )
        return

    # nosemgrep: dangerous-subprocess-use-tainted-env-args
    # Tainted source (CLAUDE_PROJECT_DIR -> repo_root) is contained by
    # _get_repo_root(); script path is validated by .is_file() check;
    # observation_file is validated by _find_observation_file. List form
    # blocks shell metacharacter injection. Defense-in-depth complete.
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
        if repo_root is None:
            return 0  # Containment guard tripped; non-blocking exit.
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

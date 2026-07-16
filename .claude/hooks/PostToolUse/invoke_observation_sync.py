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
import logging
import os
import subprocess
import sys
from pathlib import Path

# Security-rejection logger. Structured WARNING records let SIEM and grep
# tooling categorize containment-guard rejections without parsing prose.
# Code prefix convention mirrors .agents/governance/FAILURE-MODES.md.
_SECURITY_LOG = logging.getLogger("ai_agents.hooks.observation_sync.security")
if not _SECURITY_LOG.handlers:
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setFormatter(
        logging.Formatter("%(levelname)s %(name)s [%(code)s]: %(message)s")
    )
    _SECURITY_LOG.addHandler(_handler)
    _SECURITY_LOG.setLevel(logging.WARNING)

# Bootstrap: find lib directory via env var or manifest walk-up.
# CLAUDE_PLUGIN_ROOT honored when set; otherwise walk up from __file__
# looking for .claude-plugin/plugin.json (the plugin marker). Sibling
# lib/ is the plugin's lib dir. Layout-independent: works in source
# tree (.claude/) and in the deeper src/<provider>/hooks/<event>/ copy.
_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
_lib_dir: str | None = None
if _plugin_root:
    _lib_dir = str(Path(_plugin_root).resolve() / "lib")
else:
    _cur = Path(__file__).resolve().parent
    while True:
        if (_cur / ".claude-plugin" / "plugin.json").is_file():
            _lib_dir = str(_cur / "lib")
            break
        if _cur.parent == _cur:
            break
        _cur = _cur.parent
if _lib_dir is None or not os.path.isdir(_lib_dir):
    print(
        f"Plugin lib directory not found: {_lib_dir} "
        f"(CLAUDE_PLUGIN_ROOT={_plugin_root!r})",
        file=sys.stderr,
    )
    # Non-blocking hook: exit 0 on bootstrap failure (intentional, not a typo)
    sys.exit(0)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)  # Non-blocking: fail open

from hook_utilities.guards import skip_if_consumer_repo  # noqa: E402


def _emit_project_root_rejection(reason: str, env_dir: str = "") -> None:
    """Emit the existing CWE-22 project-root diagnostic."""
    _SECURITY_LOG.warning(
        reason,
        extra={
            "code": "E_CWE22_PROJECT_DIR_MISMATCH",
            "env_dir": env_dir,
            "cwe": "CWE-22",
            "hook": "observation-sync",
        },
    )


def _validated_absolute_path(raw_path: str) -> Path | None:
    """Resolve an absolute path after rejecting malformed or traversal text."""
    if not raw_path or "\x00" in raw_path:
        return None
    if any(char in raw_path for char in ("\n", "\r", "\t", "\v", "\f")):
        return None
    normalized = raw_path.replace("\\", "/")
    if "/../" in normalized or normalized.startswith("../"):
        return None
    try:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            return None
        return candidate.resolve(strict=True)
    except OSError:
        return None


def _get_repo_root() -> str | None:
    """Return the cwd Git worktree when project-dir input exactly corroborates it."""
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR", "")
    try:
        cwd = Path.cwd().resolve(strict=True)
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(cwd),
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=5,
        )
    except subprocess.TimeoutExpired:
        _emit_project_root_rejection(
            "git rev-parse timed out deriving the cwd worktree -- refusing",
            env_dir,
        )
        return None
    except OSError as exc:
        _emit_project_root_rejection(
            f"git rev-parse failed to start ({type(exc).__name__}) -- refusing",
            env_dir,
        )
        return None
    if result.returncode != 0:
        _emit_project_root_rejection(
            "Git failed to derive the cwd worktree -- refusing", env_dir
        )
        return None

    worktree_root = _validated_absolute_path(result.stdout.strip())
    if worktree_root is None:
        _emit_project_root_rejection(
            "Git returned a malformed worktree root -- refusing", env_dir
        )
        return None
    try:
        cwd.relative_to(worktree_root)
    except ValueError:
        _emit_project_root_rejection(
            "Git returned a worktree that does not contain cwd -- refusing", env_dir
        )
        return None

    if not env_dir:
        return str(worktree_root)
    corroborated_root = _validated_absolute_path(env_dir)
    if corroborated_root != worktree_root:
        _emit_project_root_rejection(
            "CLAUDE_PROJECT_DIR does not match the cwd Git worktree -- refusing",
            env_dir,
        )
        return None
    return str(worktree_root)


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
    which derives the cwd Git worktree and requires an environment root
    to resolve to that exact path. Combined with list-form ``subprocess.run``
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

    # Tainted CLAUDE_PROJECT_DIR input must exactly corroborate the cwd Git
    # root in _get_repo_root(); script path is validated by .is_file();
    # observation_file is validated by _find_observation_file. List form
    # blocks shell metacharacter injection. Defense-in-depth complete.
    result = subprocess.run(  # nosemgrep: dangerous-subprocess-use-tainted-env-args
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

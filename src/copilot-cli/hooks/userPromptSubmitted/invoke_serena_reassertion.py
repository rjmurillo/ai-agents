#!/usr/bin/env python3
"""Re-assert Serena activation each turn to prevent mid-session drift.

Claude Code UserPromptSubmit hook that re-injects a Serena-activation
reminder into context on every user prompt. The SessionStart hook
initializes Serena once, but after context compaction or across many
turns agents drift back to native Read/Edit/Bash on code files instead
of Serena symbolic tools (observed 2026-05-10, session 16: 10+ native
Read calls on code files instead of get_symbols_overview/find_symbol).

This applies a per-turn re-assertion approach (as used for the CAVEMAN
MODE and ADR-007 memory reminders): re-inject the same reminder every
UserPromptSubmit so the obligation persists reliably across compaction.
The session-start-only approach does not survive compaction.

Design note (divergence from issue #1993 proposal):
    Issue #1993 proposed branching on a Serena activation marker (file
    or MCP heartbeat) to choose between an "already active" reminder and
    an "init REQUIRED" reminder. No such marker surface exists: a
    UserPromptSubmit hook receives only the prompt on stdin and cannot
    observe whether Serena MCP tools were called this turn, and no other
    hook writes a Serena-activation marker file. Inventing that state
    would couple two components on a fact neither owns reliably
    (information leakage). Following the cited CAVEMAN pattern, this hook
    is stateless and unconditional: it emits one reminder that is correct
    whether or not Serena is active. It re-asserts the preference for
    symbolic tools AND names the recovery action (initial_instructions),
    so no branch on activation state is needed. The marker-branch can be
    added later if a real activation surface is introduced.

Prior art (non-contractual, not a load-bearing parity claim):
    .claude/hooks/UserPromptSubmit/invoke_autonomous_execution_detector.py
    uses a comparable bootstrap, prompt-extraction fallback, and
    exit-0-always shape. This hook differs: it is unconditional (no
    keyword gate) and injects on every non-empty prompt rather than only
    when a pattern matches.

Hook Type: UserPromptSubmit
Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Always (educational injection, not blocking)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Bootstrap: find lib directory via env var or manifest walk-up.
# CLAUDE_PLUGIN_ROOT honored when set; otherwise walk up from __file__
# looking for .claude-plugin/plugin.json (the plugin marker). Sibling
# lib/ is the plugin's lib dir. Layout-independent: works in source
# tree (.claude/) and in the deeper src/<provider>/hooks/<event>/ copy.
_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root:
    _lib_dir = str(Path(_plugin_root).resolve() / "lib")
else:
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
    print(f"Plugin lib directory not found: {_lib_dir} (CLAUDE_PLUGIN_ROOT={_plugin_root!r})", file=sys.stderr)
    # Non-blocking hook: exit 0 on bootstrap failure (intentional, not a typo)
    sys.exit(0)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)  # Non-blocking: fail open

try:
    from hook_utilities.guards import skip_if_consumer_repo  # noqa: E402
except ImportError:

    def skip_if_consumer_repo(hook_name: str) -> bool:  # type: ignore[misc]
        """Fallback: skip when .agents/ directory is absent.

        Resolves CLAUDE_PROJECT_DIR with expanduser().resolve() to avoid
        path-traversal surprises (CWE-22). When the env var is unset, walks
        up the directory tree from this file rather than trusting cwd, so
        the check holds when invoked from a subdirectory (e.g. tests/hooks/).
        """
        project_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
        if project_dir:
            has_agents = (Path(project_dir).expanduser().resolve() / ".agents").is_dir()
        else:
            has_agents = False
            _cur = Path(__file__).resolve().parent
            while True:
                if (_cur / ".agents").is_dir():
                    has_agents = True
                    break
                if _cur.parent == _cur:
                    break
                _cur = _cur.parent
        if not has_agents:
            print(f"[SKIP] {hook_name}: .agents/ not found", file=sys.stderr)
            return True
        return False


# The reminder injected on every prompt. Combines both messages from
# issue #1993 into one line that holds regardless of activation state:
# it re-asserts the symbolic-tools preference and names the recovery
# action so a drifted or post-compaction agent can self-correct.
SERENA_REMINDER = (
    "\nSerena re-assertion (AGENTS.md Serena Init is BLOCKING): "
    "prefer Serena symbolic tools (get_symbols_overview, find_symbol, "
    "find_referencing_symbols) over native Read/Edit/Bash for code files. "
    "If Serena is not active this session (e.g. after compaction), run "
    "mcp__serena__initial_instructions before further tool calls.\n"
)


def build_reminder() -> str:
    """Return the Serena re-assertion reminder injected into context."""
    return SERENA_REMINDER


def extract_prompt(hook_input: dict[str, object]) -> str | None:
    """Extract user prompt from hook input with fallback for schema variations."""
    for key in ("prompt", "user_message_text", "message"):
        value = hook_input.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def main() -> int:
    """Main hook entry point. Returns exit code."""
    if skip_if_consumer_repo("serena-reassertion"):
        return 0

    try:
        if sys.stdin.isatty():
            return 0

        input_json = sys.stdin.read()
        if not input_json.strip():
            return 0

        hook_input = json.loads(input_json)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"serena_reassertion: Failed to parse input JSON: {exc}", file=sys.stderr)
        return 0

    if not isinstance(hook_input, dict):
        return 0

    user_prompt = extract_prompt(hook_input)
    if not user_prompt:
        return 0

    print(build_reminder())
    return 0


if __name__ == "__main__":
    sys.exit(main())

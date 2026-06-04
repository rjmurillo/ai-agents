#!/usr/bin/env python3
"""Inject stricter protocol enforcement for autonomy keywords.

Claude Code UserPromptSubmit hook that detects keywords signaling
autonomous execution (e.g., "autonomous", "hands-off", "without asking").

When detected, injects stricter protocol guards into context.

Hook Type: UserPromptSubmit
Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Always for the educational injection logic (not blocking).
    2 = Bootstrap failure only (plugin lib directory not found). A hook that
        cannot locate its lib is a hard misconfiguration; it fails closed and
        loud per ADR-066 D2 and ADR-071 Decision item 5, NOT fail-open. A
        silent exit 0 would disable the hook and hide the misconfiguration
        (launcher/hook fail-open rejected: issues #2230, #2271).
"""

from __future__ import annotations

import json
import os
import re
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
    sys.exit(2)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from hook_utilities.guards import skip_if_consumer_repo  # noqa: E402

# Keywords signaling autonomous/unattended execution
AUTONOMY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bautonomous\b", re.IGNORECASE),
    re.compile(r"\bhands-off\b", re.IGNORECASE),
    re.compile(r"\bwithout asking\b", re.IGNORECASE),
    re.compile(r"\bwithout confirmation\b", re.IGNORECASE),
    re.compile(r"\bauto-\w+", re.IGNORECASE),
    re.compile(r"\bunattended\b", re.IGNORECASE),
    re.compile(r"\brun autonomously\b", re.IGNORECASE),
    re.compile(r"\bfull autonomy\b", re.IGNORECASE),
    re.compile(r"\bno human\b", re.IGNORECASE),
    re.compile(r"\bno verification\b", re.IGNORECASE),
    re.compile(r"\bblindly\b", re.IGNORECASE),
]

def _build_stricter_protocol_message(project_dir: str) -> str:
    """Build the stricter protocol message with conditional doc reference."""
    protocol_ref = ""
    protocol_path = Path(project_dir) / ".agents" / "SESSION-PROTOCOL.md"
    if protocol_path.is_file():
        protocol_ref = " See SESSION-PROTOCOL.md."
    return (
        "\nAutonomous mode: Stricter protocol active. "
        "Session log with evidence required. "
        "High-risk ops (merge, force-push, branch delete) need consensus gates "
        f"via /orchestrator. Blocked on main.{protocol_ref}\n"
    )


def has_autonomy_keywords(prompt: str) -> bool:
    """Check if the prompt contains any autonomy-signaling keywords."""
    if not prompt or not prompt.strip():
        return False
    for pattern in AUTONOMY_PATTERNS:
        if pattern.search(prompt):
            return True
    return False


def extract_prompt(hook_input: dict[str, object]) -> str | None:
    """Extract user prompt from hook input with fallback for schema variations."""
    for key in ("prompt", "user_message_text", "message"):
        value = hook_input.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def main() -> int:
    """Main hook entry point. Returns exit code."""
    if skip_if_consumer_repo("autonomous-execution-detector"):
        return 0

    try:
        if sys.stdin.isatty():
            return 0

        input_json = sys.stdin.read()
        if not input_json.strip():
            return 0

        hook_input = json.loads(input_json)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"autonomous_execution_detector: Failed to parse input JSON: {exc}", file=sys.stderr)
        return 0

    user_prompt = extract_prompt(hook_input)
    if not user_prompt:
        return 0

    if has_autonomy_keywords(user_prompt):
        project_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
        if not project_dir:
            project_dir = hook_input.get("cwd", os.getcwd())
        print(_build_stricter_protocol_message(project_dir))

    return 0


if __name__ == "__main__":
    sys.exit(main())

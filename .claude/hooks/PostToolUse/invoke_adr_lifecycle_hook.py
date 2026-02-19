#!/usr/bin/env python3
"""Detect ADR file changes and inject /adr-review guidance.

Claude Code PostToolUse hook that fires after Write, Edit, or Bash
operations targeting ADR files. Injects context reminding Claude that
/adr-review is required before committing ADR changes.

This is shift-left from the commit-time gate (invoke_adr_review_guard.py).
Guidance is injected immediately when an ADR is created, modified, or deleted,
not deferred until commit.

Detected operations:
- Write: New ADR file created or overwritten
- Edit: Existing ADR file modified
- Bash: rm, git rm, mv, git mv targeting ADR files

Hook Type: PostToolUse
Exit Codes:
    0 = Always (non-blocking, injects guidance via stdout)
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root:
    _lib_dir = os.path.join(_plugin_root, "lib")
else:
    _lib_dir = str(Path(__file__).resolve().parents[2] / "lib")
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
    sys.exit(2)  # Config error per ADR-035
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from hook_utilities.guards import skip_if_consumer_repo  # noqa: E402

_ADR_PATH_PATTERN = re.compile(r"ADR-\d+.*\.md$", re.IGNORECASE)

# Bash commands that remove or rename files
_DESTRUCTIVE_CMD_PATTERN = re.compile(
    r"\b(?:rm|git\s+rm|mv|git\s+mv)\b.*ADR-\d+",
    re.IGNORECASE,
)

_GUIDANCE_CREATE = """\

## ADR Change Detected: File Created

**{file_path}** was just created.

Before committing, you MUST run `/adr-review` for multi-agent consensus.
The commit-time gate will block without review evidence.
"""

_GUIDANCE_EDIT = """\

## ADR Change Detected: File Modified

**{file_path}** was just modified.

Before committing, you MUST run `/adr-review` for multi-agent consensus.
The commit-time gate will block without review evidence.
"""

_GUIDANCE_DELETE = """\

## ADR Change Detected: File Removed

An ADR file was targeted by a destructive operation: `{command}`

Before committing, you MUST run `/adr-review` to document the deprecation.
The commit-time gate will block without review evidence.
"""


def _is_adr_path(file_path: str) -> bool:
    """Check if a file path targets an ADR file."""
    return bool(_ADR_PATH_PATTERN.search(file_path))


def _detect_adr_in_bash(command: str) -> bool:
    """Check if a bash command performs a destructive operation on an ADR file."""
    return bool(_DESTRUCTIVE_CMD_PATTERN.search(command))


def _detect_write_or_edit(tool_input: dict[str, object]) -> str | None:
    """Detect Write or Edit targeting an ADR file. Returns the file path or None."""
    file_path = str(tool_input.get("file_path", ""))
    if not file_path:
        return None
    if _is_adr_path(file_path):
        return file_path
    return None


def main() -> int:
    """Main hook entry point."""
    if skip_if_consumer_repo("adr-lifecycle-hook"):
        return 0

    raw = ""
    try:
        if sys.stdin.isatty():
            return 0

        raw = sys.stdin.read()
        if not raw.strip():
            return 0

        hook_input = json.loads(raw)
        tool_name = hook_input.get("tool_name", "")
        tool_input = hook_input.get("tool_input", {})

        if not isinstance(tool_input, dict):
            return 0

        if tool_name in ("Write", "Edit"):
            adr_path = _detect_write_or_edit(tool_input)
            if adr_path:
                # Write = new file or full replacement, Edit = modification
                is_new = tool_name == "Write"
                if is_new:
                    print(_GUIDANCE_CREATE.format(file_path=adr_path))
                else:
                    print(_GUIDANCE_EDIT.format(file_path=adr_path))

        elif tool_name == "Bash":
            command = str(tool_input.get("command", ""))
            if command and _detect_adr_in_bash(command):
                print(_GUIDANCE_DELETE.format(command=command))

    except Exception as exc:
        # Fail-open: never block on infrastructure errors
        input_size = len(raw) if raw else 0
        print(f"ADR lifecycle hook error (input_size={input_size}): {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())

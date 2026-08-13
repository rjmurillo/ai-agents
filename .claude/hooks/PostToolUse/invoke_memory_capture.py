#!/usr/bin/env python3
"""Suggest a memory when a failed tool result carries a learnable error.

Thin invoker for ``memory_enhancement.hooks.post_tool_call_memory``. That
package lives under ``scripts/`` in this repository and does not ship with
the plugin, so a consumer install resolves nothing here and the hook
becomes a silent no-op.

Hook Type: PostToolUseFailure (non-blocking, fail-open)
Exit Codes:
    0 = stdout is empty or carries documented PostToolUseFailure
        ``additionalContext``.

References:
    - Issue #4011 (memory hooks were never registered)
    - Issue #4870 (capture only actual tool failures)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HOOK_NAME = "memory-capture"


def _package_root() -> Path:
    """Directory holding the ``memory_enhancement`` package."""
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    project_dir = Path(env_dir) if env_dir else Path(__file__).resolve().parents[3]
    return project_dir.resolve() / "scripts"


def main() -> int:
    """Delegate to the fact-capture hook, failing open when unavailable."""
    package_root = str(_package_root())
    if package_root not in sys.path:
        sys.path.insert(0, package_root)

    try:
        from memory_enhancement.hooks.post_tool_call_memory import main as capture_main
    except ImportError:
        return 0

    return capture_main()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # fail-open: never block a tool call
        print(f"[WARNING] {HOOK_NAME} error: {exc}", file=sys.stderr)
        sys.exit(0)

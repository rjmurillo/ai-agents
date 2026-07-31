#!/usr/bin/env python3
"""Persist memory confidence scores and print a health summary at session end.

Thin invoker for ``memory_enhancement.hooks.session_end_memory``. That
package lives under ``scripts/`` in this repository and does not ship with
the plugin, so a consumer install resolves nothing here and the hook
becomes a silent no-op.

This is the only live caller of ``reinforce_memories``, so without this
registration confidence is recomputed on every read and never written.

Hook Type: SessionEnd (non-blocking, fail-open)
Exit Codes:
    0 = always. SessionEnd cannot inject context, so a non-zero code would
        only surface the summary to the user as noise.

References:
    - Issue #4011 (memory hooks were never registered)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HOOK_NAME = "memory-reflection"


def _package_root() -> Path:
    """Directory holding the ``memory_enhancement`` package."""
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    project_dir = Path(env_dir) if env_dir else Path(__file__).resolve().parents[3]
    return project_dir.resolve() / "scripts"


def main() -> int:
    """Delegate to the reflection hook, failing open when unavailable."""
    package_root = str(_package_root())
    if package_root not in sys.path:
        sys.path.insert(0, package_root)

    try:
        from memory_enhancement.hooks.session_end_memory import main as reflection_main
    except ImportError:
        return 0

    return reflection_main()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - fail-open: session end must not error
        print(f"[WARNING] {HOOK_NAME} error: {exc}", file=sys.stderr)
        sys.exit(0)

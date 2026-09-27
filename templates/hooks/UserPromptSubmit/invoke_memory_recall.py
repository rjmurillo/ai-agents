#!/usr/bin/env python3
"""Auto-recall relevant Serena memories for the submitted prompt.

Thin invoker for ``memory_enhancement.hooks.user_prompt_submit_memory``.
That package lives under ``scripts/`` in this repository and does not ship
with the plugin, so a consumer install resolves nothing here and the hook
becomes a silent no-op.

Hook Type: UserPromptSubmit (non-blocking, fail-open). With
``--copilot-transformed`` it serves Copilot CLI's ``userPromptTransformed``
event instead, because Copilot drops config-file UserPromptSubmit output.
Exit Codes:
    0 = always. Claude Code adds the plain memory block on stdout to the
        model context. Copilot CLI reads one ``modifiedTransformedPrompt``
        object instead. Exit code 2 on UserPromptSubmit would block prompt
        processing and erase the user prompt, so this hook never blocks.

References:
    - Issue #4011 (memory hooks were never registered)
    - Issue #4727 (recall was inert under Copilot CLI)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HOOK_NAME = "memory-recall"
COPILOT_TRANSFORMED_FLAG = "--copilot-transformed"


def _package_root() -> Path:
    """Directory holding the ``memory_enhancement`` package."""
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    project_dir = Path(env_dir) if env_dir else Path(__file__).resolve().parents[3]
    return project_dir.resolve() / "scripts"


def main() -> int:
    """Delegate to the memory recall hook, failing open when unavailable."""
    package_root = _package_root()
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))

    try:
        from memory_enhancement.interpreter import reexec_under_project_venv
    except ImportError:
        return 0

    # settings.json registers this hook as `python3`, which on a developer
    # machine cannot import python-frontmatter. Without the re-exec the hook
    # exits 0 having done nothing, which is the defect issue #4011 reports.
    reexec_under_project_venv(package_root.parent)

    try:
        from memory_enhancement.hooks import user_prompt_submit_memory as recall
    except ImportError:
        return 0

    if COPILOT_TRANSFORMED_FLAG in sys.argv[1:]:
        return recall.main_transformed()
    return recall.main()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # fail-open: never erase a prompt
        print(f"[WARNING] {HOOK_NAME} error: {exc}", file=sys.stderr)
        sys.exit(0)

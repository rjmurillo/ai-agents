#!/usr/bin/env python3
"""Auto-recall relevant Serena memories for the submitted prompt.

Thin invoker for ``memory_enhancement.hooks.user_prompt_submit_memory``.
The package ships in the plugin's own ``lib/`` tree (ADR-109 amendment
2026-11-20), so this shim finds it from its own location, never from the
user's repository: ``<plugin root>/lib``. The same relative path works for the
plugin copy (``src/claude/hooks/UserPromptSubmit/``) and for this repository's
install copy (``.claude/hooks/UserPromptSubmit/``, whose ``.claude/lib`` links
to the shipped tree).

Customer value: a prompt that names a Serena memory in the user's own
repository gets up to three matching memories injected, so the model starts
the turn with decisions the team already recorded instead of re-deriving them.

Hook Type: UserPromptSubmit (non-blocking, fail-open). With
``--copilot-transformed`` it serves Copilot CLI's ``userPromptTransformed``
event instead, because Copilot drops config-file UserPromptSubmit output.
Exit Codes:
    0 = always. Claude Code adds the plain memory block on stdout to the
        model context. Copilot CLI reads one ``modifiedTransformedPrompt``
        object instead. Exit code 2 on UserPromptSubmit would block prompt
        processing and erase the user prompt, so this hook never blocks.

Interpreter: the recall import closure needs no third-party package
(``serena_integration`` guards its ``frontmatter`` and ``yaml`` imports), so
it runs under the host's bare ``python3``. Only the project registration in
``.claude/settings.json`` re-executes under the project ``.venv``, which keeps
the full parser available for developers. Under a plugin install
(``CLAUDE_PLUGIN_ROOT`` or ``COPILOT_PLUGIN_ROOT`` set) the hook never
re-executes: the dispatcher has already read stdin, and a consumer's ``.venv``
is the consumer's own code.

References:
    - Issue #4011 (memory hooks were never registered)
    - Issue #4727 (recall was inert under Copilot CLI)
    - Issue #7493 (recall ships to plugin consumers)
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

HOOK_NAME = "memory-recall"
COPILOT_TRANSFORMED_FLAG = "--copilot-transformed"
PLUGIN_ROOT_ENVS = ("CLAUDE_PLUGIN_ROOT", "COPILOT_PLUGIN_ROOT")
PROJECT_DIR_ENV = "CLAUDE_PROJECT_DIR"


def _lib_dir() -> Path:
    """Directory holding the ``memory_enhancement`` package: ``<plugin root>/lib``."""
    return Path(__file__).resolve().parents[2] / "lib"


def _project_dir() -> Path:
    """The project the hook serves: the host's project dir, else the checkout root."""
    env_dir = os.environ.get(PROJECT_DIR_ENV, "").strip()
    return Path(env_dir) if env_dir else Path(__file__).resolve().parents[3]


def _report_unavailable(lib_dir: Path, exc: ImportError) -> int:
    print(
        f"[WARNING] {HOOK_NAME}: memory_enhancement not importable from {lib_dir}: {exc}",
        file=sys.stderr,
    )
    return 0


def main() -> int:
    """Delegate to the memory recall hook, failing open when unavailable."""
    lib_dir = _lib_dir()
    if str(lib_dir) not in sys.path:
        sys.path.insert(0, str(lib_dir))

    try:
        from memory_enhancement.interpreter import reexec_under_project_venv
    except ImportError as exc:
        return _report_unavailable(lib_dir, exc)

    # settings.json registers this hook as `python3`. Re-run under the project
    # `.venv` there, so developers keep the full frontmatter parser (issue
    # #4011). A plugin install sets a plugin-root variable and never re-executes.
    if not any(os.environ.get(name, "").strip() for name in PLUGIN_ROOT_ENVS):
        reexec_under_project_venv(_project_dir())

    hook = (
        "user_prompt_transformed_memory"
        if COPILOT_TRANSFORMED_FLAG in sys.argv[1:]
        else "user_prompt_submit_memory"
    )
    try:
        recall = importlib.import_module(f"memory_enhancement.hooks.{hook}")
    except ImportError as exc:
        return _report_unavailable(lib_dir, exc)

    return int(recall.main())


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # fail-open: never erase a prompt
        print(f"[WARNING] {HOOK_NAME} error: {exc}", file=sys.stderr)
        sys.exit(0)

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
repository gets the best matching memory injected, so the model starts
the turn with decisions the team already recorded instead of re-deriving them.
Off: AI_AGENTS_MEMORY_RECALL=0|off|false (read before anything is imported).

Hook Type: UserPromptSubmit (non-blocking, fail-open). With
``--copilot-transformed`` it serves Copilot CLI's ``userPromptTransformed``
event instead, because Copilot drops config-file UserPromptSubmit output.
Exit Codes:
    0 = always. Claude Code adds the plain memory block on stdout to the
        model context. Copilot CLI reads one ``modifiedTransformedPrompt``
        object instead. Exit code 2 on UserPromptSubmit would block prompt
        processing and erase the user prompt, so this hook never blocks.

Interpreter: the recall import closure needs no third-party package
(``frontmatter_reader`` guards its ``frontmatter`` and ``yaml`` imports), so
it runs under the host's bare ``python3``. A direct run, which is the project
registration in ``.claude/settings.json``, re-executes under the project
``.venv`` so developers keep the full parser. Inside the grouped dispatcher
(``claude_hook_dispatch`` already imported) the hook never re-executes: the
dispatcher has already read stdin, and a consumer's ``.venv`` is the consumer's
own code. The signal is the loaded module, not an exported plugin-root
variable, so a direct run keeps working when the host exports one.

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
OPT_OUT_ENV = "AI_AGENTS_MEMORY_RECALL"
OPT_OUT_VALUES = frozenset({"0", "off", "false"})
DISPATCHER_MODULE = "claude_hook_dispatch"
PROJECT_DIR_ENV = "CLAUDE_PROJECT_DIR"
LINK_TEXT = "../../src/claude/lib/memory_enhancement"


def _lib_dir() -> Path:
    """Directory holding the ``memory_enhancement`` package: ``<plugin root>/lib``.

    With ``core.symlinks=false`` Git writes the ``.claude/lib`` link as a text
    file holding its target. Only that exact ADR-119 target is followed.
    """
    lib = Path(__file__).resolve().parents[2] / "lib"
    link = lib / "memory_enhancement"
    if link.is_file() and link.read_text(encoding="utf-8", errors="replace") == LINK_TEXT:
        return lib.parents[1] / "src" / "claude" / "lib"
    return lib


def _project_dir() -> Path:
    """The project the hook serves: the host's project dir, else the checkout root."""
    env_dir = os.environ.get(PROJECT_DIR_ENV, "").strip()
    return Path(env_dir) if env_dir else Path(__file__).resolve().parents[3]


def _opted_out() -> bool:
    return os.environ.get(OPT_OUT_ENV, "").strip().lower() in OPT_OUT_VALUES


def _under_dispatcher() -> bool:
    """True when the grouped dispatcher runs this shim in-process."""
    return DISPATCHER_MODULE in sys.modules


def _report_unavailable(lib_dir: Path, exc: ImportError) -> int:
    print(
        f"[WARNING] {HOOK_NAME}: memory_enhancement not importable from {lib_dir}: {exc}",
        file=sys.stderr,
    )
    return 0


def main() -> int:
    """Delegate to the memory recall hook, failing open when unavailable."""
    if _opted_out():
        return 0
    lib_dir = _lib_dir()
    if str(lib_dir) not in sys.path:
        sys.path.insert(0, str(lib_dir))

    try:
        from memory_enhancement.interpreter import reexec_under_project_venv
    except ImportError as exc:
        return _report_unavailable(lib_dir, exc)

    # settings.json registers this hook as `python3`. Re-run under the project
    # `.venv` there, so developers keep the full frontmatter parser (issue
    # #4011). Under the dispatcher stdin is already consumed, so never.
    if not _under_dispatcher():
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

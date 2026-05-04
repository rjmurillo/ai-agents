#!/usr/bin/env python3
"""Block git push when marketplace.json description counts drift.

Thin adapter over :mod:`push_guard_base`. Activates when the changeset
includes any file that influences plugin counts (agent templates, skill
manifests, command definitions, marketplace.json itself) and delegates
to ``build/scripts/validate_marketplace_counts.py``.

Hook Type: PreToolUse
Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Allow (no manifest-affecting files, all counts current)
    2 = Block (counts stale or validator config error)
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
from pathlib import Path

_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root:
    _root = Path(_plugin_root).resolve()
    _hooks_dir = str(_root / "hooks" / "PreToolUse")
    _lib_dir = str(_root / "lib")
    _scripts_dir = str(_root / "build" / "scripts")
else:
    _cur = Path(__file__).resolve().parent
    _root = None
    while True:
        if (_cur / ".claude-plugin" / "plugin.json").is_file():
            _root = _cur
            break
        if _cur.parent == _cur:
            break
        _cur = _cur.parent
    _hooks_dir = str(_root / "hooks" / "PreToolUse") if _root else None
    _lib_dir = str(_root / "lib") if _root else None
    _scripts_dir = str(_root / "build" / "scripts") if _root else None
if _hooks_dir is None or not os.path.isdir(_hooks_dir):
    print(
        f"Plugin hooks directory not found: {_hooks_dir} "
        f"(CLAUDE_PLUGIN_ROOT={_plugin_root!r})",
        file=sys.stderr,
    )
    sys.exit(2)
if _lib_dir is None or not os.path.isdir(_lib_dir):
    print(
        f"Plugin lib directory not found: {_lib_dir} "
        f"(CLAUDE_PLUGIN_ROOT={_plugin_root!r})",
        file=sys.stderr,
    )
    sys.exit(2)
if _hooks_dir not in sys.path:
    sys.path.insert(0, _hooks_dir)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)
if _scripts_dir and os.path.isdir(_scripts_dir) and _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from push_guard_base import run_guard  # noqa: E402
from hook_utilities import get_project_directory  # noqa: E402

GUARD_NAME = "manifest-count"
GLOBS = [
    "templates/agents/*.md",
    ".claude/skills/*/SKILL.md",
    ".claude/commands/*.md",
    ".claude-plugin/marketplace.json",
]
FIX_HINT = (
    "Run python3 build/scripts/validate_marketplace_counts.py --fix "
    "to auto-correct."
)


def _validate(_matching: list[str], _all_changed: list[str]) -> list[str]:
    try:
        from validate_marketplace_counts import validate_known_marketplaces
    except ImportError as exc:
        return [
            f"build/scripts/validate_marketplace_counts.py: import error - {exc}"
        ]

    project_dir = Path(get_project_directory())
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = validate_known_marketplaces(repo_root=project_dir)

    captured = buf.getvalue().splitlines()

    if rc == 0:
        return []

    if rc == 2:
        first = captured[0] if captured else "config error"
        return [f"build/scripts/validate_marketplace_counts.py: config error - {first}"]

    violations = [line for line in captured if line.strip()]
    violations.append(FIX_HINT)
    return violations


def main() -> int:
    return run_guard(_validate, GLOBS, GUARD_NAME)


if __name__ == "__main__":
    sys.exit(main())

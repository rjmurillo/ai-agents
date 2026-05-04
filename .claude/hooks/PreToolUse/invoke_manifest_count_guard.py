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

def _find_hooks_dir(root: Path) -> str | None:
    """Return hooks dir, trying both PreToolUse (Claude) and preToolUse (copilot-cli)."""
    for variant in ("PreToolUse", "preToolUse"):
        candidate = root / "hooks" / variant
        if candidate.is_dir():
            return str(candidate)
    return None


_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root:
    _resolved_root = Path(_plugin_root).resolve()
    _hooks_dir = _find_hooks_dir(_resolved_root)
    _lib_dir = str(_resolved_root / "lib")
else:
    _cur = Path(__file__).resolve().parent
    _hooks_dir = None
    _lib_dir = None
    while True:
        if (_cur / ".claude-plugin" / "plugin.json").is_file():
            _hooks_dir = _find_hooks_dir(_cur)
            _lib_dir = str(_cur / "lib")
            break
        if _cur.parent == _cur:
            break
        _cur = _cur.parent
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

from push_guard_base import run_guard  # noqa: E402
from hook_utilities import get_project_directory  # noqa: E402

GUARD_NAME = "manifest-count"
# Globs cover every source directory the marketplace counter walks per
# templates/marketplace-counters.yaml. ** matches any directory depth so
# nested hooks (e.g., .claude/hooks/PreToolUse/...) are detected too.
GLOBS = [
    ".claude-plugin/marketplace.json",
    ".github/plugin/marketplace.json",
    "src/claude/*.md",
    ".claude/agents/*.md",
    ".claude/commands/*.md",
    ".claude/hooks/*.py",
    ".claude/hooks/**/*.py",
    ".claude/skills/*/SKILL.md",
    "src/copilot-cli/*.agent.md",
    "src/copilot-cli/hooks/*.py",
    "src/copilot-cli/hooks/**/*.py",
    "src/copilot-cli/skills/*/SKILL.md",
]
FIX_HINT = (
    "Run python3 build/scripts/validate_marketplace_counts.py --fix "
    "to auto-correct."
)


def _import_validator(project_dir: Path):
    """Import validate_known_marketplaces, adding build/scripts to sys.path if needed."""
    try:
        from validate_marketplace_counts import validate_known_marketplaces
        return validate_known_marketplaces
    except ImportError:
        pass
    scripts_dir = project_dir / "build" / "scripts"
    if scripts_dir.is_dir() and str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from validate_marketplace_counts import validate_known_marketplaces
    return validate_known_marketplaces


def _validate(_matching: list[str], _all_changed: list[str]) -> list[str]:
    project_dir = Path(get_project_directory())
    try:
        validate_known_marketplaces = _import_validator(project_dir)
    except ImportError as exc:
        return [
            f"build/scripts/validate_marketplace_counts.py: import error - {exc}"
        ]

    out_buf = io.StringIO()
    err_buf = io.StringIO()
    with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
        rc = validate_known_marketplaces(repo_root=project_dir)

    captured = out_buf.getvalue().splitlines()
    err_lines = [line for line in err_buf.getvalue().splitlines() if line.strip()]

    if rc == 0:
        return []

    if rc == 2:
        # Config errors land on stderr (validator's own pattern). Surface
        # them in the violation list so the agent sees the real cause
        # instead of a generic "config error" placeholder.
        detail = " ; ".join(err_lines) if err_lines else (
            captured[0] if captured else "config error"
        )
        return [f"build/scripts/validate_marketplace_counts.py: config error - {detail}"]

    violations = [line for line in captured if line.strip()]
    if err_lines:
        violations.extend(err_lines)
    violations.append(FIX_HINT)
    return violations


def main() -> int:
    return run_guard(_validate, GLOBS, GUARD_NAME)


if __name__ == "__main__":
    sys.exit(main())

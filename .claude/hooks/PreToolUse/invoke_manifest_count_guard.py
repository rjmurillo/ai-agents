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
import sys
from pathlib import Path

from _bootstrap import ensure_plugin_paths

ensure_plugin_paths()

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
    # include_deletions=True: the marketplace counter walks the live
    # filesystem regardless of which paths the diff lists, so we must
    # fire on deletion-only pushes too. The validator never reads the
    # listed paths, so deleted entries cannot trigger FileNotFoundError.
    return run_guard(_validate, GLOBS, GUARD_NAME, include_deletions=True)


if __name__ == "__main__":
    sys.exit(main())

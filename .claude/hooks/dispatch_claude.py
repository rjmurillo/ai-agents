"""Claude Code hook-group entry point (one spawn per (event, matcher) group).

Registered in ``.claude/settings.json`` (project) and ``hooks.json``
(project-toolkit plugin) as e.g.::

    python3 -u .claude/hooks/dispatch_claude.py --group pretooluse-bash

Group membership lives in ``dispatch_groups.json`` next to this file; the
runner semantics live in ``.claude/lib/claude_hook_dispatch.py`` (which
extends the ADR-068 dispatcher to the Claude Code protocol).

Plugin double-fire guard: when this file runs from the installed
project-toolkit plugin (``CLAUDE_PLUGIN_ROOT`` set) inside a checkout of
the repo that PUBLISHES that same plugin, the project's own
``.claude/settings.json`` already registers every group. Running them a
second time from the plugin doubles the spawn count and duplicates every
context injection (observed live: duplicated ADR-007 and Serena guidance
on each prompt). In that case the dispatcher exits 0 immediately: one
cheap spawn instead of N duplicated hook bodies.

Failure policy: an unreadable or malformed manifest is a packaging error
and exits 2 (loud, fail-closed) regardless of mode, per
``.claude/rules/generated-artifacts.md`` (never silently disable a hook
surface).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_HOOKS_DIR = Path(__file__).resolve().parent
_LIB_DIR = _HOOKS_DIR.parent / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from claude_hook_dispatch import BLOCK_EXIT, run_group  # noqa: E402

_MANIFEST_NAME = "dispatch_groups.json"


def _force_utf8_streams() -> None:
    """Windows consoles default to a legacy codepage; hooks emit UTF-8."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def _plugin_name(root: Path) -> str | None:
    """Read a plugin manifest's ``name``; None when absent or malformed."""
    manifest = root / ".claude-plugin" / "plugin.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    name = data.get("name") if isinstance(data, dict) else None
    return name if isinstance(name, str) and name else None


def _project_self_hosts_plugin() -> bool:
    """True when running as a plugin inside the repo that publishes it."""
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "").strip()
    if not plugin_root:
        return False
    own_name = _plugin_name(Path(plugin_root))
    if own_name is None:
        return False
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip() or os.getcwd()
    project_name = _plugin_name(Path(project_dir) / ".claude")
    return project_name == own_name


def _load_group(group_id: str) -> tuple[str, str, list[str]]:
    """Return ``(event, mode, shims)`` for ``group_id`` from the manifest."""
    manifest_path = _HOOKS_DIR / _MANIFEST_NAME
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    group = data["groups"][group_id]
    shims = [entry["file"] for entry in group["shims"]]
    return group["event"], group["mode"], shims


def main(argv: list[str] | None = None) -> int:
    _force_utf8_streams()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", required=True, help="Group id in dispatch_groups.json")
    args = parser.parse_args(argv)

    if _project_self_hosts_plugin():
        return 0

    try:
        event, mode, shims = _load_group(args.group)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(
            f"claude-hook-dispatch: cannot load group {args.group!r} from "
            f"{_HOOKS_DIR / _MANIFEST_NAME}: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return BLOCK_EXIT

    raw_stdin = sys.stdin.buffer.read()
    return run_group(_HOOKS_DIR, event, mode, shims, raw_stdin)


if __name__ == "__main__":
    sys.exit(main())

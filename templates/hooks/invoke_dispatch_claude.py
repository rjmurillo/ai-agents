"""Claude Code hook-group entry point (one spawn per (event, matcher) group).

Registered in ``.claude/settings.json`` (project) and ``hooks.json``
(project-toolkit plugin) as e.g.::

    python3 -u .claude/hooks/invoke_dispatch_claude.py --group pretooluse-bash

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

Exit codes: 0 allows the tool call, any non-zero code denies it. On a blocking
event (PreToolUse, UserPromptSubmit) the harness reads a non-zero exit as a deny
and shows stderr to the model, so every exit here is a policy decision, not just
a status. In gate mode the code returned is the FIRST denying shim's own code,
which is not necessarily 2; 2 is what this entrypoint returns when it fails
before or around dispatch (bad payload, unknown event, unexpected error).

Failure policy: an unreadable or malformed manifest, stdin read failure, or
unexpected grouped-runtime exception exits 2 (loud, fail-closed) regardless of mode, per
``.claude/rules/generated-artifacts.md`` (never silently disable a hook
surface). Fail-closed means a broken dispatcher blocks rather than waves
through.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

try:
    _HOOKS_DIR = Path(__file__).resolve().parent
    _LIB_DIR = _HOOKS_DIR.parent / "lib"
    if str(_LIB_DIR) not in sys.path:
        sys.path.insert(0, str(_LIB_DIR))

    from claude_hook_dispatch import BLOCK_EXIT, run_group, validate_group
except (Exception, SystemExit) as exc:
    if __name__ == "__main__":
        # Exit 0, not 2. Claude reads a nonzero PreToolUse exit as a denial, so
        # exiting 2 here turned a missing or broken lib directory into a denial
        # of every tool call: the customer-wide failure this plugin was
        # uninstalled over three times. The launcher guards the plugin root and
        # the dispatcher file but cannot check lib, so this is the only place
        # that failure can be caught. Every other infrastructure path in the
        # dispatcher already degrades; this one contradicted them.
        #
        # A load failure is not a policy decision, because no policy ran.
        # Failures after the machinery loads still deny. Refs #4672.
        print(
            "project-toolkit@ai-agents WARNING: hooks DISABLED "
            "(your session is unaffected). "
            f"{type(exc).__name__}: {exc}. "
            "Reinstall: /install-plugin rjmurillo/ai-agents",
            file=sys.stderr,
        )
        raise SystemExit(0) from None
    raise

_MANIFEST_NAME = "dispatch_groups.json"
_BLOCK_EXIT_CODE: int = BLOCK_EXIT
_HOOK_STDIN_CEILING_MIB = 64
_MAX_STDIN_BYTES = _HOOK_STDIN_CEILING_MIB * 1024 * 1024


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
    # Fallback to cwd: Claude Code sets CLAUDE_PROJECT_DIR in normal
    # operation. A wrong cwd yields a name mismatch, which fails safe
    # (no bail; the group still runs).
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip() or os.getcwd()
    project_name = _plugin_name(Path(project_dir) / ".claude")
    return project_name == own_name


def _load_group(group_id: str) -> tuple[str, str, list[str]]:
    """Return ``(event, mode, shims)`` for ``group_id`` from the manifest."""
    manifest_path = _HOOKS_DIR / _MANIFEST_NAME
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError("dispatch manifest must be a JSON object")
    groups = data.get("groups")
    if not isinstance(groups, dict):
        raise TypeError("dispatch manifest field 'groups' must be an object")
    group = groups[group_id]
    if not isinstance(group, dict):
        raise TypeError(f"dispatch group {group_id!r} must be an object")
    entries = group.get("shims")
    if not isinstance(entries, list):
        raise TypeError(f"dispatch group {group_id!r} field 'shims' must be a list")

    shims: list[object] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise TypeError(f"dispatch group {group_id!r} shim {index} must be an object")
        shims.append(entry.get("file"))
    validated_group: tuple[str, str, list[str]] = validate_group(
        group.get("event"), group.get("mode"), shims
    )
    return validated_group


def _read_payload(mode: str) -> tuple[bytes, int | None]:
    """Read one bounded hook payload and return an oversized-input verdict."""
    raw_stdin = sys.stdin.buffer.read(_MAX_STDIN_BYTES + 1)
    if len(raw_stdin) <= _MAX_STDIN_BYTES:
        return raw_stdin, None
    blocks = mode in {"gate", "gate_all"}
    verdict = "denying" if blocks else "allowing without observer dispatch"
    print(
        f"claude-hook-dispatch: stdin exceeds {_MAX_STDIN_BYTES} bytes; {verdict}",
        file=sys.stderr,
    )
    return raw_stdin, _BLOCK_EXIT_CODE if blocks else 0


def main(argv: list[str] | None = None) -> int:
    _force_utf8_streams()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", required=True, help="Group id in dispatch_groups.json")
    args = parser.parse_args(argv)

    try:
        event, mode, shims = _load_group(args.group)
    except Exception as exc:
        print(
            f"claude-hook-dispatch: cannot load group {args.group!r} from "
            f"{_HOOKS_DIR / _MANIFEST_NAME}: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return _BLOCK_EXIT_CODE

    if mode not in {"gate", "gate_all"}:
        try:
            if _project_self_hosts_plugin():
                return 0
        except Exception as exc:
            print(
                f"claude-hook-dispatch: self-host check failed for group "
                f"{args.group!r}: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            return _BLOCK_EXIT_CODE

    try:
        raw_stdin, oversized_exit = _read_payload(mode)
        if oversized_exit is not None:
            return oversized_exit
        exit_code: int = run_group(_HOOKS_DIR, event, mode, shims, raw_stdin)
        return exit_code
    except Exception as exc:
        print(
            f"claude-hook-dispatch: group {args.group!r} failed during execution: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return _BLOCK_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())

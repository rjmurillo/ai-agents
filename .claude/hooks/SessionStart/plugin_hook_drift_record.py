#!/usr/bin/env python3
# taste-lint: ignore naming -- a library imported by the drift-check hook,
# registered as a hook nowhere. The `invoke_` prefix marks a registered entry
# point, so using it here would assert the opposite of what is true. Same
# reasoning as `plugin_hook_drift_state.py`.
"""Read Claude Code's own record of which plugin installs are active.

Claude Code keeps superseded plugin copies in `~/.claude/plugins/cache` after
an update, so a walk of the cache counts them as drift forever (Issue #7227).
`installed_plugins.json` lists the installs the harness actually loads.
"""

from __future__ import annotations

import json
from pathlib import Path

# Claude Code's record of active installs, beside the plugin cache. Shape
# (schema version 2): {"version": 2, "plugins": {"<name>@<marketplace>":
# [{"scope": ..., "installPath": ..., "version": ...}, ...]}}. Superseded cache
# copies stay on disk after an update but leave this file (Issue #7227).
INSTALLED_PLUGINS_FILE = "installed_plugins.json"
SUPPORTED_RECORD_VERSIONS = frozenset({2})
MAX_RECORD_BYTES = 4 * 1024 * 1024


def read_active_installs(
    record: Path, plugin_name: str, search_root: Path
) -> tuple[list[Path] | None, str | None]:
    """Active install roots of ``plugin_name`` per the harness's own record.

    Returns ``(paths, None)`` when the record is readable and its schema is
    known; ``paths`` is empty when the plugin is not installed. Returns
    ``(None, note)`` when the record is missing, unreadable, or of an unknown
    schema, so the caller can fall back to scanning every copy on disk.

    ``installPath`` is untrusted path text. Only a real directory that resolves
    under ``search_root`` is kept, which is the same tree the fallback walk is
    confined to. The note never echoes record content.
    """
    try:
        if record.stat().st_size > MAX_RECORD_BYTES:
            return None, f"{INSTALLED_PLUGINS_FILE} is too large to read"
        data = json.loads(record.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, f"{INSTALLED_PLUGINS_FILE} not found"
    except (OSError, ValueError):
        return None, f"{INSTALLED_PLUGINS_FILE} unreadable"
    plugins = data.get("plugins") if isinstance(data, dict) else None
    version = data.get("version") if isinstance(data, dict) else None
    # A JSON array or object is unhashable, so test the type before membership.
    if (
        not isinstance(data, dict)
        or isinstance(version, bool)
        or not isinstance(version, int)
        or version not in SUPPORTED_RECORD_VERSIONS
        or not isinstance(plugins, dict)
    ):
        return None, f"{INSTALLED_PLUGINS_FILE} has an unknown schema"
    try:
        resolved_root = search_root.resolve()
    except OSError:
        return None, f"{INSTALLED_PLUGINS_FILE} cannot be matched to the plugin cache"
    active: list[Path] = []
    for key, entries in plugins.items():
        if not isinstance(key, str) or key.split("@", 1)[0] != plugin_name:
            continue
        if not isinstance(entries, list):
            continue
        for entry in entries:
            raw = entry.get("installPath") if isinstance(entry, dict) else None
            if not isinstance(raw, str) or not raw:
                continue
            candidate = Path(raw)
            try:
                if candidate.is_symlink() or not candidate.is_dir():
                    continue
                if not candidate.resolve().is_relative_to(resolved_root):
                    continue
            except OSError:
                continue
            if candidate not in active:
                active.append(candidate)
    return active, None

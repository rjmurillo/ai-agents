"""Find the other Hermes packs installed beside this one.

Hermes installs each Project Toolkit pack as its own plugin, side by side in one
plugins folder. A skillforge script that needs another pack's skills looks there.
Other hosts ship one plugin, so a plugin root not named like a pack has no
siblings and nothing changes for them.
"""

from __future__ import annotations

from pathlib import Path

PACK_PREFIX = "project-toolkit-"


def sibling_pack_roots(plugin_root: Path) -> list[Path]:
    """Return the plugin roots of the other packs beside ``plugin_root``, sorted by name.

    A sibling counts only when its name starts with ``project-toolkit-`` and it
    holds a ``skills`` folder and a ``plugin.json``. An unreadable plugins folder
    gives no siblings.
    """
    if not plugin_root.name.startswith(PACK_PREFIX):
        return []
    try:
        entries = sorted(plugin_root.parent.iterdir())
    except OSError:
        return []
    return [
        entry
        for entry in entries
        if entry != plugin_root
        and entry.name.startswith(PACK_PREFIX)
        and (entry / "skills").is_dir()
        and (entry / "plugin.json").is_file()
    ]

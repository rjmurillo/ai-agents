"""Dogfood the shipped Copilot plugin base from the working tree.

Copilot CLI runs plugin hooks from an installed plugin directory under
``~/.copilot/installed-plugins/<marketplace>/<name>``. By default that
directory is a *copy* of a published plugin version, so a local checkout of
this repository does not exercise the hooks it ships to customers. That gap is
how a broken hook (for example the stale LSP guards in issue #3247) can reach
customers before anyone here notices.

This script closes the gap the same way every other artifact reaches the
machine here: by copying. It copies the working tree's ``src/copilot-cli``
directory over the installed ``project-toolkit`` plugin, so local Copilot
sessions load the exact hooks, skills, and agents that ship. Re-run it after
changing ``src/copilot-cli`` to refresh the install. The prior installed
directory is backed up once before replacement, so ``--uninstall`` restores it.

Provides the dogfood install called for by ADR-083 decision item 3, copy-only
on every platform. ADR-083's symlink-on-Unix wording is being reconciled in
#3252. Refs #3222.

Exit codes: 0 success, 2 configuration error.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

MARKETPLACE = "ai-agents"
PLUGIN_NAME = "project-toolkit"
_BACKUP_SUFFIX = ".marketplace-bak"

# Match build_all.py's shipped-tree copy semantics (__pycache__, *.pyc, *.pyo)
# and drop local tool caches so the dogfood copy mirrors what customers get.
_COPY_IGNORE = shutil.ignore_patterns(
    "__pycache__",
    "*.pyc",
    "*.pyo",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
)


def _repo_root() -> Path:
    """Return the git top-level for the directory holding this script."""
    here = Path(__file__).resolve()
    result = subprocess.run(
        ["git", "-C", str(here.parent), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(result.stdout.strip())


def default_source(root: Path) -> Path:
    """Return the shipped Copilot plugin root inside the repository."""
    return root / "src" / "copilot-cli"


def default_target() -> Path:
    """Return the installed-plugin directory Copilot CLI loads from."""
    home_env = os.environ.get("COPILOT_HOME", "").strip()
    home = Path(home_env) if home_env else Path.home() / ".copilot"
    return home / "installed-plugins" / MARKETPLACE / PLUGIN_NAME


def _read_manifest(root: Path) -> dict[str, object] | None:
    """Return a plugin root's parsed manifest, or None if absent or malformed.

    Guards against a manifest that parses to a non-object JSON value (a list,
    string, or null), which would otherwise crash callers that expect a dict.
    """
    manifest = root / ".claude-plugin" / "plugin.json"
    if not manifest.is_file():
        return None
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def _plugin_version(root: Path) -> str | None:
    """Return the version string from a plugin root, or None if absent."""
    manifest = _read_manifest(root)
    if manifest is None:
        return None
    version = manifest.get("version")
    return str(version) if version is not None else None


def _is_plugin_root(root: Path) -> bool:
    """Return True when root has a well-formed manifest naming a plugin."""
    manifest = _read_manifest(root)
    if manifest is None:
        return False
    name = manifest.get("name")
    return isinstance(name, str) and bool(name)


def _backup_path(target: Path) -> Path:
    return target.with_name(target.name + _BACKUP_SUFFIX)


def _stash_existing(target: Path) -> str:
    """Move an existing target aside so a fresh copy can replace it.

    A real directory is preserved once as a backup (so uninstall can restore
    it). A symlink or file is simply removed. Returns a human-readable note.
    """
    if target.is_symlink():
        target.unlink()
        return "removed prior symlink"
    if target.is_dir():
        backup = _backup_path(target)
        # A backup we created is always a real plugin-root directory (we only
        # ever rename the prior marketplace copy there). Anything else at that
        # path (symlink, regular file, fifo, or a stray non-plugin directory)
        # is not our backup: remove it so it cannot be mistaken for a valid
        # prior copy and so the rename() below can create a real one.
        if backup.is_symlink() or (backup.exists() and not backup.is_dir()):
            backup.unlink()
        elif backup.is_dir() and not _is_plugin_root(backup):
            shutil.rmtree(backup)
        if backup.is_dir():
            shutil.rmtree(target)
            return "discarded copy (backup already present)"
        target.rename(backup)
        return f"backed up copy to {backup.name}"
    if target.exists():
        target.unlink()
        return "removed prior file"
    return "no prior install"


def dogfood_install(source: Path, target: Path) -> str:
    """Copy the working-tree plugin over target. Returns an action summary."""
    if not _is_plugin_root(source):
        raise ValueError(
            f"not a plugin root (missing or invalid .claude-plugin/plugin.json): {source}"
        )
    note = _stash_existing(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, ignore=_COPY_IGNORE)
    return f"copied {source} -> {target} ({note})"


def dogfood_uninstall(target: Path) -> str:
    """Remove the dogfood copy and restore any backup. Returns a summary."""
    backup = _backup_path(target)
    if target.is_symlink():
        target.unlink()
        removed = "removed symlink"
    elif target.is_dir():
        shutil.rmtree(target)
        removed = "removed copy"
    elif target.exists():
        target.unlink()
        removed = "removed file"
    else:
        removed = "nothing installed"

    if backup.exists():
        backup.rename(target)
        return f"{removed}; restored backup"
    reinstall = f"copilot plugin update {PLUGIN_NAME}@{MARKETPLACE}"
    return f"{removed}; no backup to restore (reinstall with: {reinstall})"


def dogfood_status(source: Path, target: Path) -> str:
    """Return a one-line description of the current install state."""
    if target.is_symlink():
        return f"symlinked -> {os.readlink(target)}"
    if target.is_dir():
        installed = _plugin_version(target)
        shipped = _plugin_version(source)
        marker = ""
        if installed != shipped:
            marker = f" (working tree ships v{shipped}; re-run --install to refresh)"
        return f"installed copy at {target} [v{installed}]{marker}"
    return f"not installed at {target}"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dogfood_copilot_plugin",
        description="Copy the working-tree project-toolkit over the installed Copilot plugin.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--install",
        action="store_true",
        help="copy the working tree over the installed plugin (default)",
    )
    group.add_argument(
        "--uninstall",
        action="store_true",
        help="remove the dogfood copy and restore any backup",
    )
    group.add_argument(
        "--status",
        action="store_true",
        help="show the current install state and exit",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        root = _repo_root()
        source = default_source(root)
        target = default_target()
        if args.status:
            print(dogfood_status(source, target))
        elif args.uninstall:
            print(dogfood_uninstall(target))
        else:
            print(dogfood_install(source, target))
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

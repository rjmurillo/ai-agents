#!/usr/bin/env python3
"""Place install-tree entries as relative symlinks into their plugin tree.

A binplace row with ``link: true`` (``templates/platforms/binplace.yaml``)
skips the byte copy :mod:`binplace_manifest` does for every other row. Each
top-level entry of ``plugin_tree`` (one agent file, one skill directory) gets
one relative symlink of the same name under ``install_tree``. The install
tree then reads the plugin tree itself, so the two cannot drift apart: there
is no second copy to go stale.

Safety (CWE-22 and CWE-59):

- Every link target is computed here from the validated plugin tree. A link
  already on disk is never trusted; its text must equal the computed target.
- A plugin entry that is itself a symlink, or resolves outside the plugin
  tree, is refused (exit 2), so no install link chains through a top-level
  plugin entry. A symlink anywhere inside an entry is refused the same way
  (exit 2, the path named), because the install link makes it reachable.
- Only top-level names under ``install_tree`` are touched. A name in
  ``skip_names`` (a ``distribution: repo-local`` skill, which has no
  plugin-tree copy) is never linked, replaced, or reported.
- A real directory at a link path is replaced only when its files match the
  plugin entry byte for byte. Otherwise the run refuses with exit 2, so a
  hand edit made there before the switch to links is never lost.
- A real file at a link path carrying a NO-REGEN sentinel is skipped with
  exit 1, the same contract the copy path honors.

Check mode writes nothing. A missing link, a link with the wrong target, a
real file or directory where a link belongs, and a stale link to a plugin
entry that no longer exists are each reported as drift (exit 2).

Git stores each link as a mode ``120000`` entry. A Windows checkout needs
``core.symlinks=true`` and symlink privilege (Developer Mode); without them
git writes a plain text file holding the target path, which this module
reports as drift rather than following.
"""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from regen_guard import detect_reason  # noqa: E402

_STAGING_SUFFIX = ".binplace-link"
_ASIDE_SUFFIX = ".binplace-old"


@dataclass
class LinkOutcome:
    """Paths one :func:`link_row` call changed, would change, or refused."""

    written: list[str] = field(default_factory=list)
    unowned: list[str] = field(default_factory=list)
    drifted: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    exit_code: int = 0


def link_target(source: Path, link_path: Path) -> str:
    """Return the relative target text for a link at ``link_path`` naming ``source``."""
    return os.path.relpath(source, link_path.parent)


def plugin_entries(plugin_tree: Path, skip_names: frozenset[str]) -> list[Path]:
    """Return the top-level plugin entries a link row owns, sorted by name.

    Bytecode caches are never linked: CPython writes ``__pycache__`` into a
    plugin tree as an import side effect, and it is no part of the plugin.
    """
    if not plugin_tree.is_dir():
        return []
    return [
        entry
        for entry in sorted(plugin_tree.iterdir())
        if entry.name != "__pycache__" and entry.name not in skip_names
    ]


def install_link_paths(
    plugin_tree: Path, install_tree: Path, skip_names: frozenset[str]
) -> set[Path]:
    """Return the link paths a link row owns under ``install_tree``."""
    return {install_tree / entry.name for entry in plugin_entries(plugin_tree, skip_names)}


def link_row(
    plugin_tree: Path,
    install_tree: Path,
    *,
    check: bool,
    skip_names: frozenset[str] = frozenset(),
) -> LinkOutcome:
    """Link every top-level plugin entry into ``install_tree``; report the rest."""
    outcome = LinkOutcome()
    entries = plugin_entries(plugin_tree, skip_names)
    if not entries:
        return outcome
    if not check:
        install_tree.mkdir(parents=True, exist_ok=True)
    resolved_plugin = plugin_tree.resolve()
    for entry in entries:
        if entry.is_symlink() or not entry.resolve().is_relative_to(resolved_plugin):
            # CWE-59: a link here would chain .claude/<x> through the plugin
            # tree to wherever the entry points, outside what was validated.
            print(f"Error: plugin entry {entry} is a symlink; refusing to link it", file=sys.stderr)
            outcome.drifted.append(str(entry))
            outcome.exit_code = 2
            _withdraw_link(install_tree / entry.name, check)
            continue
        nested = _first_symlink(entry)
        if nested is not None:
            # CWE-59: the install link exposes the whole entry, so a link
            # nested inside it is reachable from the install tree.
            print(
                f"Error: plugin entry {entry} holds a symlink at {nested}; refusing to link it",
                file=sys.stderr,
            )
            outcome.drifted.append(str(nested))
            outcome.exit_code = 2
            _withdraw_link(install_tree / entry.name, check)
            continue
        try:
            _link_one(entry, install_tree / entry.name, check=check, outcome=outcome)
        except OSError as exc:
            print(
                f"Error: cannot create symlink {install_tree / entry.name}: {exc}. On Windows, "
                "enable Developer Mode and set `git config core.symlinks true`",
                file=sys.stderr,
            )
            outcome.drifted.append(str(install_tree / entry.name))
            outcome.exit_code = 2
    _sweep_install_tree(plugin_tree, install_tree, entries, skip_names, check, outcome)
    return outcome


def _withdraw_link(link_path: Path, check: bool) -> None:
    """Unlink an install link left by an earlier run to an entry now refused.

    CWE-59: the link would keep exposing the unsafe target. Only a symlink is
    removed; a real file or directory at the path is never touched.
    """
    if not check and link_path.is_symlink():
        link_path.unlink()


def _link_one(source: Path, link_path: Path, *, check: bool, outcome: LinkOutcome) -> None:
    """Make ``link_path`` a symlink to ``source``, or record why it is not."""
    target = link_target(source, link_path)
    if link_path.is_symlink():
        if os.readlink(link_path) == target:
            return
        _record_or_apply(link_path, outcome, check, lambda: _publish_link(link_path, target))
        return
    if link_path.is_dir():
        _replace_directory(source, link_path, target, check=check, outcome=outcome)
        return
    if link_path.exists():
        reason = detect_reason(link_path)
        if reason is not None:
            print(f"WARN: skipped {link_path} (NO-REGEN: {reason}); exempt from binplace")
            outcome.skipped.append(str(link_path))
            outcome.exit_code = max(outcome.exit_code, 1)
            return
    _record_or_apply(link_path, outcome, check, lambda: _publish_link(link_path, target))


def _replace_directory(
    source: Path, link_path: Path, target: str, *, check: bool, outcome: LinkOutcome
) -> None:
    """Swap a real directory for a link, only when nothing in it would be lost."""
    if not source.is_dir() or not trees_match(link_path, source):
        print(
            f"Error: {link_path} is a real directory whose files differ from {source}; "
            "move the edits into the plugin tree, then rerun",
            file=sys.stderr,
        )
        outcome.drifted.append(str(link_path))
        outcome.exit_code = 2
        return
    _record_or_apply(link_path, outcome, check, lambda: _swap_directory(link_path, target))


def _record_or_apply(
    link_path: Path, outcome: LinkOutcome, check: bool, apply: Callable[[], None]
) -> None:
    if check:
        outcome.drifted.append(str(link_path))
        outcome.exit_code = max(outcome.exit_code, 2)
        return
    apply()
    outcome.written.append(str(link_path))


def _publish_link(link_path: Path, target: str) -> None:
    """Point ``link_path`` at ``target`` in one rename, replacing a file or link."""
    staging = link_path.with_name(f".{link_path.name}{_STAGING_SUFFIX}")
    if staging.is_symlink() or staging.is_file():
        staging.unlink()
    resolved = (link_path.parent / target).resolve()
    os.symlink(target, staging, target_is_directory=resolved.is_dir())
    os.replace(staging, link_path)


def _swap_directory(link_path: Path, target: str) -> None:
    """Move a verified duplicate directory aside, link in its place, then delete it."""
    aside = link_path.with_name(f".{link_path.name}{_ASIDE_SUFFIX}")
    os.rename(link_path, aside)
    try:
        _publish_link(link_path, target)
    except OSError:
        os.rename(aside, link_path)
        raise
    shutil.rmtree(aside)


def trees_match(candidate: Path, source: Path) -> bool:
    """Return whether two directories hold the same files with the same bytes.

    Bytecode caches are ignored on both sides. A symlink inside either tree
    makes them differ: this module never follows one it did not create.
    """
    left = _tree_files(candidate)
    right = _tree_files(source)
    if left is None or right is None or left.keys() != right.keys():
        return False
    return all(left[rel].read_bytes() == right[rel].read_bytes() for rel in left)


def _tree_paths(root: Path) -> Iterator[tuple[Path, Path]]:
    """Yield ``(relative, absolute)`` for every path under ``root``, minus bytecode."""
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if "__pycache__" in rel.parts or path.suffix in (".pyc", ".pyo"):
            continue
        yield rel, path


def _first_symlink(root: Path) -> Path | None:
    """Return the first symlink under ``root``, or None when the tree is clean."""
    return next((path for _, path in _tree_paths(root) if path.is_symlink()), None)


def _tree_files(root: Path) -> dict[Path, Path] | None:
    files: dict[Path, Path] = {}
    for rel, path in _tree_paths(root):
        if path.is_symlink():
            return None
        if path.is_file():
            files[rel] = path
    return files


def _sweep_install_tree(
    plugin_tree: Path,
    install_tree: Path,
    entries: list[Path],
    skip_names: frozenset[str],
    check: bool,
    outcome: LinkOutcome,
) -> None:
    """Remove links to plugin entries that are gone; report other strays as unowned."""
    if not install_tree.is_dir():
        return
    owned = {entry.name for entry in entries} | skip_names | {"__pycache__"}
    resolved_plugin = plugin_tree.resolve()
    for existing in sorted(install_tree.iterdir()):
        # Only this module's own staging and aside names for an owned entry
        # are skipped; any other name, suffix or not, is reported.
        transient = {f".{name}{sfx}" for name in owned for sfx in (_STAGING_SUFFIX, _ASIDE_SUFFIX)}
        if existing.name in owned or existing.name in transient:
            continue
        if existing.is_symlink() and _names_plugin_entry(existing, resolved_plugin):
            _record_or_apply(existing, outcome, check, existing.unlink)
            continue
        outcome.unowned.append(str(existing))


def _names_plugin_entry(link_path: Path, resolved_plugin: Path) -> bool:
    """Return whether a link's text points directly under the plugin tree."""
    pointed = Path(os.path.normpath(link_path.parent / os.readlink(link_path)))
    return pointed.parent == resolved_plugin or pointed.parent.resolve() == resolved_plugin

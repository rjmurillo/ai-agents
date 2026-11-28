"""Which new head symlinks are generated ADR-119 install links (issue #7398).

`verify_dispatch_closure.py` reports every symlink the head adds, anywhere in
the tree. It has to: the gate refuses an unpinned link while it builds the
closure, so a file behind a new link can drop out of the closure, and only a
tree-wide scan sees that link. The cost was that every pull request adding a
skill failed the check on its two generated links, the Claude Code skill link
and the Codex skill link binplace writes for it.

This module names the one shape that cannot change what the gate runs. A new
link is exempt only when every condition holds:

  * its parent is the install tree of a `link: true` row in the base checkout's
    `templates/platforms/binplace.yaml` (the workflow runs from the base, so the
    file on disk is the base ref's), and that row's class is in
    `EXEMPT_ROW_CLASSES`: the skill rows shown by #7392 and #7396, plus the two
    rule rows shown by #7730. Verifiers do live under the Claude Code
    skill tree; the closure-path check below keeps a link off their paths;
  * its link text is exactly what binplace writes for that row
    (`relpath(<plugin_tree>/<name>, <install_tree>)`);
  * its target is a real entry inside the head tree, with no link component;
  * the base ref has nothing at the link path, so a real directory the head
    replaces with a link is never exempt;
  * no root or closure path is the link or its target, sits under either, or
    is a directory above either;
  * the link is not, does not contain, and does not lie anywhere under an import
    root of any closure script, as the gate's own `_import_roots` computes them.
    The work-tree root is skipped: every exempt tree starts with a dot, so no
    dotted import from the root can pass through it. Import roots read the
    environment (`_environment_libs`), so CI and a local run can differ. Only an
    operator-set plugin root placed inside a skill tree could reach a link that
    way; a pull request cannot set it.

Everything is read from the base checkout or the head tree as data. No head code
runs here.
"""

from __future__ import annotations

import posixpath
import subprocess
from collections.abc import Iterable
from pathlib import Path
from types import ModuleType

import yaml

BINPLACE = "templates/platforms/binplace.yaml"

# The binplace row classes whose links may be exempt. Keyed by class so this
# file names no install path; binplace.yaml owns those. Add a class only with a
# failing pull request that shows the need, and with a test that its install
# tree is not an import root.
EXEMPT_ROW_CLASSES = frozenset({"skills", "skills-codex", "rules", "instructions-github"})


def link_rows(tool_root: Path) -> dict[str, str]:
    """Exempt install tree -> plugin tree, from the base ref's binplace manifest."""
    try:
        loaded = yaml.safe_load((tool_root / BINPLACE).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError, UnicodeDecodeError):
        return {}
    rows = loaded.get("rows") if isinstance(loaded, dict) else None
    if not isinstance(rows, list):
        return {}
    found: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("link") is not True:
            continue
        install, plugin = row.get("install_tree"), row.get("plugin_tree")
        if row.get("class") not in EXEMPT_ROW_CLASSES:
            continue
        # The root-skip in `is_exempt` relies on a dot-led install tree, which no
        # dotted import can name; a row without one is never exempt.
        if isinstance(install, str) and isinstance(plugin, str) and install.startswith("."):
            found[install] = plugin
    return found


def import_roots(gate: ModuleType, closure: Iterable[str], head_root: Path) -> set[str]:
    """Repo-relative import roots of every closure script, from the gate's resolver."""
    roots: set[str] = set()
    for path in closure:
        if not path.endswith(".py"):
            continue
        for root in gate._import_roots(head_root / path, head_root):
            try:
                roots.add(Path(root).resolve().relative_to(head_root.resolve()).as_posix())
            except ValueError:
                continue
    return roots


def _normalized(path: str, head_root: Path) -> str:
    """Repo-relative POSIX spelling of a named path, so `./x` and `/abs/x` compare as `x`."""
    if posixpath.isabs(path):
        try:
            path = Path(path).relative_to(head_root).as_posix()
        except ValueError:
            return posixpath.normpath(path)
    return posixpath.normpath(path)


def _within(path: str, base: str) -> bool:
    return path == base or path.startswith(base + "/")


def _has_link_component(head_root: Path, rel: str) -> bool:
    probe = head_root
    for part in rel.split("/"):
        probe = probe / part
        if probe.is_symlink():
            return True
    return False


def _in_base(tool_root: Path, base_ref: str, path: str, inert_git: tuple[str, ...]) -> bool:
    listed = subprocess.run(
        ["git", *inert_git, "ls-tree", "-z", base_ref, "--", f":(literal){path}"],
        cwd=tool_root,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    # A failed listing reads as present, so the link is reported, never exempt.
    return listed.returncode != 0 or bool(listed.stdout.strip())


def is_exempt(
    link: str,
    *,
    rows: dict[str, str],
    head_root: Path,
    tool_root: Path,
    base_ref: str,
    named: set[str],
    roots: set[str],
    inert_git: tuple[str, ...],
) -> bool:
    """True only when ``link`` is a generated install link the gate cannot reach."""
    parent, name = posixpath.split(link)
    plugin = rows.get(parent)
    if plugin is None or not name:
        return False
    target = f"{plugin}/{name}"
    try:
        text = (head_root / link).readlink().as_posix()
    except OSError:
        return False
    if text != posixpath.relpath(target, parent):
        return False
    if not (head_root / target).exists() or _has_link_component(head_root, target):
        return False
    if _in_base(tool_root, base_ref, link, inert_git):
        return False
    spelled = {_normalized(p, head_root) for p in named}
    if any(_within(p, s) or _within(s, p) for p in spelled for s in (link, target)):
        return False
    for root in roots:
        if root == ".":
            continue  # see the module docstring: no dotted import reaches an exempt tree
        for spelling in (link, target):
            if _within(root, spelling) or _within(spelling, root):
                return False
    return True


def split(
    symlinks: Iterable[str],
    trees: tuple[Path, Path, str, tuple[str, ...]],
    named: set[str],
    roots: set[str],
) -> tuple[list[str], list[str]]:
    """Split new links into (reported, exempt), reading the base manifest once.

    ``trees`` is (tool root, head root, base ref, inert git flags).
    """
    tool_root, head_root, base_ref, inert_git = trees
    rows = link_rows(tool_root)
    reported: list[str] = []
    exempt: list[str] = []
    for link in symlinks:
        ok = is_exempt(
            link,
            rows=rows,
            head_root=head_root,
            tool_root=tool_root,
            base_ref=base_ref,
            named=named,
            roots=roots,
            inert_git=inert_git,
        )
        (exempt if ok else reported).append(link)
    return reported, exempt

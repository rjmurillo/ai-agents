"""Scaffold a skill's reference page and README row for init_skill.py.

A repository that keeps hand-written skill pages under docs/skills/ (with a
README.md that lists them in tables) wants one page and one row per skill.
This module writes both, but only when the new skill lands directly in a
folder named skills inside a git checkout that has docs/skills/README.md.
When this file sits in the checkout that owns the docs gate, and that
checkout contains one of the skill trees the gate inventories, only those
trees qualify. A mirrored tree does not. A checkout the gate does not
inventory keeps the broader skills-folder rule. Anywhere else this module
does nothing.

Stdlib only. The docs gate import is optional and fails soft.
"""

from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

DOCS_README = Path("docs") / "skills" / "README.md"
SKILL_FOLDER_NAME = "skills"

PAGE_SECTIONS = (
    "When to use it",
    "When not to use it",
    "Quick start",
    "What you get",
    "Advanced use",
    "Where it runs",
    "Related",
)

ROW_TEMPLATE = "| [`{name}`]({name}.md) | TODO | TODO: what a reader uses it to do |\n"
# Local page only: optional ./, fragment, and title. Not a URL.
# Same pattern as the docs gate row helper.
_ROW_LINK = re.compile(
    r"\]\(\s*<?(?:\./)?([A-Za-z0-9_.-]+)\.md(?:#[^>\s)]*)?>?"
    r"(?:\s+(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|\([^)\n]*\)))?\s*\)"
)
_GATE_MODULE = "scripts.validation.check_agent_skill_docs"
_GATE_FILE = "check_agent_skill_docs.py"
_TREES: tuple[str, ...] | None = None
_TREES_KNOWN = False


def page_text(name: str, title: str) -> str:
    """Return a reference page with the sibling sections in order."""
    body = "".join(f"## {section}\n\nTODO\n\n" for section in PAGE_SECTIONS)
    return f"# {title}\n\nTODO: one sentence on what `{name}` does for the reader.\n\n{body}"


def _git_root(start: Path) -> Path | None:
    for directory in (start, *start.parents):
        if (directory / ".git").exists():
            return directory
    return None


def _gate_repo() -> Path | None:
    """Return the checkout that contains the docs gate, if this file is in one."""
    here = Path(__file__).resolve()
    for directory in here.parents:
        candidate = directory.joinpath("scripts", "validation", _GATE_FILE)
        if candidate.is_file():
            return directory
    return None


def _inventory_trees() -> tuple[str, ...] | None:
    """Return the docs gate skill trees, or None when that gate cannot load."""
    global _TREES, _TREES_KNOWN
    if _TREES_KNOWN:
        return _TREES
    _TREES_KNOWN = True
    repo = _gate_repo()
    if repo is None:
        return None
    repo_text = str(repo)
    added = repo_text not in sys.path
    if added:
        sys.path.insert(0, repo_text)
    try:
        module = importlib.import_module(_GATE_MODULE)
    except ImportError:
        return None
    finally:
        if added and repo_text in sys.path:
            sys.path.remove(repo_text)
    trees = getattr(module, "SKILL_TREES", None)
    if isinstance(trees, tuple) and trees and all(isinstance(item, str) and item for item in trees):
        _TREES = trees
    return _TREES


def find_docs_readme(skill_parent: Path) -> Path | None:
    """Return docs/skills/README.md when this parent may receive a page.

    The parent must be named skills and sit in a git checkout that has the
    docs README. When the docs gate inventories skill trees and this checkout
    carries the canonical (first) tree, the parent must be one of those trees.
    A mirror tree alone, such as a harness folder in a consumer project, does
    not make a checkout inventoried.
    """
    parent = skill_parent.resolve()
    if parent.name != SKILL_FOLDER_NAME:
        return None
    root = _git_root(parent)
    if root is None:
        return None
    readme = root / DOCS_README
    if not readme.is_file():
        return None
    trees = _inventory_trees()
    gate_root = _gate_repo()
    inventoried = trees is not None and (
        (gate_root is not None and root == gate_root) or (root / trees[0]).is_dir()
    )
    if not inventoried or trees is None:
        return readme
    try:
        relative = parent.relative_to(root).as_posix()
    except ValueError:
        return None
    if relative not in trees:
        return None
    return readme


def _column_count(line: str) -> int:
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    if not body.strip():
        return 0
    return len(body.split("|"))


def _row_for_width(name: str, columns: int) -> str:
    """Return a README row whose cell count matches ``columns``."""
    link = f"[`{name}`]({name}.md)"
    description = "TODO: what a reader uses it to do"
    width = columns if columns >= 2 else 2
    if width == 2:
        cells = [link, description]
    else:
        cells = [link, *["TODO"] * (width - 2), description]
    return "| " + " | ".join(cells) + " |\n"


def _row_names(line: str) -> list[str]:
    return _ROW_LINK.findall(line) if line.lstrip().startswith("|") else []


def has_row(text: str, name: str) -> bool:
    """Return True when a table row in ``text`` links ``<name>.md``."""
    return any(name in _row_names(line) for line in text.splitlines())


def insert_row(text: str, section: str, name: str) -> str | None:
    """Return ``text`` with a row for ``name`` under ``## section``.

    The row uses the column count of that table. It goes before the first
    body row whose link sorts after ``name``, else after the last row.
    Returns None when the heading or table is missing.
    """
    lines = text.splitlines(keepends=True)
    try:
        start = next(i for i, line in enumerate(lines) if line.rstrip() == f"## {section}")
    except StopIteration:
        return None
    rows: list[int] = []
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line.startswith("## ") or (rows and not line.lstrip().startswith("|")):
            break
        if line.lstrip().startswith("|"):
            rows.append(index)
    if not rows:
        return None
    row = _row_for_width(name, _column_count(lines[rows[0]]))
    position = rows[-1] + 1
    for index in rows:
        names = _row_names(lines[index])
        if names and names[0] > name:
            position = index
            break
    if not lines[position - 1].endswith("\n"):
        lines[position - 1] += "\n"
    lines.insert(position, row)
    return "".join(lines)


def scaffold(name: str, title: str, readme: Path, section: str | None) -> list[str]:
    """Write the page and README row. Return what was done, for display."""
    notes: list[str] = []
    page = readme.parent / f"{name}.md"
    if page.exists():
        notes.append(f"Docs page exists, left alone: {page}")
    else:
        page.write_text(page_text(name, title), encoding="utf-8")
        notes.append(f"Docs page written: {page}")
    text = readme.read_text(encoding="utf-8")
    if has_row(text, name):
        notes.append(f"README row exists, left alone: {readme}")
        return notes
    row = ROW_TEMPLATE.format(name=name)
    updated = insert_row(text, section, name) if section else None
    if updated is None:
        where = f"heading '## {section}' has no table" if section else "no --docs-section given"
        notes.append(f"README row not added ({where}). Add this row to a table in {readme}:")
        notes.append(f"  {row.rstrip()}")
        return notes
    readme.write_text(updated, encoding="utf-8")
    notes.append(f"README row added under '## {section}': {readme}")
    return notes

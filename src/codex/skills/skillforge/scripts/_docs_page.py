"""Scaffold a skill's reference page and README row for init_skill.py.

A repository that keeps hand-written skill pages under docs/skills/ (with a
README.md that lists them in tables) wants one page and one row per skill.
This module writes both, but only when the new skill lands directly in a
folder named ``skills`` inside a git checkout that has docs/skills/README.md.
Anywhere else it does nothing, so a skill at the repository root or in a
scratch folder gets no docs files.

Stdlib only.
"""

from __future__ import annotations

import re
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
_ROW_LINK = re.compile(r"\]\((?:\./)?([A-Za-z0-9_.-]+)\.md\)")


def page_text(name: str, title: str) -> str:
    """Return a reference page with the sibling sections in order."""
    body = "".join(f"## {section}\n\nTODO\n\n" for section in PAGE_SECTIONS)
    return f"# {title}\n\nTODO: one sentence on what `{name}` does for the reader.\n\n{body}"


def find_docs_readme(skill_parent: Path) -> Path | None:
    """Return docs/skills/README.md when ``skill_parent`` is a skill folder.

    ``skill_parent`` must be named SKILL_FOLDER_NAME and sit inside a git
    checkout whose root holds DOCS_README.
    """
    parent = skill_parent.resolve()
    if parent.name != SKILL_FOLDER_NAME:
        return None
    for directory in (parent, *parent.parents):
        if (directory / ".git").exists():
            readme = directory / DOCS_README
            return readme if readme.is_file() else None
    return None


def _row_names(line: str) -> list[str]:
    return _ROW_LINK.findall(line) if line.lstrip().startswith("|") else []


def has_row(text: str, name: str) -> bool:
    """Return True when a table row in ``text`` links ``<name>.md``."""
    return any(name in _row_names(line) for line in text.splitlines())


def insert_row(text: str, section: str, name: str, row: str) -> str | None:
    """Return ``text`` with ``row`` in the table under ``## section``.

    The row goes before the first body row whose link sorts after ``name``,
    else after the last row. Returns None when the heading or table is missing.
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
    updated = insert_row(text, section, name, row) if section else None
    if updated is None:
        where = f"heading '## {section}' has no table" if section else "no --docs-section given"
        notes.append(f"README row not added ({where}). Add this row to a table in {readme}:")
        notes.append(f"  {row.rstrip()}")
        return notes
    readme.write_text(updated, encoding="utf-8")
    notes.append(f"README row added under '## {section}': {readme}")
    return notes

"""Shared SKILL.md corpus discovery for the skill validators.

``skill_size.py`` and ``skill_frontmatter.py`` both scan a fixed set of skill
trees. They scan different sets, so each passes its own root and prefixes.
Roots are anchored on the caller's project root rather than the working
directory, so an audit reports the same corpus from any subdirectory
(``.claude/skills/ai-agents-validation-and-qa/references/rule-ci-scripts.md``
MUST-8). An absent tree is skipped, not an error: a vendored install
legitimately ships one tree and not the other.

Stdlib only: ``skill_size.py`` runs by file path from lefthook.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path


def corpus_files(root: Path, prefixes: Sequence[str]) -> list[Path]:
    """Return every SKILL.md under ``root / prefix`` for each prefix, sorted."""
    files: list[Path] = []
    for prefix in prefixes:
        tree = root / prefix
        if tree.is_dir():
            files.extend(tree.rglob("SKILL.md"))
    return sorted(files)


def corpus_summary(root: Path, prefixes: Sequence[str]) -> str:
    """One line naming the trees a full scan measures, and any absent.

    Printed so the corpus behind the summary sentence is stated rather than
    assumed. An absent tree is named too: silence there is what let the
    single-tree scan read as a whole-repository result.
    """
    present = [p for p in prefixes if (root / p).is_dir()]
    absent = [p for p in prefixes if p not in present]
    line = f"Scanning skill trees: {', '.join(present) if present else '(none present)'}"
    if absent:
        line += f"; absent, not scanned: {', '.join(absent)}"
    return line

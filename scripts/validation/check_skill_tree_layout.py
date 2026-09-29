#!/usr/bin/env python3
"""Gate: every direct child of ``.claude/skills/`` must be a skill directory.

The Claude Code plugin loader registers a loose Markdown file sitting directly
under ``.claude/skills/`` as a selectable skill named after the file. Issue
#5503: ``.claude/skills/CLAUDE.md``, a contributor conventions document,
registered as a skill named ``CLAUDE`` and led the skills inventory. A model
picking a skill off that listing got a document about authoring skills.

This is the skill-tree twin of ``check_agent_tree_frontmatter.py`` (issue
#5493). A loose file at the tree root and a directory with no ``SKILL.md`` both
fail. Nothing is exempt: the loader does not read exemptions, so an allowlist
would only teach this repository's CI to look away.

The scan walks the filesystem, not ``git ls-files``, because the loader reads
the filesystem. An untracked or ignored stray file is a true positive.

CLI::

    uv run python scripts/validation/check_skill_tree_layout.py
    uv run python scripts/validation/check_skill_tree_layout.py <repo-root>

Exit codes (ADR-035):
    0 - Success (every child of the tree is a skill directory)
    1 - Logic error (a loose file or a directory without SKILL.md)
    2 - Config error (invalid repository root, or the tree is missing)
"""

from __future__ import annotations

import sys
from pathlib import Path

SKILL_TREE = Path(".claude/skills")
_SKILL_MANIFEST = "SKILL.md"


def find_non_skill_entries(repo_root: Path) -> list[tuple[Path, str]]:
    """Return ``(relative path, reason)`` for each tree child that is not a skill.

    Raises ``FileNotFoundError`` when the tree is absent or empty. A silently
    empty scan passes and proves nothing, so absence is a configuration error.
    """
    tree = repo_root / SKILL_TREE
    if not tree.is_dir():
        msg = f"skill tree not found: {tree}"
        raise FileNotFoundError(msg)

    children = sorted(tree.iterdir())
    if not children:
        msg = f"skill tree is empty: {tree}"
        raise FileNotFoundError(msg)

    findings: list[tuple[Path, str]] = []
    for child in children:
        rel = child.relative_to(repo_root)
        if not child.is_dir():
            findings.append((rel, "loose file; the loader registers it as a skill"))
        elif not (child / _SKILL_MANIFEST).is_file():
            findings.append((rel, f"directory without {_SKILL_MANIFEST}"))
    return findings


def validate_skill_tree_layout(repo_root: Path) -> bool:
    """Return True when every child of ``.claude/skills/`` is a skill directory.

    Entry point matching the ``validate_*(repo_root) -> bool`` contract used by
    ``pre_pr.py``.
    """
    try:
        findings = find_non_skill_entries(repo_root)
    except FileNotFoundError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return False

    if not findings:
        return True

    print(
        f"[FAIL] {len(findings)} entry(ies) directly under {SKILL_TREE.as_posix()}/ "
        "are not skills. The Claude Code plugin loader registers a loose Markdown "
        "file there as a selectable skill, so a model can pick a document that "
        "is not a skill:",
        file=sys.stderr,
    )
    for rel, reason in findings:
        print(f"  {rel.as_posix()}  ({reason})", file=sys.stderr)
    print(
        "\nFix: move the file into a skill's references/ directory, or add the "
        f"missing {_SKILL_MANIFEST}. Do not add an exemption; the loader does not "
        "read exemptions. Refs issue #5503.",
        file=sys.stderr,
    )
    return False


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns an ADR-035 exit code."""
    args = argv if argv is not None else sys.argv[1:]
    repo_root = Path(args[0]).resolve() if args else Path(__file__).resolve().parents[2]
    if not repo_root.is_dir():
        print(f"[FAIL] Invalid repository root: {repo_root}", file=sys.stderr)
        return 2
    if not (repo_root / SKILL_TREE).is_dir():
        print(f"[FAIL] Missing skill tree: {repo_root / SKILL_TREE}", file=sys.stderr)
        return 2
    return 0 if validate_skill_tree_layout(repo_root) else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Regression guard: .gitignore and .markdownlint-cli2.yaml worktree exclusions agree.

Issue #4248: .markdownlint-cli2.yaml excluded only one of five gitignored worktree
root shapes, so a full-repo markdown walk counted 11,964 duplicate .md files from
worktrees that had not been excluded.

The test does not restate either list. It parses both files and asserts the parsed
sets agree, so a new sanctioned worktree root cannot be added to .gitignore alone.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
GITIGNORE = REPO_ROOT / ".gitignore"
MARKDOWNLINT_CONFIG = REPO_ROOT / ".markdownlint-cli2.yaml"

# Globs that look like worktree root shapes (either glob wildcard or known prefix).
_WORKTREE_SHAPE = re.compile(
    r"^("
    r"worktree[-_]"       # worktree-* or worktree--
    r"|wt_"               # wt_*
    r"|\.wt$"             # .wt exactly
    r"|\.work-"           # .work-*
    r"|\.worktrees$"      # .worktrees exactly
    r"|\.claude/worktrees$"  # .claude/worktrees exactly
    r")"
)


def _gitignore_worktree_roots() -> set[str]:
    """Return all worktree root globs from .gitignore.

    Scans the whole file for lines that match a known worktree root shape.
    Returns the glob without trailing slash (git requires it; markdown does not).
    """
    roots: set[str] = set()
    for line in GITIGNORE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        root = stripped.rstrip("/")
        if _WORKTREE_SHAPE.match(root):
            roots.add(root)
    return roots


def _markdownlint_worktree_ignores() -> set[str]:
    """Return the worktree root globs from .markdownlint-cli2.yaml ignores.

    Strips the trailing /** suffix used by the YAML config and filters to
    entries that match the known worktree root shapes.
    """
    config = yaml.safe_load(MARKDOWNLINT_CONFIG.read_text(encoding="utf-8"))
    assert isinstance(config, dict), (
        f"{MARKDOWNLINT_CONFIG} did not parse to a mapping (got {type(config).__name__}). "
        "An empty or restructured config would otherwise surface as an AttributeError "
        "several frames away from the real cause."
    )
    ignores = config.get("ignores", [])
    assert isinstance(ignores, list), (
        f"{MARKDOWNLINT_CONFIG} 'ignores' is not a list (got {type(ignores).__name__}). "
        "The parity check reads it as a sequence of glob strings."
    )
    roots: set[str] = set()
    for entry in ignores:
        if entry.endswith("/**"):
            root = entry[: -len("/**")]
        elif entry.endswith("/"):
            root = entry.rstrip("/")
        else:
            root = entry
        if _WORKTREE_SHAPE.match(root):
            roots.add(root)
    return roots


def test_gitignore_worktree_roots_are_found() -> None:
    """Sanity: the parser finds at least the known entries."""
    roots = _gitignore_worktree_roots()
    assert "worktree-*" in roots, f"expected worktree-* in gitignore roots: {roots}"
    assert "wt_*" in roots, f"expected wt_* in gitignore roots: {roots}"
    assert ".wt" in roots, f"expected .wt in gitignore roots: {roots}"
    assert ".claude/worktrees" in roots, f"expected .claude/worktrees in gitignore roots: {roots}"
    assert ".worktrees" in roots, f"expected .worktrees in gitignore roots: {roots}"


def test_markdownlint_ignores_all_gitignored_worktree_roots() -> None:
    """Every gitignore worktree root must appear in markdownlint ignores.

    This is the regression guard for issue #4248: four of five gitignored
    worktree root shapes were missing from .markdownlint-cli2.yaml, causing
    full-repo markdown walks to count 11,964 duplicate .md files.
    """
    git_roots = _gitignore_worktree_roots()
    md_roots = _markdownlint_worktree_ignores()

    missing = git_roots - md_roots
    assert not missing, (
        f"Worktree root(s) in .gitignore but missing from .markdownlint-cli2.yaml ignores: "
        f"{sorted(missing)}. "
        "Add them as '<root>/**' entries under the worktree comment in the ignores list. "
        "Refs issue #4248."
    )


def test_markdownlint_has_no_orphaned_worktree_entries() -> None:
    """Every markdownlint worktree ignore root must appear in .gitignore.

    An ignore entry that has no matching .gitignore line is either stale or
    names a shape that should be added to .gitignore. Either way it needs
    attention.
    """
    git_roots = _gitignore_worktree_roots()
    md_roots = _markdownlint_worktree_ignores()

    orphaned = md_roots - git_roots
    assert not orphaned, (
        f"Worktree root(s) in .markdownlint-cli2.yaml ignores but missing from .gitignore: "
        f"{sorted(orphaned)}. "
        "Either add them to .gitignore or remove the stale markdownlint entry."
    )


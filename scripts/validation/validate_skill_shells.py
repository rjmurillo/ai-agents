#!/usr/bin/env python3
"""Detect skill "shell" directories: tracked content but no SKILL.md (issue #2677).

A skill lives at ``.claude/skills/<name>/`` (and its Copilot mirror at
``src/copilot-cli/skills/<name>/``). The ``SKILL.md`` file is what makes the
directory a real, routable skill: it carries the frontmatter the loader reads
and the description the router matches. When an earlier prune or deletion removes
``SKILL.md`` but leaves other files behind, the directory survives as an
invisible "skill shell": the catalog looks like the skill still exists (a dir is
there) when it does not. No existing validator caught this (issue #2677), so the
shell lingers and miscounts skill-count and portability scans.

What counts as a shell (the failure condition):
  A directory directly under a skills root that has at least one GIT-TRACKED
  file outside ``__pycache__`` but has no git-tracked ``SKILL.md``. An
  untracked manifest on disk does not count because CI and clean clones cannot
  see it.

Why "git-tracked, non-__pycache__":
  The three dirs named in issue #2677 (session-migration, session-qa-eligibility,
  workflow) contain ONLY untracked ``scripts/__pycache__/*.pyc`` in a working
  tree; on a clean checkout they do not exist. Those are local build cruft, not
  a committed shell. Tracking status (via ``git ls-files``) is the line between
  "a shell a clone would inherit" and "stale local cache". A validator that
  tripped on untracked ``__pycache__`` would false-positive on every developer
  who ran the skill's tests once. So the gate keys on tracked content and
  ignores ``__pycache__`` entirely.

Skills roots scanned (when present):
  * ``.claude/skills/``
  * ``src/copilot-cli/skills/``

Exit codes (ADR-035):
  0 - skills root found and no shells found
  1 - one or more skill shells found
  2 - configuration error (repo root not found / git unavailable)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# Skills roots, relative to the repo root. Both the Claude tree and the Copilot
# mirror carry skill directories; a shell can regress either tree.
SKILLS_ROOTS: tuple[str, ...] = (
    ".claude/skills",
    "src/copilot-cli/skills",
)

# The file whose presence makes a directory a real skill.
SKILL_MANIFEST = "SKILL.md"

# Path segment marking Python bytecode cache. A tracked file under this segment
# is build cruft, not skill content, and never counts toward "has content".
PYCACHE_SEGMENT = "__pycache__"


def _resolve_repo_root(start: Path) -> Path | None:
    """Walk up from ``start`` to the directory that holds ``.claude/skills``."""
    base = start if start.is_dir() else start.parent
    for ancestor in (base, *base.parents):
        if (ancestor / ".claude" / "skills").is_dir():
            return ancestor
    return None


def _tracked_files(repo_root: Path, rel_dir: str) -> list[str]:
    """Return repo-relative paths git tracks under ``rel_dir`` (forward slashes).

    Uses ``git ls-files`` so the answer is "what a clone would inherit", not
    "what is on this developer's disk". Returns an empty list when the directory
    is untracked-only or absent. Raises on git failure so the caller can exit 2.
    """
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", rel_dir],
        cwd=repo_root,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    # -z gives a NUL-separated, quote-free list (handles paths with spaces).
    return [entry for entry in result.stdout.split("\0") if entry]


def _is_pycache(rel_path: str) -> bool:
    """True when the path lies under a ``__pycache__`` segment."""
    return PYCACHE_SEGMENT in rel_path.split("/")


def _has_skill_manifest(skill_dir_rel: str, tracked: list[str]) -> bool:
    """True when ``SKILL.md`` is tracked for the skill.

    The validator keys on git-tracked content, so the manifest must also be
    tracked. An untracked working-tree ``SKILL.md`` cannot protect CI or clean
    clones from a committed shell.
    """
    manifest_rel = f"{skill_dir_rel}/{SKILL_MANIFEST}"
    return manifest_rel in tracked


def _iter_skill_dirs(repo_root: Path, root_rel: str) -> list[str]:
    """Repo-relative paths of immediate child directories under a skills root.

    Derived from the tracked file set so a clean clone and a dirty working tree
    agree on which skills exist. A directory with only untracked content yields
    no tracked files and is therefore not iterated, which is the intended
    behavior (untracked-only dirs do not exist on a clean checkout).
    """
    prefix = f"{root_rel}/"
    seen: set[str] = set()
    ordered: list[str] = []
    for rel_path in _tracked_files(repo_root, root_rel):
        if not rel_path.startswith(prefix):
            continue
        remainder = rel_path[len(prefix) :]
        name, _, rest = remainder.partition("/")
        if not rest:
            # A tracked file sitting directly in the skills root (e.g. a README),
            # not inside a skill directory. Ignore.
            continue
        skill_dir_rel = f"{root_rel}/{name}"
        if skill_dir_rel not in seen:
            seen.add(skill_dir_rel)
            ordered.append(skill_dir_rel)
    return ordered


def find_skill_shells(repo_root: Path) -> list[str]:
    """Return repo-relative skill dirs that have tracked content but no SKILL.md.

    A directory is a shell when, after dropping ``__pycache__`` files, it still
    has at least one tracked file yet no ``SKILL.md``. Sorted for stable output.
    """
    shells: list[str] = []
    for root_rel in SKILLS_ROOTS:
        if not (repo_root / root_rel).is_dir():
            continue
        for skill_dir_rel in _iter_skill_dirs(repo_root, root_rel):
            tracked = _tracked_files(repo_root, skill_dir_rel)
            content = [p for p in tracked if not _is_pycache(p)]
            if not content:
                continue
            if _has_skill_manifest(skill_dir_rel, tracked):
                continue
            shells.append(skill_dir_rel)
    return sorted(shells)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detect skill shell directories missing SKILL.md (issue #2677).",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root. Defaults to walking up from this script.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    start = args.repo_root if args.repo_root is not None else Path(__file__).resolve()
    repo_root = _resolve_repo_root(start)
    if repo_root is None:
        print(
            "Could not locate repo root (no .claude/skills above the start path).",
            file=sys.stderr,
        )
        return 2

    try:
        shells = find_skill_shells(repo_root)
    except FileNotFoundError:
        print("git executable not found on PATH.", file=sys.stderr)
        return 2
    except subprocess.CalledProcessError as exc:
        print(f"git ls-files failed: {exc.stderr or exc}", file=sys.stderr)
        return 2

    if not shells:
        print("No skill shells found (every skill dir with tracked content has SKILL.md).")
        return 0

    print("Skill shell directories detected (tracked content but no SKILL.md):")
    for shell in shells:
        print(f"  [SHELL] {shell}")
    print()
    print(
        "Fix: restore the skill's SKILL.md, or remove the whole directory "
        "(including scripts/ and __pycache__). See issue #2677."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())

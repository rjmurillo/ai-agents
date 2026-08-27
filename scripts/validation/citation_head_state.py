#!/usr/bin/env python3
"""Git reads backing the citation-freshness gate (issue #5337).

Extracted from ``check_citation_freshness.py`` to keep that validator under
the file-size ceiling, the same seam ``checks_changed_paths.py`` documents
for the target-scoping gates. Everything here answers one question: what
does the committed state actually contain. All splits are LF-only, because
git's line model is LF while ``splitlines()`` also breaks on U+2028 and
friends inside a tracked line, shifting every following line number.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import cast

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
# checks_common transitively imports ``scripts.cli_exec`` (absolute), so the
# repo root must be importable even when the consumer runs as a plain script
# (Issue #3073).
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from checks_common import _run_subprocess  # noqa: E402

_HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@")


def _git(repo_root: Path, args: list[str]) -> tuple[int, str, str]:
    """Run git in repo_root, returning (exit_code, stdout, stderr)."""
    result = _run_subprocess(["git", "-C", str(repo_root), *args], timeout=60)
    return cast("tuple[int, str, str]", result)


def _head_tracked_paths(repo_root: Path) -> set[str] | None:
    """Return the set of paths tracked at HEAD, or None on git failure."""
    exit_code, stdout, _stderr = _git(
        repo_root, ["ls-tree", "-r", "-z", "--name-only", "HEAD"]
    )
    if exit_code != 0:
        return None
    return {path for path in stdout.split("\0") if path}


def _added_lines_since_base(
    repo_root: Path, base_ref: str
) -> dict[str, list[tuple[int, str]]] | None:
    """Map citing file -> [(new line number, line text)] for added lines.

    Parses ``git diff -U0 --diff-filter=ACMR base...HEAD``: the committed
    changes this branch would push, excluding deletions (a deleted citing
    file asserts nothing). File headers are recognized only OUTSIDE hunks,
    so an added line whose content begins ``++ `` is never misread as one.
    """
    # Deterministic textual output whatever the contributor's diff drivers
    # or textconv configure (.gitattributes assigns markdown a driver).
    # Matches scripts/validation/git_hook_policy.py:274 verbatim:
    #     TEXTUAL_DIFF_FLAGS = ("--no-ext-diff", "--no-textconv", "--text")
    exit_code, stdout, _stderr = _git(
        repo_root,
        [
            "diff",
            "--no-color",
            "--no-ext-diff",
            "--no-textconv",
            "--text",
            "-U0",
            "--diff-filter=ACMR",
            f"{base_ref}...HEAD",
        ],
    )
    if exit_code != 0:
        return None

    added: dict[str, list[tuple[int, str]]] = {}
    current_file: str | None = None
    new_lineno = 0
    in_hunk = False
    for raw in stdout.split("\n"):
        if raw.startswith("diff --git "):
            current_file = None
            in_hunk = False
            continue
        if not in_hunk and raw.startswith("+++ "):
            target = raw[4:].strip()
            current_file = None if target == "/dev/null" else target.removeprefix("b/")
            continue
        hunk = _HUNK_HEADER.match(raw)
        if hunk:
            new_lineno = int(hunk.group("new_start"))
            in_hunk = True
            continue
        if current_file is None or not in_hunk:
            continue
        if raw.startswith("+"):
            added.setdefault(current_file, []).append((new_lineno, raw[1:]))
            new_lineno += 1
    return added


class _HeadFileCache:
    """Lazy line-content reads from HEAD, one ``git show`` per file."""

    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root
        self._cache: dict[str, list[str] | None] = {}

    def lines(self, path: str) -> list[str] | None:
        """Return the HEAD lines of path (LF-only split), or None if unreadable."""
        if path not in self._cache:
            exit_code, stdout, _stderr = _git(self._repo_root, ["show", f"HEAD:{path}"])
            if exit_code != 0:
                self._cache[path] = None
            else:
                lines = stdout.split("\n")
                if lines and lines[-1] == "":
                    lines.pop()
                self._cache[path] = lines
        return self._cache[path]

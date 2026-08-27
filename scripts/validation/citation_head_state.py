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

from scripts.ci.diff_line_scope import unquote_diff_path  # noqa: E402

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
    # Rename detection and path rendering are pinned too, following
    # scripts/ci/diff_line_scope.py's git_diff_unified_zero: with a
    # contributor's diff.renames=false a pure rename degrades to
    # delete-plus-add and every latent citation in the renamed file
    # reads as newly authored; core.quotePath octal-escapes non-ASCII
    # paths so they stop matching HEAD; diff.noprefix/mnemonicPrefix
    # change the +++ prefix this parser strips.
    exit_code, stdout, _stderr = _git(
        repo_root,
        [
            "-c",
            "core.quotePath=false",
            "diff",
            "--no-color",
            "--no-ext-diff",
            "--no-textconv",
            "--text",
            "--find-renames",
            "--default-prefix",
            "-U0",
            # T included: a symlink replaced by a regular file is a type
            # change whose whole post-image is added lines this gate must
            # scan; without it that content was silently unscanned.
            "--diff-filter=ACMRT",
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
            # Git C-quotes a header path carrying a quote, backslash, or
            # control character even with core.quotePath=false; the shared
            # unquoter (diff_line_scope's) decodes it so the citing file
            # still matches its HEAD path and keeps its exemptions.
            target = unquote_diff_path(raw[4:]).strip()
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


class HeadReadError(RuntimeError):
    """``git show`` failed for a path tracked at HEAD.

    Every path this gate reads was just listed by ``ls-tree`` or named by
    the diff, so a failed read is an operational git failure, not a
    property of any citation; callers surface it as the documented
    config-error exit, never as a stale-citation finding.
    """


class _HeadFileCache:
    """Lazy line-content reads from HEAD, one ``git show`` per file."""

    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root
        self._cache: dict[str, list[str]] = {}

    def lines(self, path: str) -> list[str]:
        """Return the HEAD lines of path (LF-only split).

        Raises :class:`HeadReadError` when git cannot produce the content.
        """
        if path not in self._cache:
            exit_code, stdout, _stderr = _git(self._repo_root, ["show", f"HEAD:{path}"])
            if exit_code != 0:
                raise HeadReadError(path)
            lines = stdout.split("\n")
            if lines and lines[-1] == "":
                lines.pop()
            self._cache[path] = lines
        return self._cache[path]

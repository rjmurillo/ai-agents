#!/usr/bin/env python3
"""Repo-relative file paths cited in an ADR's binding sections (issue #5194).

ADR-050 stayed `accepted` after the script it mandates, and the document that
script synced against, were deleted in PR #5179. Nothing resolved a file path
named in an accepted ADR, so the record kept telling readers a gate existed.
`check_adr_lifecycle.py` calls this module for its `cited-paths-exist` check.

Scope, tightest first:

* Only the caller decides which records are `accepted`. This module sees a body.
* Only prose under `## Decision` and `## Implementation Notes`, including their
  `###` subsections. Context, Rationale, and References describe history and
  are deliberately not read.
* Only an inline code span whose whole content is a path: a directory
  separator, then a file extension, no spaces, no glob or placeholder
  characters. A directory
  segment that ends in an extension (`A.md/B.md`) is an either-or list, not a
  path. A span holding a command (`python3 scripts/x.py --flag`) cites
  nothing.
* Fenced and indented code blocks, and raw HTML, are blanked first with
  `blank_non_prose_block_lines`. A YAML schema or a routing tree shown as a
  sample is an illustration, not a citation.

Stricter/looser/different than the issue text: the issue comment says to strip
inline backtick spans before extracting. That would delete the very citation
that motivated the issue, since ADR-050 writes `scripts/sync_adr_protocol.py` in
a span. Spans are therefore the one place a citation is read from, and only
fenced blocks are stripped.

Existence is judged against tracked files (`git ls-files`), not the filesystem,
per `.claude/rules/ci-scripts.md` MUST 9: a gitignored build output present on
one machine must not move a ratchet count. Outside a git checkout of
`repo_root` itself the working tree is the only source of truth, so the
filesystem answers instead.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ci.count_ratchet import git_environment
from scripts.utils.markdown_parser import blank_non_prose_block_lines

BINDING_SECTIONS: frozenset[str] = frozenset({"decision", "implementation notes"})

_LEVEL_TWO_HEADING = re.compile(r"(?m)^[ \t]{0,3}##[ \t]+(.+?)[ \t]*$")
_CODE_SPAN = re.compile(r"`([^`\n]+)`")
_LOCATOR_SUFFIX = re.compile(r"(?::\d+(?:-\d+)?|#\S*)$")
# A directory separator, then a dotted extension that starts with a letter.
# `[\w.@-]` excludes glob (`*?[]{}`), placeholder (`<>$%`), and space characters.
_PATH = re.compile(r"^(?:\./)?[\w.@-]+(?:/[\w.@-]+)+\.[A-Za-z][A-Za-z0-9]{0,4}$")
# A directory segment that itself ends in a file extension (`AGENTS.md/CLAUDE.md`)
# is an either-or list, not one path. Dot-leading directories (`.claude`) have
# nothing before the dot and are not matched.
_FILE_LIKE_DIRECTORY = re.compile(r"^[\w@-][\w.@-]*\.[A-Za-z][A-Za-z0-9]{0,4}$")
_GIT_TIMEOUT_SECONDS = 30


def binding_sections(body: str) -> list[str]:
    """Text of each `## Decision` / `## Implementation Notes` section in ``body``."""
    prose = blank_non_prose_block_lines(body)
    headings = list(_LEVEL_TWO_HEADING.finditer(prose))
    sections: list[str] = []
    for index, heading in enumerate(headings):
        if heading.group(1).strip().lower() not in BINDING_SECTIONS:
            continue
        end = headings[index + 1].start() if index + 1 < len(headings) else len(prose)
        sections.append(prose[heading.end() : end])
    return sections


def _as_path(span: str) -> str | None:
    """The repo-relative path a code span cites, or None when it cites none."""
    candidate = _LOCATOR_SUFFIX.sub("", span.strip())
    if not _PATH.match(candidate):
        return None
    path = candidate.removeprefix("./")
    if any(_FILE_LIKE_DIRECTORY.match(segment) for segment in path.split("/")[:-1]):
        return None
    # A `..` segment is relative to the ADR, not the repository root, and would
    # let the filesystem fallback resolve outside it (CWE-22).
    return None if ".." in path.split("/") else path


def extract_cited_paths(body: str) -> list[str]:
    """Distinct paths cited in the binding sections of ``body``, in first-seen order."""
    seen: dict[str, None] = {}
    for section in binding_sections(body):
        for span in _CODE_SPAN.findall(section):
            path = _as_path(span)
            if path is not None:
                seen.setdefault(path)
    return list(seen)


def _git(repo_root: Path, *args: str) -> str | None:
    """Stdout of ``git -C repo_root args``, or None when git cannot answer."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GIT_TIMEOUT_SECONDS,
            env=git_environment(),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout if proc.returncode == 0 else None


def tracked_paths(repo_root: Path) -> frozenset[str] | None:
    """Tracked files of the checkout rooted exactly at ``repo_root``, else None.

    None means ``repo_root`` is not the top level of a git checkout (a bare
    directory, or a subdirectory of some other repository, as a test's
    temporary tree can be). The listing would then describe a different tree,
    so the caller falls back to the filesystem.
    """
    toplevel = _git(repo_root, "rev-parse", "--show-toplevel")
    if toplevel is None or Path(toplevel.strip()).resolve() != repo_root.resolve():
        return None
    listing = _git(repo_root, "ls-files", "-z")
    if listing is None:
        return None
    return frozenset(name for name in listing.split("\0") if name)


def missing_paths(paths: list[str], repo_root: Path, tracked: frozenset[str] | None) -> list[str]:
    """The members of ``paths`` that do not exist, preserving order."""
    if tracked is not None:
        return [path for path in paths if path not in tracked]
    return [path for path in paths if not (repo_root / path).is_file()]

"""Shared unified-diff line-scope parsing for the per-change lint gates.

Issue #2993. Two gates need the same answer: "which post-image lines did this
change actually touch?" The mypy gate in ``scripts/validation/git_hook_policy.py``
answered it first (``_parse_changed_lines``); the ruff gate in
``scripts/ci/ruff_ratchet.py`` linted whole touched files instead, so a
contributor editing a clean line inherited every pre-existing finding in the
file. This module is the single authoritative representation of the parsing so
the two gates cannot drift.

Canonical contract, quoted verbatim from
``scripts/validation/git_hook_policy.py::_parse_changed_lines`` at commit
4f5a12c::

    # Post-image line numbers touched per file: both added and modified lines
    # land in the ``+start,count`` span. Two hunk shapes intentionally
    # contribute nothing, so the ratchet never blocks mypy errors on them:
    #   * Deletion-only hunks (``+N,0``) touch no post-image line. Adding
    #     ``start`` here would flag errors on an unchanged neighboring line,
    #     reintroducing the false positives on untouched code that the
    #     per-file gate produced before this ratchet (issue #2993).
    #   * Pure renames carry no ``+++ b/`` hunk, so the renamed path stays
    #     absent from the map; unchanged content cannot add new type debt.

Stricter/looser/different than canonical:
    * Different: ``parse_changed_lines`` unquotes C-style quoted paths in the
      ``+++ b/"..."`` header. The mypy copy did not, so a filename containing a
      quote, a backslash, or a control character produced a map key that never
      matched the tool-reported path, silently blocking on every finding in
      that file. Callers pass ``-c core.quotePath=false`` (see
      ``git_diff_unified_zero``) so non-ASCII stays raw and only genuinely
      special characters are escaped.
    * Same: everything else. Hunk-span semantics, the deletion-only and
      pure-rename carve-outs, and ``normalize_path`` are byte-identical to the
      canonical source, which now imports them from here.

Stdlib only: ``scripts/ci`` scripts run by path in CI and must not depend on the
project's import graph.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Sequence
from pathlib import Path

# Unified diff (``--unified=0``) markers. ``+++ b/<path>`` names the file with
# stable prefixes; the optional prefix keeps parser tests honest against
# diff.noprefix drift. The ``+c,d`` field of each hunk header is the changed-line
# span (post-image).
DIFF_ADDED_FILE_RE = re.compile(r"^\+\+\+ (?:b/)?(?P<path>.+)$")
DIFF_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<start>\d+)(?:,(?P<count>\d+))? @@")


def normalize_path(path: str) -> str:
    # A tool on Windows can echo OS-native backslash separators, while git diff
    # names and command-line inputs are forward-slash; normalize so the pushed
    # set, the changed-line map, and parsed tool paths compare equal.
    cleaned = path.strip().replace("\\", "/")
    if cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned


# The escapes git's ``quote_c_style`` emits by name. Everything else it needs
# to escape becomes a three-digit octal run, handled separately below.
_NAMED_ESCAPES = {
    "a": "\a",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "v": "\v",
    "\\": "\\",
    '"': '"',
}
_OCTAL_DIGITS = frozenset("01234567")


def _flush(pending: bytearray, out: list[str]) -> None:
    """Decode an accumulated octal-escape run and append it to ``out``.

    Octal escapes carry raw bytes, and one multi-byte UTF-8 character spans
    several of them, so the run must be decoded as a unit rather than per byte.
    """
    if not pending:
        return
    out.append(pending.decode("utf-8", "replace"))
    pending.clear()


def unquote_diff_path(path: str) -> str:
    """Decode a C-style quoted path from a diff header.

    Git wraps a path in double quotes and C-escapes it when the name carries a
    quote, a backslash, or a control character (``quote_c_style`` in git's
    ``quote.c``). Callers set ``core.quotePath=false`` so non-ASCII stays raw;
    git's own output encoding already decoded it, so only the backslash escapes
    need undoing here.

    An unquoted path is returned unchanged, so this is safe to call on every
    header line. An escape git does not emit is kept literally rather than
    raising: a lint gate must never crash on a pathological filename.
    """
    stripped = path.strip()
    if len(stripped) < 2 or not stripped.startswith('"') or not stripped.endswith('"'):
        return path
    body = stripped[1:-1]
    out: list[str] = []
    pending = bytearray()
    index = 0
    while index < len(body):
        character = body[index]
        if character != "\\" or index + 1 >= len(body):
            _flush(pending, out)
            out.append(character)
            index += 1
            continue
        octal = body[index + 1 : index + 4]
        if len(octal) == 3 and _OCTAL_DIGITS.issuperset(octal):
            pending.append(int(octal, 8))
            index += 4
            continue
        _flush(pending, out)
        named = _NAMED_ESCAPES.get(body[index + 1])
        out.append(named if named is not None else character)
        index += 2 if named is not None else 1
    _flush(pending, out)
    return "".join(out)


def parse_changed_lines(diff_text: str) -> dict[str, set[int]]:
    """Return post-image line numbers touched per path in ``diff_text``.

    See the module docstring for the deletion-only and pure-rename carve-outs.
    """
    changed: dict[str, set[int]] = {}
    current: str | None = None
    for line in diff_text.splitlines():
        file_match = DIFF_ADDED_FILE_RE.match(line)
        if file_match is not None:
            current = normalize_path(unquote_diff_path(file_match.group("path")))
            changed.setdefault(current, set())
            continue
        hunk_match = DIFF_HUNK_RE.match(line)
        if hunk_match is None or current is None:
            continue
        start = int(hunk_match.group("start"))
        count_raw = hunk_match.group("count")
        count = int(count_raw) if count_raw is not None else 1
        changed[current].update(range(start, start + count))
    return changed


def git_diff_unified_zero(
    base_ref: str,
    repo_root: Path,
    paths: Sequence[str],
) -> subprocess.CompletedProcess[str]:
    """Run the zero-context diff the line map is parsed from."""
    return subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "-c",
            "core.quotePath=false",
            "diff",
            "--unified=0",
            "--no-color",
            f"{base_ref}...HEAD",
            "--",
            *paths,
        ],
        check=False,
        capture_output=True,
        text=True,
        errors="replace",
        encoding="utf-8",
    )


def changed_line_map(
    base_ref: str,
    repo_root: Path,
    paths: Sequence[str],
) -> dict[str, set[int]] | None:
    """Return added or modified line numbers per path versus ``base_ref``.

    ``None`` signals that the diff base could not be resolved; callers then
    fall back to blocking on any finding so the gate is never weaker than the
    whole-file behavior it replaces.
    """
    if not paths:
        return {}
    result = git_diff_unified_zero(base_ref, repo_root, paths)
    if result.returncode != 0:
        return None
    return parse_changed_lines(result.stdout)


def intersects_changed_lines(
    changed_lines: dict[str, set[int]] | None,
    path: str,
    start_row: int,
    end_row: int,
) -> bool:
    """Report whether any row in ``[start_row, end_row]`` was added or modified.

    ``changed_lines is None`` means the diff base was unresolvable, which fails
    closed: every finding blocks. A multi-line finding blocks when any row in
    its reported range intersects the change, which is the accepted contract on
    issue #2993: an edit inside a multi-line statement owns the whole statement.
    """
    if changed_lines is None:
        return True
    touched = changed_lines.get(normalize_path(path))
    if not touched:
        return False
    low, high = (start_row, end_row) if start_row <= end_row else (end_row, start_row)
    return any(row in touched for row in range(low, high + 1))

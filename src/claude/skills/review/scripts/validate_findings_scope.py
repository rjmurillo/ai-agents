#!/usr/bin/env python3
"""Validate that review-axis findings reference files in the PR diff.

After each stage-2 axis returns, the orchestrator passes the axis text to
this script.  The script extracts ``location:`` fields and free-form file
paths, strips line suffixes, and checks each path against the three-dot diff.

When one or more locations fall outside the diff, the script exits 1 and
prints the out-of-scope paths to stderr.  With ``--emit-adjusted-text``, it
also prints axis text whose out-of-scope location lines are marked
``[pre-existing - not in this PR diff]`` and whose blocking verdict is
downgraded to WARN when every cited location is outside the PR diff.

When all locations are in scope (or the diff is empty/unavailable), the
script exits 0 and the orchestrator records the axis output unmodified.

EXIT CODES (ADR-035):
    0 - All locations are in scope, or the diff list is empty or unavailable.
    1 - One or more locations are out of scope.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Pattern that matches a ``location:`` field in axis output.
# Axis prompts require ``location: file:line`` (or ``file:line-range``).
# The pattern is intentionally broad: it captures the path segment before
# the first colon (file separator) or end-of-value.
# Optional backtick wrapping is handled: ``location: `file:line`` and
# ``**location**: `file:line` `` are both accepted.
_LOCATION_FIELD_RE = re.compile(
    r"(?i)\blocation\b"              # ``location`` word, case-insensitive
    r"\s*\*{0,2}\s*"                 # optional closing bold markers: ``**``
    r":\s*"                          # colon separator
    r"`?"                            # optional opening backtick
    r"([^\s``,\[|\]]+)"              # the path (stops at whitespace/comma/table char/backtick)
)
_PROSE_PATH_RE = re.compile(
    r"(?<![\w./-])"
    r"((?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+"
    r"\.(?:py|md|yml|yaml|json|ts|js|cs|ps1|sh))"
    r"(?::\d+(?:-\d+)?)?"
    r"(?![\w./-])"
)

_VERDICT_RE = re.compile(
    r"(?im)^(?P<prefix>\s*(?:final\s+)?verdict\s*:\s*\[?)"
    r"(?P<token>PASS|WARN|CRITICAL_FAIL|REJECTED|FAIL|NEEDS_REVIEW|"
    r"NON_COMPLIANT|COMPLIANT|PARTIAL|UNKNOWN)"
    r"(?P<suffix>\]?.*)$"
)
_FAIL_VERDICTS = frozenset(
    {"CRITICAL_FAIL", "REJECTED", "FAIL", "NEEDS_REVIEW", "NON_COMPLIANT"}
)
_PRE_EXISTING_MARKER = "[pre-existing - not in this PR diff]"

# A location value is a file path when it contains a path separator or a
# known extension.  Values like ``line 42`` or ``N/A`` are not file paths.
# For slash-based paths, require at least one segment with more than one
# character to exclude notations like ``N/A``.
_PATH_EXTENSIONS = frozenset(
    {".py", ".md", ".yml", ".yaml", ".json", ".ts", ".js", ".cs", ".ps1", ".sh"}
)


def _looks_like_path(value: str) -> bool:
    """Return True when *value* looks like a file path, not a prose token.

    Rejects single-character-per-segment notations like ``N/A`` or ``x/y``
    (both slash-separated but not file paths), and generic prose tokens
    without any path-like structure.
    """
    if "/" in value or "\\" in value:
        # Require at least one segment with more than one character so that
        # notations like ``N/A`` (each segment is a single letter) are
        # rejected as prose tokens.
        separator = "/" if "/" in value else "\\"
        segments = value.split(separator)
        if all(len(seg) <= 1 for seg in segments if seg):
            return False
        return True
    dot_pos = value.rfind(".")
    if dot_pos >= 0 and value[dot_pos:].lower() in _PATH_EXTENSIONS:
        return True
    return False


def _strip_line_suffix(location: str) -> str:
    """Strip a ``:line`` or ``:line-range`` suffix from a location value."""
    return re.sub(r":\d+(-\d+)?$", "", location)


def get_diff_files(worktree: str, base_branch: str) -> list[str] | None:
    """Return the list of files changed in the PR diff.

    Returns *None* when git is unavailable or the command fails so callers
    can degrade gracefully (exit 0 with a warning rather than blocking a
    review entirely on a git error).
    """
    if not shutil.which("git"):
        return None
    try:
        result = subprocess.run(
            ["git", "-C", worktree, "diff", "--name-only", f"origin/{base_branch}...HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]
    except (OSError, subprocess.TimeoutExpired):
        return None


def extract_locations(text: str) -> list[str]:
    """Extract file paths from ``location:`` fields and prose in *text*."""
    paths: list[str] = []
    for match in _LOCATION_FIELD_RE.finditer(text):
        raw = match.group(1).strip().strip("`").strip("'\"")
        path = _strip_line_suffix(raw)
        if _looks_like_path(path):
            paths.append(path)
    for match in _PROSE_PATH_RE.finditer(text):
        path = _strip_line_suffix(match.group(1).strip().strip("`").strip("'\""))
        if _looks_like_path(path) and path not in paths:
            paths.append(path)
    return paths


def _file_in_diff(location: str, diff_files: list[str]) -> bool:
    """Return True when *location* matches a file in *diff_files*.

    Supports suffix matching: ``scripts/foo.py`` matches both
    ``scripts/foo.py`` and ``path/to/scripts/foo.py`` in the diff.
    """
    for diff_file in diff_files:
        if diff_file == location:
            return True
        if diff_file.endswith(f"/{location}") or location.endswith(f"/{diff_file}"):
            return True
    return False


def validate_scope(text: str, diff_files: list[str]) -> tuple[list[str], list[str]]:
    """Return (in_scope, out_of_scope) location lists for *text*.

    When *diff_files* is empty the function treats all locations as in-scope.
    This is intentional: an empty diff means either the diff query returned
    no changed files (nothing to scope-check against) or the base branch
    could not be resolved.  In both cases blocking findings would produce
    false positives, so we degrade gracefully.  The caller (``main``) already
    handles ``None`` (git unavailable) separately; an empty list here means
    git succeeded but the three-dot range produced no file names.
    """
    locations = extract_locations(text)
    if not diff_files:
        return locations, []
    in_scope: list[str] = []
    out_of_scope: list[str] = []
    for loc in locations:
        if _file_in_diff(loc, diff_files):
            in_scope.append(loc)
        else:
            out_of_scope.append(loc)
    return in_scope, out_of_scope


def extract_verdict(text: str) -> str | None:
    """Return the first verdict token in *text*, if present."""
    match = _VERDICT_RE.search(text)
    return match.group("token") if match else None


def scope_adjusted_verdict(text: str, diff_files: list[str]) -> str | None:
    """Return the verdict after removing out-of-scope blocking weight.

    If all cited file locations are outside the PR diff, a blocking verdict
    cannot belong to this change. Downgrade it to WARN so the finding stays
    visible without blocking the PR. Mixed in-scope and out-of-scope outputs
    keep their original verdict because at least one cited finding belongs to
    the reviewed diff.
    """
    verdict = extract_verdict(text)
    if verdict is None:
        return None
    in_scope, out_of_scope = validate_scope(text, diff_files)
    if out_of_scope and not in_scope and verdict in _FAIL_VERDICTS:
        return "WARN"
    return verdict


def _replace_verdict(text: str, verdict: str) -> str:
    """Replace the first verdict token in *text* with *verdict*."""
    def replace(match: re.Match[str]) -> str:
        return f"{match.group('prefix')}{verdict}{match.group('suffix')}"

    return _VERDICT_RE.sub(replace, text, count=1)


def _annotate_out_of_scope_lines(text: str, out_of_scope: list[str]) -> str:
    if not out_of_scope:
        return text

    out_of_scope_set = set(out_of_scope)
    lines: list[str] = []
    for line in text.splitlines(keepends=True):
        match = _LOCATION_FIELD_RE.search(line)
        location = None
        if match:
            location = _strip_line_suffix(match.group(1).strip().strip("`").strip("'\""))
        else:
            prose_match = _PROSE_PATH_RE.search(line)
            if prose_match:
                location = _strip_line_suffix(
                    prose_match.group(1).strip().strip("`").strip("'\"")
                )
        if location is None:
            lines.append(line)
            continue
        if location in out_of_scope_set and _PRE_EXISTING_MARKER not in line:
            newline = "\n" if line.endswith("\n") else ""
            body = line[:-1] if newline else line
            lines.append(f"{body} {_PRE_EXISTING_MARKER}{newline}")
        else:
            lines.append(line)
    return "".join(lines)


def format_scope_checked_text(text: str, diff_files: list[str]) -> str:
    """Return axis text with out-of-scope findings marked and verdict adjusted."""
    in_scope, out_of_scope = validate_scope(text, diff_files)
    if not out_of_scope:
        return text

    adjusted_text = _annotate_out_of_scope_lines(text, out_of_scope)
    original_verdict = extract_verdict(text)
    adjusted_verdict = scope_adjusted_verdict(text, diff_files)
    if (
        original_verdict is not None
        and adjusted_verdict is not None
        and adjusted_verdict != original_verdict
    ):
        adjusted_text = _replace_verdict(adjusted_text, adjusted_verdict)
        adjusted_text = (
            adjusted_text.rstrip()
            + "\n\nScope adjustment: original verdict "
            + f"{original_verdict} downgraded to {adjusted_verdict} because "
            + "every cited location is outside the PR diff.\n"
        )
    return adjusted_text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate review-axis finding locations against the PR diff.",
    )
    parser.add_argument(
        "--worktree",
        default=".",
        help="Path to the git worktree to run `git diff` in (default: CWD).",
    )
    parser.add_argument(
        "--base-branch",
        default="main",
        help="Base branch for the three-dot diff (default: main).",
    )
    parser.add_argument(
        "--text",
        help="Axis output text to validate.  Reads from stdin when omitted.",
    )
    parser.add_argument(
        "--emit-adjusted-text",
        action="store_true",
        help=(
            "Print axis text with out-of-scope findings marked and any "
            "all-out-of-scope blocking verdict downgraded to WARN."
        ),
    )
    args = parser.parse_args(argv)

    text = args.text if args.text is not None else sys.stdin.read()

    worktree = str(Path(args.worktree).resolve())
    diff_files = get_diff_files(worktree, args.base_branch)

    if diff_files is None:
        print(
            f"WARNING: could not get diff for origin/{args.base_branch}...HEAD "
            f"in {worktree}; skipping scope check",
            file=sys.stderr,
        )
        if args.emit_adjusted_text:
            print(text, end="" if text.endswith("\n") else "\n")
        return 0

    in_scope, out_of_scope = validate_scope(text, diff_files)
    if args.emit_adjusted_text:
        print(format_scope_checked_text(text, diff_files), end="")

    if out_of_scope:
        unique_oos = sorted(set(out_of_scope))
        print(
            f"OUT-OF-SCOPE ({len(unique_oos)} location(s) not in PR diff):",
            file=sys.stderr,
        )
        for loc in unique_oos:
            print(f"  {loc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Check whether an open PR already addresses a given issue (issue #2477).

Pre-flight guard against competing PRs: before an autonomous pipeline or an
interactive session opens a new PR for an issue, it should confirm no open PR
already claims that issue via a closing keyword. Two workers acting on the same
issue otherwise open duplicate PRs (the #2477 failure mode).

Detection is deterministic: list open PRs and match each body/title against the
GitHub closing-keyword forms for the issue number (Fixes/Closes/Resolves),
rather than a fragile free-text search.

Exit codes follow ADR-035:
    0 - No open PR claims implementation ownership (safe to proceed)
    1 - One or more open PRs claim implementation ownership (do not open a duplicate)
    2 - Config error (plugin lib path missing)
    3 - External error (gh/API failure)
    4 - Auth error (not authenticated)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

_plugin_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
_workspace = os.environ.get("GITHUB_WORKSPACE")
if _plugin_root and os.path.isdir(os.path.join(_plugin_root, "lib", "github_core")):
    _lib_dir = os.path.join(_plugin_root, "lib")
elif _workspace:
    _lib_dir = os.path.join(_workspace, ".claude", "lib")
else:
    _lib_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "lib")
    )
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
    sys.exit(2)  # Config error per ADR-035
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (
    assert_gh_authenticated,
    resolve_repo_params,
)
from github_core.output import (
    add_output_format_arg,
    get_output_format,
    write_skill_error,
    write_skill_output,
)

# GitHub closing keywords identify PRs that claim implementation ownership. Issue
# #2477 originally included "Refs", but issue #4894 proved that diagnostic
# references can name unrelated blockers without implementing them.
_KEYWORDS = "close[sd]?|fix(e[sd])?|resolve[sd]?"
_GH_TIMEOUT_SECONDS = 30
_GIT_TIMEOUT_SECONDS = 10
_PullRequestPayload = dict[str, object]

# Span-exclusion patterns for issue #3827: GitHub does not parse a closing
# keyword inside an inline code span or a fenced code block (confirmed via
# the GraphQL `closingIssuesReferences` API), so a match inside either must
# not count as the PR claiming implementation ownership of the issue. Ported
# verbatim from `scripts/validation/pr_description.py` (`_INLINE_CODE_SPAN`
# and `_fenced_code_block_ranges`), which solves the identical problem for
# the PR description validator's closing-link check (see that module's
# `validate_closing_links`, issue #3827, PRs #4078 and #4716).
#
# Stricter/looser/different than canonical: identical patterns, same
# exclusion semantics. The one difference is what a match inside the
# excluded span means: `pr_description.py` reports a CRITICAL (the author
# meant to close the issue and the markup silently defeated it), while this
# module simply treats the match as not claiming ownership at all (a PR
# quoting or documenting a closing keyword is not implementing the issue).
#
# CommonMark 0.31.2 section 4.5 says the content of a fenced block runs
# "until a closing code fence of the same type as the code block began with,
# or until the end of the containing block", so an opening fence with no
# closing fence still opens a code block that runs to end of input, and a
# closing fence must use the same character as the opener and be AT LEAST as
# long, not exactly as long. Without the end-of-input fallback a body ending
# mid-fence matched neither span pattern, so a keyword GitHub never links was
# read as a real claim (Copilot review on PR #5371). A fixed-length `\1`
# backreference cannot express "at least as long", so `_fenced_code_block_ranges`
# below finds each opener's run length first and builds that opener's closer
# pattern dynamically (Copilot review on PR #5371, round 3). Both mechanisms
# live in `pr_description.py` too, so the "ported verbatim" claim above stays
# true.
#
# `[ ]{0,3}` on both the opening and closing fence lines tolerates the
# indentation CommonMark 0.31.2 section 4.5 allows (up to three spaces); a
# fourth space starts an indented code block instead, a different construct
# this module does not classify. `[ \t]*$` on the closer requires the line to
# hold nothing but the fence run and optional trailing whitespace, so a line
# like `` ```not-a-closer `` cannot end the block early: a bare same-length
# match alone matched any line merely *starting* with the same run, closing
# the block one line too soon and letting a real claim past it that GitHub
# still renders as code (Copilot review on PR #5371, round 2).
#
# CommonMark allows a line ending inside a code span for every delimiter
# length, not just short runs; confining the 3+ backtick branch to a single
# line missed a real multiline inline span and read the keyword inside it as
# a genuine bare claim (Copilot review on PR #5371, round 4). Letting that
# branch go multiline means it can also match all the way across a real
# fenced block; `_code_spans_outside_fences` below handles that at the call
# site by dropping any span match that overlaps a real fence, so a
# fence still reports as fenced rather than relabeled as an inline span.
#
# The two `_FENCE_OPEN_LINE` alternatives are deliberately asymmetric.
# CommonMark 0.31.2 section 4.5: "If the info string comes after a backtick
# fence, it may not contain any backtick characters." A tilde fence's info
# string has no such restriction. `(?![^\n]*`)` on the backtick alternative
# rejects a line like ` ```lang`x` ` from opening a fence at all, exactly as
# CommonMark reads it as ordinary text instead (Copilot review on PR #5371,
# round 4).
#
# Known limitation, left deliberately out of scope: this line-anchored
# search does not reparse list-item or blockquote container prefixes
# (`- ` / `> `) the way CommonMark does, so a fence nested inside a list
# item or blockquote is not recognized as a fence at all (Copilot review on
# PR #5371, round 4, suppressed comments). A closing keyword inside such a
# nested fence is therefore read as an unfenced bare claim rather than
# excluded. This preflight targets the common shape of a PR description (a
# top-level fenced example), not arbitrary nested Markdown containers;
# closing this gap needs container-prefix-aware line parsing, which is a
# larger change than this fix round scopes to. Same limitation in
# `pr_description.py`.
_INLINE_CODE_SPAN = re.compile(
    r"(?<!`)(`{1,2})(?!`)(?:[^\n]|\n(?!\s*\n))+?(?<!`)\1(?!`)"
    r"|"
    r"(?<!`)(`{3,})(?!`)(?:[^\n]|\n(?!\s*\n))+?(?<!`)\2(?!`)"
)
_FENCE_OPEN_LINE = re.compile(
    r"^[ ]{0,3}(?:(`{3,})(?![^\n]*`)|(~{3,}))[^\n]*\n",
    re.MULTILINE,
)


def _fenced_code_block_ranges(text: str) -> list[tuple[int, int]]:
    """Return (start, end) pairs for every fenced code block in ``text``.

    Walks openers left to right, and for each one builds a closer pattern
    sized to that opener's own fence-character and run length (CommonMark
    0.31.2 4.5: same character, length >= opener length). An opener with no
    matching closer runs to the end of the text. ``pos`` advances to the end
    of each resolved block so a fence-like line inside one block's content is
    never re-read as a fresh opener.
    """
    ranges: list[tuple[int, int]] = []
    pos = 0
    while True:
        opener = _FENCE_OPEN_LINE.search(text, pos)
        if opener is None:
            break
        run = opener.group(1) or opener.group(2)
        closer_pattern = re.compile(
            rf"^[ ]{{0,3}}{re.escape(run[0])}{{{len(run)},}}[ \t]*$",
            re.MULTILINE,
        )
        closer = closer_pattern.search(text, opener.end())
        end = closer.end() if closer else len(text)
        ranges.append((opener.start(), end))
        pos = end
    return ranges


def _span_ranges(text: str, pattern: re.Pattern[str]) -> list[tuple[int, int]]:
    """Return (start, end) pairs for all non-overlapping matches of pattern."""
    return [(m.start(), m.end()) for m in pattern.finditer(text)]


def _in_any_range(pos: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start <= pos < end for start, end in ranges)


def _ranges_overlap(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _code_spans_outside_fences(
    text: str, fenced_ranges: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    """Inline code-span ranges, excluding any that overlap a real fence.

    A real fence always wins (CommonMark parses block structure before
    inline content, so nothing inside a fenced block's raw text is itself
    inline-parsed). Rejecting only a span whose START falls inside a fence
    (round 4) misses a span that STARTS before a fence and ENDS after it --
    e.g. a 4-backtick run in the paragraph before a fence, paired with a
    later 4-backtick run after the fence closes -- which still engulfs the
    fence and any real claim right after it (Copilot review on PR #5371,
    round 5). Rejecting on any overlap closes both shapes. Ported verbatim
    from `pr_description.py`.
    """
    return [
        span
        for span in _span_ranges(text, _INLINE_CODE_SPAN)
        if not any(_ranges_overlap(span, fenced) for fenced in fenced_ranges)
    ]


def references_issue(text: str, issue: int, repo_slug: str = "") -> bool:
    """Return True when ``text`` claims ``issue`` via a closing keyword.

    A closing keyword found only inside an inline code span or a fenced code
    block does not count: GitHub never creates a real closing link there, so
    treating it as a claim of implementation ownership would let a PR that
    merely quotes or documents a closing keyword suppress a legitimate new PR
    as a false duplicate (issue #3827).
    """

    if not text:
        return False
    # Normalize CRLF to LF: the fence and span regexes use \n anchors, so
    # CRLF input causes closers to go unrecognized and extends fenced blocks
    # through EOF (Devin review on PR #5371).
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    issue_ref = rf"#{issue}\b"
    if repo_slug:
        issue_ref = rf"(?:{re.escape(repo_slug)}#|#){issue}\b"
    pattern = re.compile(rf"(?i)\b(?:{_KEYWORDS})\b[\s:]*{issue_ref}")
    fenced_ranges = _fenced_code_block_ranges(text)
    code_span_ranges = _code_spans_outside_fences(text, fenced_ranges)
    for match in pattern.finditer(text):
        pos = match.start()
        if _in_any_range(pos, fenced_ranges) or _in_any_range(pos, code_span_ranges):
            continue
        return True
    return False


def _run(cmd: list[str], *, timeout: int = _GH_TIMEOUT_SECONDS) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as err:
        raise RuntimeError(f"{cmd[0]} timed out after {timeout} seconds") from err
    except OSError as err:
        raise RuntimeError(f"failed to run {cmd[0]}: {err}") from err


def current_branch() -> str:
    """Return the active branch name when available."""

    head_ref = os.environ.get("GITHUB_HEAD_REF")
    if head_ref:
        return head_ref
    try:
        result = _run(["git", "branch", "--show-current"], timeout=_GIT_TIMEOUT_SECONDS)
    except RuntimeError:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def current_login() -> str:
    """Return the authenticated gh user login."""

    result = _run(["gh", "api", "user", "--jq", ".login"])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "gh api user failed")
    login = result.stdout.strip()
    if not login:
        raise RuntimeError("gh api user returned empty login")
    return login


def _as_text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _iter_pull_requests(payload: object) -> list[_PullRequestPayload]:
    if not isinstance(payload, list):
        return []
    prs: list[_PullRequestPayload] = []
    for item in payload:
        if isinstance(item, dict):
            prs.append(item)
        elif isinstance(item, list):
            prs.extend(pr for pr in item if isinstance(pr, dict))
    return prs


def _head_ref(pr: _PullRequestPayload) -> str:
    head = pr.get("head")
    if isinstance(head, dict):
        return _as_text(head.get("ref"))
    return _as_text(pr.get("headRefName"))


def _author_login(pr: _PullRequestPayload) -> str:
    user = pr.get("user")
    if isinstance(user, dict):
        return _as_text(user.get("login"))
    return _as_text(pr.get("author"))


def _is_self_branch_pr(
    author_login: str,
    head_ref: str,
    *,
    current_branch_name: str,
    current_user_login: str,
) -> bool:
    """Return True when a PR is the current user's own current-branch PR.

    Suppression exists so the preflight does not flag the PR that belongs to the
    branch you are already on. It applies only when the current branch name is
    known and matches the PR head exactly.

    An empty ``current_branch_name`` (detached HEAD, or CI without
    ``GITHUB_HEAD_REF``) is NOT a match. Treating empty as a match suppressed
    every PR by the current user, so in a single-author repo the duplicate-PR
    guard reported zero coverage for every issue (issue #4965).
    """
    if not current_user_login or author_login != current_user_login:
        return False
    if not current_branch_name:
        return False
    return head_ref == current_branch_name


def filter_prs_for_issue(
    prs: object,
    issue: int,
    *,
    repo_slug: str = "",
    current_branch_name: str = "",
    current_user_login: str = "",
) -> list[_PullRequestPayload]:
    """Return open PRs whose title or body claims implementation of ``issue``.

    Pure matching logic, separated from the ``gh`` fetch so the suppression
    rules are deterministically testable (issue #4965).

    Title and body are matched independently, never as one joined string.
    GitHub renders them as two separate Markdown documents, so a code span
    cannot straddle them. Joining them let an unmatched backtick in the title
    pair with one in the body to form a span that swallowed a real closing
    keyword between them, hiding a genuine duplicate PR (Copilot review on PR
    #5371). Each field now gets its own span-exclusion pass.
    """
    matches: list[_PullRequestPayload] = []
    for pr in _iter_pull_requests(prs):
        head_ref = _head_ref(pr)
        author_login = _author_login(pr)
        title = _as_text(pr.get("title"))
        body = _as_text(pr.get("body"))
        if not (
            references_issue(title, issue, repo_slug=repo_slug)
            or references_issue(body, issue, repo_slug=repo_slug)
        ):
            continue
        if _is_self_branch_pr(
            author_login,
            head_ref,
            current_branch_name=current_branch_name,
            current_user_login=current_user_login,
        ):
            continue
        matches.append({
            "number": pr.get("number"),
            "title": title,
            "url": _as_text(pr.get("html_url") or pr.get("url")),
            "head": head_ref,
            "author": author_login,
        })
    return matches


def find_open_prs_for_issue(
    owner: str,
    repo: str,
    issue: int,
    *,
    current_branch_name: str = "",
    current_user_login: str = "",
) -> list[_PullRequestPayload]:
    """Fetch open PRs and return those claiming implementation of ``issue``."""

    result = _run(
        ["gh", "api", f"repos/{owner}/{repo}/pulls?state=open&per_page=100",
         "--paginate", "--slurp"],
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "gh api pulls failed")
    try:
        prs = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError) as err:
        raise RuntimeError("could not parse gh api pulls output") from err
    return filter_prs_for_issue(
        prs,
        issue,
        repo_slug=f"{owner}/{repo}",
        current_branch_name=current_branch_name,
        current_user_login=current_user_login,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check whether an open PR already addresses an issue.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument("--issue", type=int, required=True, help="Issue number")
    add_output_format_arg(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo
    fmt = get_output_format(args.output_format)

    try:
        matches = find_open_prs_for_issue(
            owner,
            repo,
            args.issue,
            current_branch_name=current_branch(),
            current_user_login=current_login(),
        )
    except RuntimeError as err:
        write_skill_error(
            str(err), 3, error_type="ApiError",
            output_format=fmt, script_name="check_existing_pr_for_issue.py",
        )
        raise SystemExit(3) from err

    data = {
        "issue": args.issue,
        "existing_pr_count": len(matches),
        "existing_prs": matches,
    }
    if matches:
        summary = ", ".join(f"#{m['number']}" for m in matches)
        write_skill_error(
            f"Issue #{args.issue} already has open PR(s): {summary}. "
            "Do not open a duplicate; coordinate on the existing PR.",
            1, error_type="General",
            output_format=fmt, script_name="check_existing_pr_for_issue.py",
            extra=data,
        )
        raise SystemExit(1)

    write_skill_output(
        data, output_format=fmt,
        human_summary=(
            f"No open PR claims implementation ownership of issue #{args.issue}; "
            "safe to proceed."
        ),
        status="PASS", script_name="check_existing_pr_for_issue.py",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

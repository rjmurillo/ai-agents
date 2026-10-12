#!/usr/bin/env python3
"""Verify commit references in resolved review threads are in the PR head."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from html.parser import HTMLParser
from typing import Any

_plugin_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root and os.path.isdir(os.path.join(_plugin_root, "lib", "github_core")):
    _lib_dir = os.path.join(_plugin_root, "lib")
else:
    _lib_dir = ""
    _here = os.path.abspath(os.path.dirname(__file__))
    _ancestor = _here
    while True:
        _candidate = os.path.join(_ancestor, "lib", "github_core")
        if os.path.isdir(_candidate):
            _lib_dir = os.path.dirname(_candidate)
            break
        _parent = os.path.dirname(_ancestor)
        if _parent == _ancestor:
            break
        _ancestor = _parent
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
    sys.exit(2)

if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import assert_gh_authenticated, gh_graphql, resolve_repo_params

try:
    from markdown_it import MarkdownIt
    from markdown_it.token import Token

    _MARKDOWN: MarkdownIt | None = MarkdownIt("commonmark").enable("table")
except ImportError:  # pragma: no cover - exercised when markdown-it-py is missing
    # Plugin scripts run under bare python3 (plugin-self-containment MUST 4), so
    # the parser is optional. Without it the raw body is scanned, which fails closed.
    _MARKDOWN = None

_MAX_THREAD_PAGES = 50
_GIT_TIMEOUT_SECONDS = 30
# Which text the SHA regex read: the rendered text, or the raw body as a
# fail-closed fallback (reported per reference and per comment).
TEXT_MODE_PARSED = "parsed"
TEXT_MODE_RAW_PARSER_MISSING = "raw-parser-missing"
TEXT_MODE_RAW_NESTING_LIMIT = "raw-nesting-limit"
_SHA_RE = re.compile(r"\b([0-9a-f]{7,40})\b", re.IGNORECASE)
_COMMIT_URL_RE = re.compile(r"/commits?/([0-9a-f]{7,40})\b", re.IGNORECASE)

_THREADS_QUERY = """\
query($owner: String!, $repo: String!, $prNumber: Int!, $cursor: String) {
    repository(owner: $owner, name: $repo) {
        pullRequest(number: $prNumber) {
            headRefOid
            reviewThreads(first: 100, after: $cursor) {
                pageInfo {
                    hasNextPage
                    endCursor
                }
                nodes {
                    id
                    isResolved
                    path
                    line
                    comments(first: 100) {
                        totalCount
                        nodes {
                            id
                            databaseId
                            body
                            author { login }
                            createdAt
                        }
                    }
                }
            }
        }
    }
}"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check resolved review-thread commit references.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--pull-request",
        type=int,
        required=True,
        help="Pull request number",
    )
    parser.add_argument(
        "--repo-path",
        default=".",
        help="Local git repository path used for ancestry checks.",
    )
    return parser


# Markdown that GitHub hides or shows as code must not feed the SHA regex. Bots
# hide hex IDs in HTML comments (CodeRabbit: <!-- cr-comment:v1:<24 hex> -->).
# markdown-it-py parses the body; html.parser reads raw HTML blocks. Fenced and
# indented code blocks are skipped on purpose, since they quote commands, not fix
# references. A link target counts only when its URL names a commit
# (/commit/<sha>); unused reference definitions do not render, so they are not read.
#
# html.parser changed across CPython patch releases (gh-135664): older builds end
# "<!-->" at a later "-->" and parse fewer raw-text elements. _HtmlText pins the
# fixed behavior, copied from CPython 3.14.7 html/parser.py, so the SHAs found do
# not depend on which python3 runs the gate.
_COMMENT_ABRUPT_CLOSE_RE = re.compile(r"-?>")
_COMMENT_CLOSE_RE = re.compile(r"--!?>")
# Raw-text elements whose text never renders; GitHub strips them from comments.
# xmp is raw text too, but its text renders, so it is still read.
_UNRENDERED_ELEMENTS = frozenset({"script", "style", "iframe", "noembed", "noframes"})


class _HtmlText(HTMLParser):
    # typeshed marks this Final, but html.parser reads it through self, so a
    # subclass value pins the raw-text set on every CPython version.
    CDATA_CONTENT_ELEMENTS = ("script", "style", "xmp", "iframe", "noembed", "noframes")  # type: ignore[misc]

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._unrendered_tag: str | None = None
        self._at_eof = False

    def close(self) -> None:
        self._at_eof = True
        super().close()

    def parse_comment(self, i: int, report: bool = True) -> int:
        # https://html.spec.whatwg.org/multipage/parsing.html#comment-start-state
        # An unclosed comment runs to end of input (older CPython emits it as text).
        rawdata = self.rawdata
        match = _COMMENT_ABRUPT_CLOSE_RE.match(rawdata, i + 4)
        if not match:
            match = _COMMENT_CLOSE_RE.search(rawdata, i + 4)
        if match is not None:
            start, end = match.start(), match.end()
        elif self._at_eof:
            start = end = len(rawdata)
        else:
            return -1
        if report:
            self.handle_comment(rawdata[i + 4 : start])
        return end

    def handle_data(self, data: str) -> None:
        if self._unrendered_tag is None:
            self.parts.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _UNRENDERED_ELEMENTS:
            self._unrendered_tag = tag
        self.parts.extend(_commit_refs(value) for name, value in attrs if name == "href" and value)

    def handle_endtag(self, tag: str) -> None:
        if tag == self._unrendered_tag:
            self._unrendered_tag = None


def _commit_refs(url: str) -> str:
    # A link cites a commit only through a /commit/<sha> path. Other URL parts
    # (attachment UUIDs, comment IDs) are hex-like but are not commits.
    return " ".join(_COMMIT_URL_RE.findall(url))


def _html_block_text(html: str) -> str:
    parser = _HtmlText()
    parser.feed(html)
    parser.close()
    return " ".join(parser.parts)


def _is_gfm_comment(html: str) -> bool:
    # GitHub follows GFM 0.29: a comment body cannot start with ">" or "->",
    # contain "--", or end with "-". Anything else renders as visible text.
    # markdown-it emits html_inline comments only in complete <!-- ... --> form.
    body = html[4:-3]
    return not (body.startswith((">", "->")) or "--" in body or body.endswith("-"))


def _inline_text(token: Token) -> str:
    parts: list[str] = []
    for child in token.children or []:
        if child.type in ("text", "code_inline"):
            parts.append(child.content)
        elif child.type in ("softbreak", "hardbreak"):
            parts.append("\n")
        elif child.type == "link_open":
            parts.append(f" {_commit_refs(str(child.attrs.get('href', '')))} ")
        elif child.type == "html_inline" and child.content.startswith("<!--"):
            parts.append(" " if _is_gfm_comment(child.content) else child.content)
        elif child.type == "html_inline":
            parts.append(f" {_html_block_text(child.content)} ")
        else:
            parts.append(" ")
    return "".join(parts)


def _reached_nesting_limit(tokens: list[Token], max_nesting: int) -> bool:
    # markdown-it drops content past maxNesting without raising, and a token at
    # maxNesting - 1 cannot tell a complete parse from a truncated one.
    children = (child for token in tokens for child in token.children or [])
    return any(token.level >= max_nesting - 1 for token in (*tokens, *children))


def _visible_text(body: str) -> tuple[str, str]:
    if _MARKDOWN is None:
        return body, TEXT_MODE_RAW_PARSER_MISSING
    env: dict[str, Any] = {}
    tokens = _MARKDOWN.parse(body, env)
    if _reached_nesting_limit(tokens, _MARKDOWN.options["maxNesting"]):
        return body, TEXT_MODE_RAW_NESTING_LIMIT
    # The commonmark preset reads "[^1]: text" as a link definition, but GitHub
    # renders it as a visible footnote, so its text is read here.
    references = env.get("references", {}).items()
    parts = [f"{ref['href']} {ref['title']}" for label, ref in references if label.startswith("^")]
    for token in tokens:
        if token.type == "inline":
            parts.append(_inline_text(token))
        elif token.type == "html_block":
            parts.append(_html_block_text(token.content))
    return "\n".join(parts), TEXT_MODE_PARSED


def scan_comment(body: str) -> tuple[list[str], str]:
    """Return the SHAs a comment shows and the text mode that found them."""
    visible, text_mode = _visible_text(body)
    # A link and its definition name the same commit; check each SHA once.
    shas = dict.fromkeys(match.group(1).lower() for match in _SHA_RE.finditer(visible))
    return list(shas), text_mode


def extract_shas(body: str) -> list[str]:
    return scan_comment(body)[0]


def fetch_review_threads(
    owner: str,
    repo: str,
    pull_request: int,
) -> tuple[str, list[dict[str, Any]], bool]:
    threads: list[dict[str, Any]] = []
    head_sha = ""
    cursor: str | None = None

    for _page in range(_MAX_THREAD_PAGES):
        variables: dict[str, Any] = {
            "owner": owner,
            "repo": repo,
            "prNumber": pull_request,
        }
        if cursor is not None:
            variables["cursor"] = cursor
        data = gh_graphql(_THREADS_QUERY, variables)
        pull_request_data = (data.get("repository") or {}).get("pullRequest")
        if not isinstance(pull_request_data, dict):
            raise RuntimeError(f"PR #{pull_request} not found")
        head_sha = str(pull_request_data.get("headRefOid") or head_sha)
        review_threads = pull_request_data.get("reviewThreads")
        if not isinstance(review_threads, dict):
            raise RuntimeError("reviewThreads missing from GraphQL response")
        page_nodes = review_threads.get("nodes") or []
        if not isinstance(page_nodes, list):
            raise RuntimeError("reviewThreads.nodes is not a list")
        threads.extend(t for t in page_nodes if isinstance(t, dict))

        page_info = review_threads.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            comments_complete = all(_thread_comments_complete(t) for t in threads)
            return head_sha, threads, comments_complete
        cursor = page_info.get("endCursor")
        if not cursor:
            return head_sha, threads, False
    return head_sha, threads, False


def _thread_comments_complete(thread: dict[str, Any]) -> bool:
    comments = thread.get("comments")
    if not isinstance(comments, dict):
        return False
    nodes = comments.get("nodes")
    if not isinstance(nodes, list):
        return False
    total = comments.get("totalCount")
    if not isinstance(total, int):
        return False
    return total == len(nodes)


def _latest_comment(thread: dict[str, Any]) -> dict[str, Any] | None:
    comments = thread.get("comments")
    if not isinstance(comments, dict):
        return None
    nodes = comments.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return None
    comment_nodes = [node for node in nodes if isinstance(node, dict)]
    if not comment_nodes:
        return None
    return max(comment_nodes, key=lambda c: str(c.get("createdAt") or ""))


def _git(repo_path: str, *args: str) -> tuple[int, str, str]:
    """Run git; a timeout or a git that cannot start returns rc -1 and the reason."""
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, *args],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return -1, "", f"git {args[0]} timed out after {_GIT_TIMEOUT_SECONDS}s"
    except OSError as exc:
        return -1, "", f"git could not run: {exc}"
    return result.returncode, result.stdout, result.stderr


def _git_error(stderr: str) -> str:
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    return f"git-error: {lines[0]}" if lines else "git-error"


def _classify_unresolved(sha: str, repo_path: str) -> tuple[bool, str, str]:
    returncode, stdout, stderr = _git(repo_path, "rev-parse", f"--disambiguate={sha}")
    if returncode != 0:
        return False, "invalid", _git_error(stderr)
    candidates = [line for line in stdout.splitlines() if line.strip()]
    if len(candidates) > 1:
        return False, "ambiguous", f"{len(candidates)} objects share this prefix"
    if candidates:
        return False, "invalid", "not-a-commit"
    return False, "invalid", "missing-object"


def check_ancestor(sha: str, head_sha: str, repo_path: str) -> tuple[bool, str, str]:
    """Classify a SHA as (reachable, status, detail).

    status is reachable, unreachable, ambiguous, or invalid; the gate fails on
    the last three. detail says why an invalid SHA failed: missing-object (not
    in the local clone), not-a-commit, or git-error: <git's first stderr line>.
    """
    # rev-parse --verify --quiet exits 1 when the name does not resolve to a
    # commit; any other nonzero exit is git itself failing.
    returncode, stdout, stderr = _git(
        repo_path, "rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}"
    )
    if returncode == 1:
        return _classify_unresolved(sha, repo_path)
    if returncode != 0:
        return False, "invalid", _git_error(stderr)

    returncode, _, stderr = _git(repo_path, "merge-base", "--is-ancestor", stdout.strip(), head_sha)
    if returncode == 0:
        return True, "reachable", ""
    if returncode == 1:
        return False, "unreachable", ""
    return False, "invalid", _git_error(stderr)


def _failure_reason(threads: list[dict[str, Any]], fetched_pages_complete: bool) -> str | None:
    if fetched_pages_complete:
        return None
    partial = [str(t.get("id")) for t in threads if not _thread_comments_complete(t)]
    if partial:
        return f"comments not fully fetched for thread(s): {', '.join(partial)}"
    return (
        "review thread pagination incomplete "
        f"(page cap {_MAX_THREAD_PAGES} reached or end cursor missing)"
    )


def _reference(
    thread: dict[str, Any],
    comment: dict[str, Any],
    sha: str,
    text_mode: str,
    ancestry: tuple[bool, str, str],
) -> dict[str, Any]:
    reachable, status, detail = ancestry
    author = comment.get("author")
    return {
        "thread_id": thread.get("id"),
        "path": thread.get("path"),
        "line": thread.get("line"),
        "comment_id": comment.get("id"),
        "comment_database_id": comment.get("databaseId"),
        "comment_author": (author.get("login") if isinstance(author, dict) else ""),
        "comment_created_at": comment.get("createdAt"),
        "sha": sha,
        "reachable": reachable,
        "status": status,
        "detail": detail,
        "text_mode": text_mode,
    }


def build_report(
    owner: str,
    repo: str,
    pull_request: int,
    head_sha: str,
    threads: list[dict[str, Any]],
    fetched_pages_complete: bool,
    repo_path: str,
) -> dict[str, Any]:
    references: list[dict[str, Any]] = []
    raw_scan_comments: list[dict[str, Any]] = []
    # One git lookup per SHA for the whole run, however many threads cite it.
    ancestry: dict[str, tuple[bool, str, str]] = {}
    resolved_threads = [t for t in threads if t.get("isResolved")]
    for thread in resolved_threads:
        comment = _latest_comment(thread)
        if comment is None:
            continue
        shas, text_mode = scan_comment(str(comment.get("body") or ""))
        if text_mode != TEXT_MODE_PARSED:
            raw_scan_comments.append(
                {
                    "thread_id": thread.get("id"),
                    "comment_id": comment.get("id"),
                    "text_mode": text_mode,
                }
            )
        for sha in shas:
            if sha not in ancestry:
                ancestry[sha] = check_ancestor(sha, head_sha, repo_path)
            references.append(_reference(thread, comment, sha, text_mode, ancestry[sha]))

    unreachable_count = sum(1 for r in references if r["status"] == "unreachable")
    invalid_count = sum(1 for r in references if r["status"] == "invalid")
    ambiguous_count = sum(1 for r in references if r["status"] == "ambiguous")
    return {
        "success": fetched_pages_complete,
        "failure_reason": _failure_reason(threads, fetched_pages_complete),
        "pull_request": pull_request,
        "owner": owner,
        "repo": repo,
        "head_sha": head_sha,
        "thread_count": len(threads),
        "resolved_thread_count": len(resolved_threads),
        "sha_reference_count": len(references),
        "reachable_count": sum(1 for r in references if r["status"] == "reachable"),
        "unreachable_count": unreachable_count,
        "invalid_count": invalid_count,
        "ambiguous_count": ambiguous_count,
        "git_error_count": sum(1 for r in references if r["detail"].startswith("git-error")),
        "fetched_pages_complete": fetched_pages_complete,
        "references": references,
        "raw_scan_comments": raw_scan_comments,
    }


def _warn_raw_scans(raw_scan_comments: list[dict[str, Any]]) -> None:
    # A missing parser is reported once at startup; a nesting fallback is
    # per comment, so name each one.
    for entry in raw_scan_comments:
        if entry["text_mode"] == TEXT_MODE_RAW_NESTING_LIMIT:
            print(
                f"Comment {entry['comment_id']} in thread {entry['thread_id']} nests past "
                f"the markdown parser limit; scanned its raw body ({entry['text_mode']}). "
                "Hidden hex IDs in it may report as invalid.",
                file=sys.stderr,
            )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.pull_request <= 0:
        print("Pull request number must be positive.", file=sys.stderr)
        return 2
    if _MARKDOWN is None:
        print(
            "markdown-it-py not installed; scanning raw comment bodies. "
            "Hidden bot IDs may report as invalid. Install markdown-it-py to fix.",
            file=sys.stderr,
        )

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo

    try:
        head_sha, threads, fetched_pages_complete = fetch_review_threads(
            owner,
            repo,
            args.pull_request,
        )
    except RuntimeError as exc:
        print(f"Failed to fetch review threads: {exc}", file=sys.stderr)
        return 3

    report = build_report(
        owner,
        repo,
        args.pull_request,
        head_sha,
        threads,
        fetched_pages_complete,
        args.repo_path,
    )
    _warn_raw_scans(report["raw_scan_comments"])
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Read a pull request's code-scanning alerts for /review (ADR-041 amendment).

Implements source 1 of the ADR-041 amendment 2026-11-09 ("Let /review read
CodeQL results as an explicit caller"). The full rules are in
``.project-toolkit/analysis/adr-041-review-caller-rules.md``; this script is the
Tier 1 reader. It prints one JSON envelope on stdout whose ``Data.outcome`` is:

    CURRENT       the pull request merge ref was analyzed at the reviewed HEAD
                  and the tree is clean; ``Data.alerts`` holds the attached alerts
    STALE         analyzed head differs from the reviewed HEAD, or the tree is dirty
    NOT ANALYZED  no CodeQL analysis exists for the pull request merge ref
    SKIPPED       the read could not complete; ``Data.reason`` says why

STALE, NOT ANALYZED, and SKIPPED are never clean. Only CURRENT carries alerts.

Rules this script enforces
--------------------------
* GET requests only. Every call is ``gh api --method GET``.
* List endpoints are read page by page until the response has no ``rel="next"``
  link. A failed page, an unparseable next link, a repeated link, or more than
  50 pages is SKIPPED, never a partial read (``lossless-queue-reads.md``).
* Tier 1 analyzes the pull request merge ref (``refs/pull/N/merge``), so the
  analysis ``commit_sha`` is a merge commit. The analyzed pull request head SHA
  is that merge commit's second parent, read from ``GET commits/{sha}``.
  "Current" means every category's newest analysis resolves to the reviewed HEAD.
* Origin filter (ADR-041 debate log 4): only analyses whose ``analysis_key`` is exactly
  ``.github/workflows/codeql-analysis.yml:analyze``, whose category fully matches
  ``/language:[a-z-]+``, and whose ``tool.name`` is ``CodeQL`` count, and only alerts
  whose most recent instance came from one. The tool name is never the only test. Every other upload
  is ignored, whatever tool name its SARIF carries. If only other workflows analyzed
  the ref, the outcome is NOT ANALYZED.
* Each alert reaches the caller as rule id, repository-relative path, and line.
  A rule id that fails ``^[A-Za-z0-9/_.-]{1,100}$`` is counted and dropped. No
  message or rule name is passed on.
* An alert is attached when any location (primary, related, or code-flow step)
  is in a file the diff touches. The path and line reported are those of the
  first such location. Other alerts are counted by file.
* Every ``Data.reason`` is a fixed string. Text from GitHub never reaches it.

Stricter/looser/different than canonical
========================================
Paging does not use ``github_core.api.gh_api_paginated``, which returns a partial
list on a failure after page 1. ``code_scanning_transport.py`` holds the GET-only
transport and the fail-loud paging, with the reason. This script keeps the
``assert_gh_authenticated`` and ``resolve_repo_params`` preflight of its siblings.

Fields verified against GitHub's published REST description
(github/rest-api-description, ``api.github.com.json``, 2026-11-09), operations
``code-scanning/list-alerts-for-repo`` (``rule.id``, ``state``,
``most_recent_instance.{commit_sha,category,location}``),
``code-scanning/list-recent-analyses`` (``id``, ``ref``, ``commit_sha``,
``category``, ``error``, ``created_at``), ``code-scanning/get-analysis``
(``application/sarif+json`` adds ``github/alertNumber``), and ``repos/get-commit``
(``parents[].sha``).

Exit codes (ADR-035):
    0  CURRENT, STALE, or NOT ANALYZED
    2  usage or configuration error (bad flag value, unreadable changed-files list)
    3  SKIPPED: GitHub request failed, paging incomplete, or response not usable
    4  SKIPPED: authorization or not-found refusal, or gh not authenticated
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from typing import Any, NoReturn
from urllib.parse import quote

# Plugin-root resolution: sibling scripts' shape (check_pr_live_state.py) minus its
# GITHUB_WORKSPACE branch, which would hard-code an upstream-only lib path.
_plugin_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root and os.path.isdir(os.path.join(_plugin_root, "lib", "github_core")):
    _lib_dir = os.path.join(_plugin_root, "lib")
else:
    _lib_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "lib")
    )
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
    sys.exit(2)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import assert_gh_authenticated, resolve_repo_params
from github_core.output import (
    add_output_format_arg,
    write_skill_error,
    write_skill_output,
)

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from code_scanning_errors import EXIT_AUTH, EXIT_EXTERNAL, SkipError
from code_scanning_sarif import normalize_changed_files, sarif_results_by_alert_number
from code_scanning_scope import is_origin_analysis, scope_alerts
from code_scanning_transport import (
    Transport,
    get_all_pages,
    get_object,
    gh_get,
    parse_json,
)

_SCRIPT_NAME = "get_pr_code_scanning_alerts.py"
_TOOL_NAME = "CodeQL"
_SARIF_MEDIA_TYPE = "application/sarif+json"
_PAGE_SIZE = 100
_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")

EXIT_OK = 0
EXIT_USAGE = 2

# ---------------------------------------------------------------------------
# Analyses: freshness
# ---------------------------------------------------------------------------


def merge_ref(pull_request: int) -> str:
    return f"refs/pull/{pull_request}/merge"


def _ref_query(pull_request: int) -> str:
    ref = quote(merge_ref(pull_request), safe="/")
    return f"ref={ref}&tool_name={_TOOL_NAME}&per_page={_PAGE_SIZE}"


def newest_analysis_per_category(analyses: list[Any]) -> list[dict[str, Any]]:
    """Return the newest analysis of each category.

    Tier 1 uploads one analysis per category (for example ``python`` and
    ``actions``) for each run. "Current" is judged on every category's newest
    analysis, so one lagging category cannot hide behind a fresh one.

    Raises:
        SkipError: an analysis lacks an integer ``id`` or a 40-hex ``commit_sha``.
    """
    newest: dict[str, dict[str, Any]] = {}
    for analysis in analyses:
        if not _is_usable_analysis(analysis):
            raise SkipError("analysis record had an unexpected shape")
        key = analysis.get("category") or analysis.get("analysis_key") or ""
        held = newest.get(key)
        if held is None or (analysis.get("created_at") or "") > (held.get("created_at") or ""):
            newest[key] = analysis
    return list(newest.values())


def _is_usable_analysis(analysis: object) -> bool:
    if not isinstance(analysis, dict):
        return False
    identifier = analysis.get("id")
    sha = analysis.get("commit_sha")
    return (
        isinstance(identifier, int)
        and not isinstance(identifier, bool)
        and isinstance(sha, str)
        and _FULL_SHA.fullmatch(sha) is not None
    )


def derive_analyzed_head(transport: Transport, owner: str, repo: str, merge_sha: str) -> str:
    """Return the pull request head SHA a merge-ref analysis covered.

    The analysis record stores the merge commit SHA (``refs/pull/N/merge``). That
    commit has two parents: the base tip first, the pull request head second. The
    head is therefore ``parents[1]``.

    Raises:
        SkipError: the commit does not have exactly two parents with 40-hex SHAs.
    """
    commit = get_object(transport, f"repos/{owner}/{repo}/commits/{merge_sha}")
    parents = commit.get("parents")
    if not isinstance(parents, list) or len(parents) != 2:
        raise SkipError("merge commit does not have two parents; analyzed head unknown")
    head = parents[1].get("sha") if isinstance(parents[1], dict) else None
    if not isinstance(head, str) or _FULL_SHA.fullmatch(head) is None:
        raise SkipError("merge commit parent had an unexpected shape")
    return head


# ---------------------------------------------------------------------------
# Outcome
# ---------------------------------------------------------------------------


def _read_sarif_index(
    transport: Transport, owner: str, repo: str, analyses: list[dict[str, Any]]
) -> dict[int, Any]:
    index: dict[int, Any] = {}
    for analysis in analyses:
        endpoint = f"repos/{owner}/{repo}/code-scanning/analyses/{analysis['id']}"
        _, body = transport(endpoint, _SARIF_MEDIA_TYPE)
        try:
            index.update(sarif_results_by_alert_number(parse_json(body)))
        except ValueError as exc:
            raise SkipError("analysis SARIF had an unexpected shape") from exc
    return index


def _stale(analyzed: list[str], reviewing: str) -> dict[str, Any]:
    shown = ",".join(sorted(set(analyzed)))
    return {
        "outcome": "STALE",
        "analyzed_head_sha": shown,
        "reviewing": reviewing,
        "status_line": f"CodeQL: STALE (analyzed {shown}, reviewing {reviewing})",
    }


def read_outcome(
    transport: Transport,
    *,
    owner: str,
    repo: str,
    pull_request: int,
    head_sha: str,
    tree_clean: bool,
    changed_files: frozenset[str],
) -> dict[str, Any]:
    """Return the Tier 1 outcome for one pull request.

    Raises:
        SkipError: the read could not complete. The caller reports SKIPPED.
    """
    base = f"repos/{owner}/{repo}/code-scanning"
    analyses = get_all_pages(transport, f"{base}/analyses?{_ref_query(pull_request)}")
    analyses = [a for a in analyses if is_origin_analysis(a)]
    if not analyses:
        return {"outcome": "NOT ANALYZED", "status_line": "CodeQL: NOT ANALYZED"}
    current = newest_analysis_per_category(analyses)
    if any(a.get("error") for a in current):
        raise SkipError("the analysis reported an error")
    heads = {
        a["commit_sha"]: derive_analyzed_head(transport, owner, repo, a["commit_sha"])
        for a in current
    }
    analyzed = list(heads.values())
    if not tree_clean:
        return _stale(analyzed, "working tree")
    if any(head != head_sha for head in analyzed):
        return _stale(analyzed, head_sha)
    alerts = get_all_pages(
        transport,
        f"{base}/alerts?{_ref_query(pull_request)}&state=open",
    )
    sarif_index = _read_sarif_index(transport, owner, repo, current)
    scoped = scope_alerts(alerts, sarif_index, frozenset(heads), changed_files)
    return {
        "outcome": "CURRENT",
        "analyzed_head_sha": head_sha,
        "analysis_ids": sorted(a["id"] for a in current),
        "status_line": _current_status_line(scoped),
        **scoped,
    }


def _current_status_line(scoped: dict[str, Any]) -> str:
    attached = len(scoped["alerts"]) + scoped["attached_omitted"]
    return (
        f"CodeQL: CURRENT ({attached} alert(s) in diff files, "
        f"{scoped['other_total']} elsewhere, "
        f"{scoped['counts']['invalid_rule_id']} dropped for rule id)"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

_HELP_EPILOG = """\
examples:
  %(prog)s --pull-request 123 --head-sha 0123456789abcdef0123456789abcdef01234567 --tree-state clean --changed-file src/app.py
  %(prog)s --pull-request 123 --head-sha 0123456789abcdef0123456789abcdef01234567 --tree-state clean --changed-files-from changed.txt

exit codes:
  0  outcome CURRENT, STALE, or NOT ANALYZED (read Data.outcome)
  2  usage or configuration error
  3  outcome SKIPPED: request failed, paging incomplete, or response unusable
  4  outcome SKIPPED: authorization or not-found refusal, or gh not authenticated

Data.outcome is one of CURRENT, STALE, NOT ANALYZED, SKIPPED. Only CURRENT carries
alerts, each as rule_id, path, line. Anything but CURRENT is never a clean result.
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read a pull request's CodeQL code-scanning alerts (GET only, every page) "
            "and report CURRENT, STALE, NOT ANALYZED, or SKIPPED."
        ),
        epilog=_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--owner", default="", help="Repository owner (default: from git remote)")
    parser.add_argument("--repo", default="", help="Repository name (default: from git remote)")
    parser.add_argument("--pull-request", type=int, required=True, help="Pull request number")
    parser.add_argument(
        "--head-sha",
        required=True,
        help="Reviewed HEAD, 40 lower-case hex characters (git rev-parse HEAD)",
    )
    parser.add_argument(
        "--tree-state",
        choices=("clean", "dirty"),
        default="dirty",
        help="Working tree state. Anything but 'clean' makes the result STALE (default: dirty)",
    )
    parser.add_argument(
        "--changed-file",
        action="append",
        default=[],
        metavar="PATH",
        help="Repo-relative file the diff touches. Repeat per file",
    )
    parser.add_argument(
        "--changed-files-from",
        metavar="FILE",
        help="File with one changed path per line, or '-' for stdin",
    )
    add_output_format_arg(parser)
    return parser


def _usage_error(message: str, output_format: str) -> NoReturn:
    write_skill_error(
        message,
        EXIT_USAGE,
        error_type="InvalidParams",
        output_format=output_format,
        script_name=_SCRIPT_NAME,
    )
    raise SystemExit(EXIT_USAGE)


def _collect_changed_files(args: argparse.Namespace) -> frozenset[str]:
    paths = list(args.changed_file)
    source = args.changed_files_from
    if source == "-" and sys.stdin.isatty():
        _usage_error(
            "--changed-files-from - needs piped input; stdin is a terminal", args.output_format
        )
    if source is not None:
        try:
            text = sys.stdin.read() if source == "-" else _read_text(source)
        except (OSError, UnicodeDecodeError) as exc:
            detail = exc.strerror if isinstance(exc, OSError) else "not valid UTF-8"
            _usage_error(f"cannot read --changed-files-from: {detail}", args.output_format)
        paths.extend(text.splitlines())
    return normalize_changed_files(paths)


def _read_text(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _emit_skipped(skip: SkipError, args: argparse.Namespace) -> int:
    write_skill_error(
        f"CodeQL: SKIPPED ({skip.reason})",
        skip.exit_code,
        error_type="AuthError" if skip.exit_code == EXIT_AUTH else "ApiError",
        output_format=args.output_format,
        script_name=_SCRIPT_NAME,
        extra={
            "outcome": "SKIPPED",
            "reason": skip.reason,
            "status_line": f"CodeQL: SKIPPED ({skip.reason})",
            "pull_request": args.pull_request,
        },
    )
    return skip.exit_code


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.pull_request < 1:
        _usage_error("--pull-request must be a positive integer", args.output_format)
    if _FULL_SHA.fullmatch(args.head_sha) is None:
        _usage_error("--head-sha must be 40 lower-case hex characters", args.output_format)
    changed_files = _collect_changed_files(args)
    try:
        assert_gh_authenticated(rest_only=True)
        repo_info = resolve_repo_params(args.owner, args.repo)
    except SystemExit as exc:
        # Both helpers print the cause on stderr and exit. Keep that text, and
        # still emit the one JSON outcome the caller parses.
        code = exc.code if exc.code in (EXIT_USAGE, EXIT_EXTERNAL, EXIT_AUTH) else EXIT_AUTH
        return _emit_skipped(SkipError("gh is not ready for this repository", int(code)), args)
    try:
        data = read_outcome(
            gh_get,
            owner=repo_info.owner,
            repo=repo_info.repo,
            pull_request=args.pull_request,
            head_sha=args.head_sha,
            tree_clean=args.tree_state == "clean",
            changed_files=changed_files,
        )
    except SkipError as skip:
        return _emit_skipped(skip, args)
    data["pull_request"] = args.pull_request
    write_skill_output(
        data,
        output_format=args.output_format,
        human_summary=data["status_line"],
        status="PASS" if data["outcome"] == "CURRENT" else "WARNING",
        script_name=_SCRIPT_NAME,
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

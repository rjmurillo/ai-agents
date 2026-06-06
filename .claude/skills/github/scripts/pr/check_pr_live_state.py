#!/usr/bin/env python3
"""Per-PR live-state re-triage probe (issue #2455).

The pr-autofix workflow triages all open PRs once at session start
(`docs/autonomous-pr-monitor.md`), then walks the queue acting on each
one in turn. In a repo with heavy merge automation, the queue can stale
in two distinct ways while the walk is in progress:

1. **Live state drift.** A PR that was OPEN at session start has been
   merged or closed by mid-run automation (a sibling agent, a bot,
   `set_pr_auto_merge` firing). Acting on it now wastes work, risks
   pushing redundant commits to a closed branch, and surfaces as
   confusing log noise.
2. **Superseded by main.** The PR's diff has already landed on main
   (typically via a consolidated PR that covered the same fix). Every
   commit on the PR branch has a patch-id match on origin/main, so a
   merge would be a no-op at best or a conflicting duplicate at worst.

This script is the pre-action gate that pr-autofix MUST call immediately
before acting on each PR. It returns a single verdict:

    {"action": "ACT" | "SKIP", "reason": "...", ...}

Exit codes follow ADR-035:
    0 - PR is safe to act on (still OPEN; not superseded by main)
    1 - PR should be skipped/closed (merged, closed, or superseded by main)
    2 - PR not found
    3 - External error (API failure)
    4 - Auth error

Stricter/looser/different than canonical
========================================
This script is **purely advisory** with respect to the four-condition
Ready-to-Merge gate (`docs/autonomous-pr-monitor.md` Ready-to-Merge
Definition; `.claude/commands/pr-autofix.md` Ready-to-Merge Definition).
An action="ACT" verdict means "the PR is still actionable", NOT "merge
this PR". The caller still runs `test_pr_merge_ready.py` and the
4-condition cross-check before any merge.

A SKIP verdict, on the other hand, is binding: the caller MUST NOT push
commits or enable auto-merge on a PR this script classifies as SKIP.
That is the protection issue #2455 buys.

Evidence: pr-autofix session 2026-06-05 deep-worked PRs #2409/#2412 that
were already superseded by the consolidated PR #2394 on main; #2409 was
auto-merge-armed before the redundancy was caught.
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import time

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Plugin-root resolution: matches sibling scripts (test_pr_merged.py,
# test_pr_merge_ready.py). When the script runs inside a deployed Claude
# plugin, CLAUDE_PLUGIN_ROOT points at the plugin's installed path; when
# it runs inside the repo (the case under test), we walk up to .claude/lib.
# ---------------------------------------------------------------------------
_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
_workspace = os.environ.get("GITHUB_WORKSPACE")
if _plugin_root:
    _lib_dir = os.path.join(_plugin_root, "lib")
elif _workspace:
    _lib_dir = os.path.join(_workspace, ".claude", "lib")
else:
    _lib_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "lib")
    )
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
    sys.exit(2)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (  # noqa: E402
    RepoInfo,  # re-exported so tests can reach it via _mod.RepoInfo
    assert_gh_authenticated,
    gh_graphql,
    resolve_repo_params,
    safe_log_str,
)
from github_core.output import (  # noqa: E402
    add_output_format_arg,
    write_skill_error,
    write_skill_output,
)

_SCRIPT_NAME = "check_pr_live_state.py"


def _git_locale_env() -> dict[str, str]:
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    return env


def _emit_error(
    message: str,
    code: int,
    error_type: str,
    output_format: str,
    pr_number: int,
    owner: str,
    repo: str,
) -> None:
    write_skill_error(
        message,
        code,
        error_type=error_type,
        output_format=output_format,
        script_name=_SCRIPT_NAME,
        extra={"pull_request": pr_number, "owner": owner, "repo": repo},
    )
    raise SystemExit(code)


__all__ = [
    "RepoInfo",
    "build_parser",
    "classify_live_state",
    "is_superseded_by_base",
    "main",
    "parse_git_cherry",
]

# ---------------------------------------------------------------------------
# GraphQL: minimum live-state shape needed to classify
# ---------------------------------------------------------------------------

_LIVE_STATE_QUERY = """\
query($owner: String!, $repo: String!, $number: Int!) {
    repository(owner: $owner, name: $repo) {
        pullRequest(number: $number) {
            number
            state
            merged
            isDraft
            closed
            headRefName
            baseRefName
        }
    }
}"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def parse_git_cherry(stdout: str) -> dict:
    """Parse `git cherry` output into a supersession verdict.

    `git cherry <base> <head>` prints one line per commit on <head> that
    is NOT on <base>, prefixed by:
      - ``+ <sha>``  the commit has no patch-id match on base (real new work)
      - ``- <sha>``  the commit's patch-id IS on base (superseded)

    A PR is "fully superseded by base" only when every line is ``- ``;
    a partial supersession (some ``-``, some ``+``) is reported but does
    not auto-skip, because the remaining commits may be real changes.

    Whitespace tolerant. Malformed lines (no prefix) are silently dropped
    so a stray blank line or stderr leak does not poison the count.
    """
    superseded = 0
    new_commits = 0
    for raw in stdout.splitlines():
        line = raw.strip()
        if not line:
            continue
        # Accept either '+ <sha>' or '- <sha>' as the canonical shape.
        # Drop anything else (defensive: stderr can leak into stdout
        # under some shell pipelines).
        if line.startswith("+ "):
            new_commits += 1
        elif line.startswith("- "):
            superseded += 1
        else:
            continue
    total = superseded + new_commits
    return {
        "pr_commits": total,
        "superseded_commits": superseded,
        "fully_superseded": total > 0 and superseded == total,
    }


def is_superseded_by_base(
    base_branch: str,
    head_ref: str,
    skip_fetch: bool = False,
) -> dict:
    """Run `git cherry` against the base branch and return the verdict.

    When skip_fetch=False (default), runs `git fetch origin <base>` first
    to ensure origin/<base> reflects the live tip. The pr-autofix walk
    can pass --skip-fetch on the per-PR call after running one outer
    fetch to keep the loop cheap.

    The cherry call uses ``origin/<base>`` as the reference so a stale
    or missing local <base> in the worktree cannot produce a false
    "no supersession" result.

    On any subprocess failure the result reports ``fully_superseded=False``
    plus ``git_cherry_failed=True`` so the caller treats the probe as
    inconclusive instead of as a positive signal. (Failing closed on
    SKIP would block valid PRs; failing open on ACT is the correct
    fallback because supersession is an optimization, not a safety
    requirement.)
    """
    if not skip_fetch:
        try:
            subprocess.run(
                ["git", "fetch", "--quiet", "origin", base_branch],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                env=_git_locale_env(),
                timeout=60,
                check=False,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            logger.warning(
                "op=live_state_fetch_failed base=%s err=%s",
                base_branch, safe_log_str(str(exc)),
            )
            # Continue: cherry against whatever origin/<base> we have.

    cherry_cmd = [
        "git", "cherry", "-v",
        f"origin/{base_branch}",
        head_ref,
    ]
    try:
        result = subprocess.run(
            cherry_cmd,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            env=_git_locale_env(),
            timeout=60,
            check=False,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        logger.warning(
            "op=live_state_cherry_failed base=%s head=%s err=%s",
            base_branch, head_ref, safe_log_str(str(exc)),
        )
        return {
            "pr_commits": 0,
            "superseded_commits": 0,
            "fully_superseded": False,
            "git_cherry_failed": True,
        }

    if result.returncode != 0:
        logger.warning(
            "op=live_state_cherry_nonzero rc=%d base=%s head=%s stderr=%s",
            result.returncode, base_branch, head_ref,
            safe_log_str((result.stderr or "")[:200]),
        )
        return {
            "pr_commits": 0,
            "superseded_commits": 0,
            "fully_superseded": False,
            "git_cherry_failed": True,
        }

    verdict = parse_git_cherry(result.stdout or "")
    verdict["git_cherry_failed"] = False
    return verdict


def classify_live_state(pr: dict, supersession: dict | None) -> dict:
    """Combine GitHub state + supersession into a single ACT/SKIP verdict.

    SKIP conditions (binding for the caller):
      - merged=True or state == "MERGED": already landed; nothing to do.
      - closed=True or state == "CLOSED": author or automation closed it.
      - isDraft=True: drafts are not actionable in pr-autofix (the
        triage protocol classifies them as non-mergeable; acting on
        them risks pushing to a workspace the author still owns).
      - fully_superseded=True: every commit on the branch is already on
        the base via patch-id. Merging is a no-op or a conflict.

    ACT verdict carries an informational ``reason`` for the log:
      - "still open" for the clean case.
      - "partially superseded (N/M)" when some commits match base but
        others are real new work; the caller may want to surface this
        to the human reviewer but it does NOT block the action.
    """
    if pr.get("merged") is True or pr.get("state") == "MERGED":
        return {"action": "SKIP", "reason": "PR is already merged"}
    if pr.get("closed") is True or pr.get("state") == "CLOSED":
        return {"action": "SKIP", "reason": "PR is closed (not merged)"}
    if pr.get("isDraft") is True:
        return {"action": "SKIP", "reason": "PR is in draft state"}

    if supersession and supersession.get("fully_superseded"):
        n = supersession.get("superseded_commits", 0)
        return {
            "action": "SKIP",
            "reason": (
                f"PR is fully superseded by base: all {n} commit(s) "
                "patch-id match origin/<base>; recommend close"
            ),
        }
    if supersession and supersession.get("superseded_commits", 0) > 0:
        n = supersession.get("superseded_commits", 0)
        m = supersession.get("pr_commits", 0)
        return {
            "action": "ACT",
            "reason": (
                f"PR is partially superseded ({n}/{m} commits already on "
                "base); proceed with caution"
            ),
        }
    return {"action": "ACT", "reason": "PR is still open and actionable"}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Per-PR live-state probe for pr-autofix. Re-queries PR state "
            "and detects supersession-by-base immediately before acting."
        ),
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--pull-request", type=int, required=True, help="Pull request number",
    )
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help=(
            "Do NOT run `git fetch origin <base>` before `git cherry`. "
            "Set this when pr-autofix has already run one outer fetch for "
            "the whole walk so each per-PR call avoids a redundant network "
            "round-trip. Default: fetch."
        ),
    )
    add_output_format_arg(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_format = args.output_format
    assert_gh_authenticated()

    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo

    op_start = time.monotonic()
    try:
        data = gh_graphql(
            _LIVE_STATE_QUERY,
            {"owner": owner, "repo": repo, "number": args.pull_request},
        )
    except RuntimeError as exc:
        msg = str(exc)
        duration_ms = int((time.monotonic() - op_start) * 1000)
        if "Could not resolve" in msg:
            logger.warning(
                "op=live_state_failed pr=%d owner=%s repo=%s "
                "reason=pr_not_found duration_ms=%d",
                args.pull_request, owner, repo, duration_ms,
            )
            _emit_error(
                f"PR #{args.pull_request} not found in {owner}/{repo}",
                2,
                "NotFound",
                output_format,
                args.pull_request,
                owner,
                repo,
            )
        logger.warning(
            "op=live_state_failed pr=%d owner=%s repo=%s "
            "reason=graphql_error duration_ms=%d error=%s",
            args.pull_request, owner, repo, duration_ms, safe_log_str(msg),
        )
        _emit_error(
            f"Failed to query PR live state: {msg}",
            3,
            "ApiError",
            output_format,
            args.pull_request,
            owner,
            repo,
        )

    pr = (data.get("repository") or {}).get("pullRequest")
    if pr is None:
        duration_ms = int((time.monotonic() - op_start) * 1000)
        logger.warning(
            "op=live_state_failed pr=%d owner=%s repo=%s "
            "reason=pr_not_found duration_ms=%d",
            args.pull_request, owner, repo, duration_ms,
        )
        _emit_error(
            f"PR #{args.pull_request} not found in {owner}/{repo}",
            2,
            "NotFound",
            output_format,
            args.pull_request,
            owner,
            repo,
        )

    # Only run the supersession probe when the PR is still OPEN; for a
    # MERGED/CLOSED/DRAFT PR the verdict is already settled and the git
    # call would just burn a fetch + subprocess for no gain.
    supersession: dict | None = None
    pr_open = (
        pr.get("state") == "OPEN"
        and pr.get("merged") is not True
        and pr.get("closed") is not True
        and pr.get("isDraft") is not True
    )
    if pr_open:
        supersession = is_superseded_by_base(
            base_branch=pr.get("baseRefName", "main"),
            head_ref=f"origin/{pr.get('headRefName', '')}",
            skip_fetch=args.skip_fetch,
        )

    verdict = classify_live_state(pr, supersession)

    output = {
        "success": True,
        "pull_request": args.pull_request,
        "owner": owner,
        "repo": repo,
        "state": pr.get("state"),
        "merged": pr.get("merged") is True,
        "is_draft": pr.get("isDraft") is True,
        "closed": pr.get("closed") is True,
        "head_ref": pr.get("headRefName"),
        "base_ref": pr.get("baseRefName"),
        "superseded_by_base": supersession or {
            "pr_commits": 0,
            "superseded_commits": 0,
            "fully_superseded": False,
        },
        "action": verdict["action"],
        "reason": verdict["reason"],
    }

    duration_ms = int((time.monotonic() - op_start) * 1000)
    logger.info(
        "op=live_state pr=%d owner=%s repo=%s state=%s action=%s "
        "fully_superseded=%s duration_ms=%d",
        args.pull_request, owner, repo, pr.get("state"), verdict["action"],
        (supersession or {}).get("fully_superseded"), duration_ms,
    )

    write_skill_output(
        output,
        output_format=output_format,
        human_summary=(
            f"PR #{args.pull_request} live-state: "
            f"{verdict['action']} ({verdict['reason']})"
        ),
        status="PASS" if verdict["action"] == "ACT" else "WARNING",
        script_name=_SCRIPT_NAME,
    )

    return 0 if verdict["action"] == "ACT" else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# taste-lint: ignore file-size, CLI script keeps merge orchestration and output contract together.
# taste-lint: ignore complexity, CLI script keeps merge orchestration and output contract together.
"""Merge a GitHub Pull Request.

Merges a PR using the specified strategy. Supports auto-merge
for PRs with pending checks.

When --strategy is omitted, the script consults the repository's
allowed merge methods and picks a default that satisfies repo policy
(squash preferred, then merge, then rebase). This avoids the
issue #2449 failure mode where a hard-coded 'merge' default
violated repos that disallow merge commits (e.g. rjmurillo/ai-agents
allows squash only).

All output goes through the standard skill envelope per ADR-056,
including error paths. Disallowed strategy, not-found PR, conflicts,
and other failures emit a JSON envelope on stdout (instead of plain
text on stderr), so consumers can pipe to json.loads without crashing.

Action boundaries (issue #5767, REQ-043): every merge is pinned to the
reviewed head SHA with ``--match-head-commit`` (``--expected-head-sha``
overrides the SHA read from the PR and fails closed on a mismatch). After
every merge attempt the script reads the PR back and reports what GitHub
says, never what the merge command implied: MERGED is success, an OPEN PR
with an auto-merge request is "queued, NOT merged yet", anything else is
exit 3. A failed or timed-out merge command that the readback shows MERGED
is reported as success with ``recovered: true``. Every envelope carries an
``audit`` record (actor, target, action, approval, result, rollback,
residual risk).

Stacked PRs (issue #5473): GraphQL and the synchronous REST merge both refuse
a PR that is part of a stack. The script then gates every unmerged downstack
member with test_pr_merge_ready.py, because merge-async lands the whole stack
up to the requested PR, and gates the requested PR itself, since merge-async
runs no branch protection. It pins each downstack head SHA at the gate, re-reads
the stack before the request, and re-checks the pins after the merge: a push
that landed unreviewed reports exit 3 instead of success. It then calls
``PUT pulls/{n}/merge-async`` pinned to the head SHA and polls the returned UUID
to a terminal status. ``--auto`` never takes this path.

Exit codes follow ADR-035:
    0 - Success
    1 - Invalid parameters / logic error
    2 - Not found
    3 - External error (API failure)
    4 - Auth error
    100 - Not mergeable (script-specific; ADR-035 reserves 5-99)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any, NoReturn

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
    sanitize_failure_detail,
)
from github_core.not_found import is_pr_not_found
from github_core.output import (
    add_output_format_arg,
    write_skill_error,
    write_skill_output,
)
from github_core.placeholder_identity import filter_coauthor_trailers

_SCRIPT_NAME = "merge_pr.py"
# Script-specific exit code per ADR-035 (100+), documented in the header above.
_EXIT_NOT_MERGEABLE = 100
# gh reports a missing repository as "Could not resolve to a Repository".
# A wrong repository never resolves on retry, so it is a config error (ADR-035).
_REPO_NOT_FOUND_MARKER = "could not resolve to a repository"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Merge a GitHub Pull Request.")
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--pull-request",
        type=int,
        required=True,
        help="Pull request number",
    )
    parser.add_argument(
        "--strategy",
        choices=["merge", "squash", "rebase"],
        default=None,
        help=("Merge strategy. Omit to auto-pick from repo policy (squash > merge > rebase)."),
    )
    parser.add_argument(
        "--delete-branch",
        action="store_true",
        help="Delete the head branch after merge",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Enable auto-merge (merge when checks pass)",
    )
    parser.add_argument(
        "--expected-head-sha",
        default="",
        help=(
            "Reviewed head commit SHA (40 hex). Refuses to merge when the PR "
            "head differs, and pins the merge to this commit."
        ),
    )
    parser.add_argument("--subject", default="", help="Custom commit subject")
    parser.add_argument("--body", default="", help="Custom commit body")
    add_output_format_arg(parser)
    return parser


_STRATEGY_TO_REPO_FIELD = {
    "merge": "allow_merge_commit",
    "squash": "allow_squash_merge",
    "rebase": "allow_rebase_merge",
}

# Order matters: prefer squash (cleanest history), then merge, then rebase.
_STRATEGY_PREFERENCE = ("squash", "merge", "rebase")

_BLOCKED_KEYWORDS = ("BLOCKED", "branch protection", "required status check")

# Issue #5473: GraphQL refuses outright for a PR GitHub considers part of a
# stack. Retargeting the child to break the stack is refused too. The
# synchronous REST merge (_rest_merge) answers 403 for a stack, so the only
# working path is the asynchronous endpoint (_merge_stack_async).
_STACK_KEYWORDS = ("part of a stack", "asynchronous merge REST API")

# merge-async lives only in this REST API version. The 409 body returns the
# UUID of the request already in flight.
_ASYNC_API_VERSION = "2026-03-10"
_ASYNC_POLL_INTERVAL_SECONDS = 2.0
_ASYNC_POLL_TIMEOUT_SECONDS = 120.0
# Consecutive failed status polls tolerated before the outcome is called unknown.
_ASYNC_POLL_MAX_ERRORS = 3
_API_CALL_TIMEOUT_SECONDS = 30
_READINESS_TIMEOUT_SECONDS = 180
_READINESS_SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "test_pr_merge_ready.py"
)

# Issue #5767: GitHub refuses a pinned merge when the head moved after review.
# gh and the REST endpoint both say "Head branch was modified". Matched
# case-insensitively against gh output.
_HEAD_MOVED_KEYWORDS = ("head branch was modified", "head commit")

_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")

_MERGE_TIMEOUT_SECONDS = 60

_READBACK_FIELDS = "state,mergeCommit,mergedBy,autoMergeRequest,headRefOid"

_APPROVAL = "repository branch protection (server-enforced)"

# merge-async runs no branch protection at request time (issue #5473), so the
# approval on that path is this script's own readiness gate, not GitHub's.
_APPROVAL_ASYNC = (
    "script readiness gate (test_pr_merge_ready.py) on the target and each unmerged "
    "downstack PR at pinned heads; merge-async evaluates no branch protection"
)

_RESIDUAL_RISK = (
    "deny rules match command text only; branch protection is the enforcement (ADR-112)"
)


class _MergeFailureError(Exception):
    """A merge attempt failed in a way the readback must adjudicate."""

    def __init__(
        self,
        message: str,
        code: int,
        error_type: str,
        *,
        landed: bool = False,
        approval: str = _APPROVAL,
        stack: int | None = None,
        pins: dict[int, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.error_type = error_type
        # Who approved the merge this failure belongs to: branch protection for
        # the GraphQL and REST paths, the script's readiness gate for merge-async.
        self.approval = approval
        # Set when the failure came out of the merge-async path after the gate
        # pinned the downstack heads. A readback that then shows MERGED must
        # re-check those pins before it reports a recovered success.
        self.stack = stack
        self.pins = pins
        # True when the merge landed but a post-merge check found a problem; the
        # readback must then report the failure instead of recovering to success.
        self.landed = landed


@dataclass(frozen=True)
class _StackMember:
    """One validated entry of a stack listing."""

    number: int
    state: str
    head_sha: str
    merged: bool = False


@dataclass(frozen=True)
class _MergeContext:
    """Immutable facts about one merge attempt, shared by the helpers."""

    pr: int
    repo_flag: str
    head_sha: str
    strategy: str
    delete_branch: bool
    auto: bool
    output_format: str


def get_allowed_merge_methods(repo_flag: str) -> dict[str, bool]:
    """Query repository settings for allowed merge methods.

    Returns repository allow_* fields mapped to booleans.
    """
    result = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{repo_flag}",
            "--jq",
            "{allow_merge_commit, allow_squash_merge, allow_rebase_merge}",
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to query repository settings: {result.stderr.strip()}")

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to decode JSON from GitHub API response: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("GitHub repository settings response must be an object")
    return {field: bool(data.get(field, False)) for field in _STRATEGY_TO_REPO_FIELD.values()}


def resolve_default_strategy(repo_settings: dict[str, bool]) -> str | None:
    """Pick a sensible default strategy from the repo's allowed methods.

    Returns the first preferred strategy that is allowed by the repo:
    squash > merge > rebase. Returns None if no strategy is allowed
    (caller should error with code 1).
    """
    for strategy in _STRATEGY_PREFERENCE:
        field = _STRATEGY_TO_REPO_FIELD[strategy]
        if repo_settings.get(field, False):
            return strategy
    return None


def validate_strategy(
    strategy: str,
    repo_settings: dict[str, bool] | None,
    repo_flag: str,
    output_format: str,
) -> None:
    """Emit a JSON envelope and exit 1 when the strategy is disallowed.

    Regression guard for issue #2449: before this change, validation
    called error_and_exit which wrote plain text to stderr and produced
    no stdout, breaking consumers that piped to json.loads.

    When repo_settings is None, the caller supplied an explicit strategy and
    skipped REST settings discovery. GitHub rejects a disallowed method at
    merge time, and _handle_merge_failure surfaces a structured error.
    """
    if repo_settings is None:
        return
    field = _STRATEGY_TO_REPO_FIELD.get(strategy)
    if field and repo_settings.get(field, False):
        return

    allowed = [
        name for name, fld in _STRATEGY_TO_REPO_FIELD.items() if repo_settings.get(fld, False)
    ]
    hint = f" Allowed: {', '.join(allowed)}." if allowed else ""
    write_skill_error(
        f"Strategy '{strategy}' is not allowed by {repo_flag}.{hint}",
        1,
        error_type="InvalidParams",
        output_format=output_format,
        script_name=_SCRIPT_NAME,
        extra={
            "pull_request": None,
            "strategy_requested": strategy,
            "allowed_strategies": allowed,
        },
    )
    raise SystemExit(1)


def _emit_error(
    message: str,
    code: int,
    error_type: str,
    output_format: str,
    pr: int,
    audit: dict[str, Any] | None = None,
) -> NoReturn:
    """Helper: emit envelope, then exit with the code.

    Annotated NoReturn because the body always raises SystemExit. Declaring
    None made callers look like they fall through, so a narrowed value stayed
    optional past the call (issue #5473).
    """
    write_skill_error(
        message,
        code,
        error_type=error_type,
        output_format=output_format,
        script_name=_SCRIPT_NAME,
        extra={"pull_request": pr, **({"audit": audit} if audit else {})},
    )
    raise SystemExit(code)


def _is_repo_not_found(gh_output: str) -> bool:
    """Return True when failed gh output says the repository does not exist."""
    return _REPO_NOT_FOUND_MARKER in gh_output.lower()


def _fetch_pr_state(
    pr: int,
    repo_flag: str,
    output_format: str,
) -> dict[str, Any]:
    """Fetch the PR state via gh; emit envelope and exit on failure."""
    pr_result = subprocess.run(
        [
            "gh",
            "pr",
            "view",
            str(pr),
            "--repo",
            repo_flag,
            "--json",
            "state,mergeable,mergeStateStatus,headRefName,headRefOid",
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if pr_result.returncode != 0:
        output = pr_result.stderr or pr_result.stdout
        combined = f"{pr_result.stdout}\n{pr_result.stderr}"
        if _is_repo_not_found(combined):
            _emit_error(
                f"Repository {repo_flag} not found: {sanitize_failure_detail(combined)}",
                2,
                "NotFound",
                output_format,
                pr,
            )
        if is_pr_not_found(combined):
            # Keep gh's words: a 404 from a wrong host or repo also lands here.
            _emit_error(
                f"PR #{pr} not found in {repo_flag}: {sanitize_failure_detail(combined)}",
                2,
                "NotFound",
                output_format,
                pr,
            )
        _emit_error(
            f"Failed to get PR state: {sanitize_failure_detail(output)}",
            3,
            "ApiError",
            output_format,
            pr,
        )

    try:
        data = json.loads(pr_result.stdout)
    except json.JSONDecodeError:
        _emit_error(
            f"PR #{pr} state response was not valid JSON",
            3,
            "ApiError",
            output_format,
            pr,
        )
    if not isinstance(data, dict):
        _emit_error(
            f"PR #{pr} response was not a JSON object",
            3,
            "ApiError",
            output_format,
            pr,
        )
    return {str(key): value for key, value in data.items()}


def _reject_unknown_merge_state(
    pr_data: dict[str, Any],
    pr: int,
    output_format: str,
) -> None:
    """Reject a direct merge while GitHub is still calculating mergeability.

    Issue #2637: after a base update, GitHub reports mergeable=UNKNOWN and
    mergeStateStatus=UNKNOWN while it recalculates. The completion gate
    (.claude/skills/github/scripts/pr/test_pr_merge_ready.py) rejects this
    state with the reason "Merge status is being calculated" (its
    ``_evaluate_pr_state`` appends that reason for ``mergeable == "UNKNOWN"``),
    so a direct merge must reject it too instead of merging a PR its own gate
    just refused. Exit code 3 (ADR-035 external/transient): the caller can
    retry once GitHub settles. Callers that want auto-merge pass --auto, which
    skips this check and hands the decision to GitHub's own gate.
    """
    mergeable = pr_data.get("mergeable") or ""
    merge_state = pr_data.get("mergeStateStatus") or ""
    if mergeable != "UNKNOWN" and merge_state != "UNKNOWN":
        return
    _emit_error(
        f"PR #{pr} merge status is being calculated by GitHub "
        f"(mergeable={mergeable or 'UNKNOWN'}, "
        f"mergeStateStatus={merge_state or 'UNKNOWN'}). "
        "Retry once it settles, or use --auto to defer to GitHub's gate.",
        3,
        "ApiError",
        output_format,
        pr,
    )


def _build_merge_args(
    args: argparse.Namespace,
    pr: int,
    repo_flag: str,
    head_sha: str = "",
) -> list[str]:
    """Assemble the gh pr merge argv from parsed args.

    A non-empty head_sha adds ``--match-head-commit`` so GitHub refuses the
    merge when the head moved after review (issue #5767).
    """
    merge_args = [
        "gh",
        "pr",
        "merge",
        str(pr),
        "--repo",
        repo_flag,
        f"--{args.strategy}",
    ]
    if head_sha:
        merge_args.extend(["--match-head-commit", head_sha])
    if args.delete_branch:
        merge_args.append("--delete-branch")
    if args.auto:
        merge_args.append("--auto")
    if args.subject:
        merge_args.extend(["--subject", args.subject])
    if args.body:
        # Issue #2466: strip any placeholder Co-authored-by trailers before
        # passing the body to gh. The worktree-bootstrap reset (worktree_identity.py)
        # and pre-push guard (check_placeholder_identity.py) are the primary
        # defences; this sanitizer is a final backstop for the --body path.
        # When --body is empty, gh auto-assembles the squash message from commit
        # subjects; those commits are protected by the pre-push guard and the
        # worktree-bootstrap reset instead.
        sanitized_body = filter_coauthor_trailers(args.body)
        merge_args.extend(["--body", sanitized_body])
    return merge_args


def _rest_merge(
    pr: int,
    repo_flag: str,
    strategy: str,
    head_sha: str,
    subject: str,
    body: str,
) -> subprocess.CompletedProcess[str]:
    """Attempt a merge via the REST PUT endpoint.

    Issue #4362: the GraphQL ``mergePullRequest`` mutation used by ``gh pr
    merge`` can return "the base branch policy prohibits the merge" for PRs
    whose required checks are all SUCCESS and whose unresolved thread count
    is 0.  The REST endpoint enforces the same branch rules but accepts the
    same head SHA seconds later.  A single REST retry after a BLOCKED
    failure lets the authoritative server adjudicate instead of surfacing a
    GraphQL-specific refusal as a client-side error.
    """
    cmd = [
        "gh",
        "api",
        "-X",
        "PUT",
        f"repos/{repo_flag}/pulls/{pr}/merge",
        "-f",
        f"merge_method={strategy}",
        "-f",
        f"sha={head_sha}",
    ]
    if subject:
        cmd += ["-f", f"commit_title={subject}"]
    if body:
        cmd += ["-f", f"commit_message={body}"]
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=_MERGE_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        # Issue #5767: the PUT may have landed; the readback decides.
        raise _MergeFailureError(
            f"REST merge for PR #{pr} timed out after {_MERGE_TIMEOUT_SECONDS}s "
            f"({exc}); outcome unknown",
            3,
            "Timeout",
        ) from exc


def _pr_is_merged(pr: int, repo_flag: str) -> bool:
    """Return True when GitHub reports the PR as merged.

    A REST merge can return success without ``merged: true`` in the body.
    Treating a missing flag as failure would report a completed merge as an
    error, so ask GitHub for the PR's state instead of inferring it.  Any query
    failure returns False so an unverified merge is never reported as a success.
    """
    try:
        result = subprocess.run(
            ["gh", "pr", "view", str(pr), "--repo", repo_flag, "--json", "state"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False
    if result.returncode != 0:
        return False
    try:
        return bool(json.loads(result.stdout).get("state") == "MERGED")
    except (json.JSONDecodeError, AttributeError):
        return False


def _api_get_json(endpoint: str, what: str) -> dict[str, Any]:
    """GET a REST endpoint at the merge-async API version; return the JSON object.

    Any failure raises _MergeFailureError so the caller fails closed: an
    unreadable stack is never treated as an empty one.
    """
    cmd = ["gh", "api", "-H", f"X-GitHub-Api-Version: {_ASYNC_API_VERSION}", endpoint]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=_API_CALL_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise _MergeFailureError(f"{what} timed out ({exc})", 3, "Timeout") from exc
    if result.returncode != 0:
        detail = sanitize_failure_detail(result.stderr or result.stdout)
        raise _MergeFailureError(f"{what} failed: {detail}", 3, "ApiError")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise _MergeFailureError(f"{what} returned invalid JSON", 3, "ApiError") from exc
    if not isinstance(data, dict):
        raise _MergeFailureError(f"{what} did not return a JSON object", 3, "ApiError")
    return data


def _stack_number(pr: int, repo_flag: str) -> int:
    """Return the stack number GitHub reports for ``pr``; raise when it reports none."""
    pr_data = _api_get_json(f"repos/{repo_flag}/pulls/{pr}", f"PR #{pr} lookup")
    stack = pr_data.get("stack")
    number = stack.get("number") if isinstance(stack, dict) else None
    if not isinstance(number, int) or isinstance(number, bool):
        raise _MergeFailureError(
            f"PR #{pr} was refused as part of a stack but GitHub reports no stack "
            "for it; the members a merge would land are unknown, no merge attempted",
            _EXIT_NOT_MERGEABLE,
            "General",
        )
    return number


def _unreadable_member(stack: int, index: int, problem: str) -> _MergeFailureError:
    """Build the fail-closed error for a stack member the script cannot interpret."""
    return _MergeFailureError(
        f"stack #{stack} member {index} has {problem}; the members a merge would "
        "land are unknown, no merge attempted",
        _EXIT_NOT_MERGEABLE,
        "General",
    )


def _parse_member(stack: int, index: int, raw: Any) -> _StackMember:
    """Validate one stack listing entry strictly; anything unexpected raises."""
    if not isinstance(raw, dict):
        raise _unreadable_member(stack, index, "an entry that is not an object")
    number = raw.get("number")
    if not isinstance(number, int) or isinstance(number, bool):
        raise _unreadable_member(stack, index, f"a missing or non-integer number ({number!r})")
    state = raw.get("state")
    if not isinstance(state, str):
        raise _unreadable_member(stack, index, f"a missing or non-string state ({state!r})")
    head = raw.get("head")
    sha = head.get("sha") if isinstance(head, dict) else None
    merged_at = raw.get("merged_at")
    if merged_at is not None and not isinstance(merged_at, str):
        raise _unreadable_member(stack, index, f"a non-string merged_at ({merged_at!r})")
    return _StackMember(number, state, sha if isinstance(sha, str) else "", bool(merged_at))


def _stack_members(stack: int, repo_flag: str) -> list[_StackMember]:
    """Read and validate the full member list of a stack, bottom first."""
    listing = _api_get_json(f"repos/{repo_flag}/stacks/{stack}", f"stack #{stack} lookup")
    raw_members = listing.get("pull_requests")
    if not isinstance(raw_members, list):
        raise _MergeFailureError(
            f"stack #{stack} listing has no member list; the members a merge would "
            "land are unknown, no merge attempted",
            _EXIT_NOT_MERGEABLE,
            "General",
        )
    return [_parse_member(stack, i, raw) for i, raw in enumerate(raw_members)]


def _members_through(members: list[_StackMember], pr: int, stack: int) -> list[_StackMember]:
    """Return the members merge-async would land: everything up to and including ``pr``."""
    numbers = [m.number for m in members]
    if pr not in numbers:
        raise _MergeFailureError(
            f"PR #{pr} is not in the member list of stack #{stack}; the members a "
            "merge would land are unknown, no merge attempted",
            _EXIT_NOT_MERGEABLE,
            "General",
        )
    return members[: numbers.index(pr) + 1]


def _downstack_pins(landing: list[_StackMember], pr: int) -> dict[int, str]:
    """Map each unmerged downstack member to its head SHA.

    Issue #5473: merge-async lands every PR in the stack up to and including the
    requested one. A merged member stays listed with state ``closed`` and a
    ``merged_at``, and only that pair skips the gate. A ``closed`` member with
    no ``merged_at`` was closed without merging: it can neither pass a gate nor
    be pinned, so it raises. Any other state is gated, so an unexpected spelling
    fails closed. An unmerged member with no valid head SHA raises, because
    without a pin a later push to it could not be detected.
    """
    pins: dict[int, str] = {}
    for member in landing:
        if member.number == pr:
            continue
        if member.state == "closed":
            if member.merged:
                continue
            raise _MergeFailureError(
                f"downstack PR #{member.number} is closed without being merged, so what a "
                "merge of the stack would land is unknown; no merge attempted",
                _EXIT_NOT_MERGEABLE,
                "General",
            )
        if not _SHA_PATTERN.match(member.head_sha):
            raise _MergeFailureError(
                f"downstack PR #{member.number} has no readable head SHA in the stack "
                "listing, so its reviewed head cannot be pinned; no merge attempted",
                _EXIT_NOT_MERGEABLE,
                "General",
            )
        pins[member.number] = member.head_sha.lower()
    return pins


def _read_landing(pr: int, repo_flag: str, stack: int) -> list[_StackMember]:
    """Read the stack and return the members a merge of ``pr`` would land."""
    return _members_through(_stack_members(stack, repo_flag), pr, stack)


def _member_not_ready_reason(member: int, repo_flag: str, pinned_head: str) -> str | None:
    """Run the completion gate on one member; return why it failed, or None if ready.

    The gate is told the head it must see. Comparing pinned heads before and
    after the gate cannot catch a head that moved to a second commit during the
    gate and then back, because both reads show the first commit.
    """
    owner, _, repo = repo_flag.partition("/")
    cmd = [
        sys.executable,
        _READINESS_SCRIPT,
        "--owner",
        owner,
        "--repo",
        repo,
        "--pull-request",
        str(member),
        "--expected-head-sha",
        pinned_head,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=_READINESS_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return f"readiness check timed out after {_READINESS_TIMEOUT_SECONDS}s"
    if result.returncode == 0:
        return None
    detail = sanitize_failure_detail(result.stderr or result.stdout)
    if result.returncode == 1:
        return f"not merge-ready: {detail}"
    return f"readiness check could not run (exit {result.returncode}): {detail}"


def _assert_stack_ready(ctx: _MergeContext, stack: int) -> dict[int, str]:
    """Refuse the async merge unless the target and every unmerged downstack PR is ready.

    merge-async runs no branch protection at request time and merges the whole
    stack up to the target. The target itself and any member that never cleared
    a gate would land unreviewed, so anything not provably ready aborts before
    the call. Returns the downstack head SHAs the gate was run against.
    """
    landing = _read_landing(ctx.pr, ctx.repo_flag, stack)
    pins = _downstack_pins(landing, ctx.pr)
    failures = []
    for member, pinned_head in [*pins.items(), (ctx.pr, ctx.head_sha)]:
        reason = _member_not_ready_reason(member, ctx.repo_flag, pinned_head)
        if reason:
            failures.append(f"#{member} ({reason})")
    if failures:
        raise _MergeFailureError(
            f"merging PR #{ctx.pr} would also merge PRs that are not "
            f"merge-ready: {'; '.join(failures)}. No merge attempted.",
            _EXIT_NOT_MERGEABLE,
            "General",
        )
    return pins


def _assert_pins_unchanged(ctx: _MergeContext, stack: int, pins: dict[int, str]) -> None:
    """Re-read the stack just before the PUT and refuse when it drifted from the gate.

    The ``sha`` field pins only the target. A push to a downstack PR after its
    readiness check, or an unmerged member that appeared below the target, would
    land unreviewed, so any difference from the gated set aborts the request.
    """
    current = _downstack_pins(_read_landing(ctx.pr, ctx.repo_flag, stack), ctx.pr)
    drifted = sorted(n for n in pins.keys() | current.keys() if pins.get(n) != current.get(n))
    if drifted:
        listed = ", ".join(f"#{n}" for n in drifted)
        raise _MergeFailureError(
            f"downstack PR {listed} head moved or the stack changed after the readiness "
            f"check; refusing to merge PR #{ctx.pr} on a stale review. No merge attempted.",
            _EXIT_NOT_MERGEABLE,
            "General",
        )


def _assert_heads_landed_as_gated(ctx: _MergeContext, stack: int, pins: dict[int, str]) -> None:
    """After the merge, confirm each gated downstack head still matches its pin.

    A PR that merged keeps its final head SHA in the listing, so a difference
    means commits landed that the readiness check never saw. The merge cannot
    be undone here, so this raises a failure the readback must not recover from.
    """
    try:
        landing = _read_landing(ctx.pr, ctx.repo_flag, stack)
    except _MergeFailureError as failure:
        raise _MergeFailureError(
            f"merge-async merged PR #{ctx.pr} but the post-merge stack check failed, "
            f"so the downstack heads are unverified: {failure.message}",
            3,
            "ApiError",
            landed=True,
            approval=_APPROVAL_ASYNC,
        ) from failure
    heads = {m.number: m.head_sha.lower() for m in landing}
    moved = sorted(n for n, sha in pins.items() if heads.get(n) != sha)
    if moved:
        listed = ", ".join(f"#{n}" for n in moved)
        raise _MergeFailureError(
            f"merge-async merged PR #{ctx.pr} but downstack PR {listed} head differs from "
            "the head that passed the readiness check; unreviewed commits may have landed. "
            "Review the merge commit and revert if needed.",
            3,
            "ApiError",
            landed=True,
            approval=_APPROVAL_ASYNC,
        )


def _parse_json_object(text: str) -> dict[str, Any]:
    """Parse text as a JSON object; anything else yields an empty dict."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _async_uuid(body: dict[str, Any]) -> str:
    """Return the merge request UUID from a merge-async body, or an empty string."""
    details = body.get("details")
    candidate = details.get("uuid") if isinstance(details, dict) else body.get("uuid")
    return candidate if isinstance(candidate, str) else ""


def _request_async_merge(ctx: _MergeContext, subject: str, body: str) -> dict[str, Any]:
    """PUT merge-async pinned to the reviewed head; return the response body.

    The ``sha`` field makes GitHub cancel the merge when the branch moved after
    the readiness check. A 409 means a request is already in flight and its
    UUID comes back in the body, so that body is returned rather than treated as
    a failure and no second request is issued.
    """
    cmd = [
        "gh",
        "api",
        "-X",
        "PUT",
        "-H",
        f"X-GitHub-Api-Version: {_ASYNC_API_VERSION}",
        f"repos/{ctx.repo_flag}/pulls/{ctx.pr}/merge-async",
        "-f",
        f"merge_method={ctx.strategy}",
        "-f",
        "merge_action=direct_merge",
        "-f",
        f"sha={ctx.head_sha}",
    ]
    if subject:
        cmd += ["-f", f"commit_title={subject}"]
    if body:
        cmd += ["-f", f"commit_message={body}"]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=_MERGE_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        # The request may have landed; the readback decides.
        raise _MergeFailureError(
            f"merge-async request for PR #{ctx.pr} timed out after "
            f"{_MERGE_TIMEOUT_SECONDS}s ({exc}); outcome unknown",
            3,
            "Timeout",
        ) from exc
    parsed = _parse_json_object(result.stdout)
    in_flight = result.returncode != 0 and "HTTP 409" in (result.stderr or "")
    if result.returncode == 0 or (in_flight and _async_uuid(parsed)):
        return parsed
    detail = sanitize_failure_detail(result.stderr or result.stdout)
    raise _MergeFailureError(
        f"merge-async request was refused: {detail}", _EXIT_NOT_MERGEABLE, "General"
    )


def _fetch_async_status(ctx: _MergeContext, uuid: str) -> dict[str, Any] | None:
    """GET one merge-async status; None when the poll itself failed."""
    cmd = [
        "gh",
        "api",
        "-H",
        f"X-GitHub-Api-Version: {_ASYNC_API_VERSION}",
        f"repos/{ctx.repo_flag}/pulls/{ctx.pr}/merge-async/{uuid}",
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=_API_CALL_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None
    if result.returncode != 0:
        return None
    return _parse_json_object(result.stdout) or None


def _async_status_is_merged(body: dict[str, Any], pr: int) -> bool:
    """True when merged, False while pending; any other status raises.

    Only the polled body status is terminal. The HTTP code is not: a 202 means
    accepted and a 200 can mean already queued.
    """
    status = body.get("status")
    if status == "merged":
        return True
    if status == "pending":
        return False
    details = body.get("details")
    message = details.get("message") if isinstance(details, dict) else None
    if status == "failed":
        raise _MergeFailureError(
            f"merge-async reported failure: {message or body}", _EXIT_NOT_MERGEABLE, "General"
        )
    if status == "enqueued":
        raise _MergeFailureError(
            f"merge-async queued PR #{pr} and did not merge it: {message or body}",
            _EXIT_NOT_MERGEABLE,
            "General",
        )
    raise _MergeFailureError(
        f"merge-async returned an unrecognized status {status!r}: {body}", 3, "ApiError"
    )


def _wait_for_async_merge(ctx: _MergeContext, accepted: dict[str, Any]) -> None:
    """Poll the merge-async UUID to a terminal status within a bounded time."""
    if _async_status_is_merged(accepted, ctx.pr):
        return
    uuid = _async_uuid(accepted)
    if not uuid:
        raise _MergeFailureError(
            f"merge-async accepted PR #{ctx.pr} but returned no request UUID to poll; "
            "outcome unknown",
            3,
            "ApiError",
        )
    deadline = time.monotonic() + _ASYNC_POLL_TIMEOUT_SECONDS
    errors = 0
    while time.monotonic() < deadline:
        body = _fetch_async_status(ctx, uuid)
        errors = errors + 1 if body is None else 0
        if errors >= _ASYNC_POLL_MAX_ERRORS:
            raise _MergeFailureError(
                f"merge-async status poll for PR #{ctx.pr} failed {errors} times in a "
                "row; outcome unknown",
                3,
                "ApiError",
            )
        if body is not None and _async_status_is_merged(body, ctx.pr):
            return
        time.sleep(_ASYNC_POLL_INTERVAL_SECONDS)
    raise _MergeFailureError(
        f"merge-async for PR #{ctx.pr} still pending after "
        f"{_ASYNC_POLL_TIMEOUT_SECONDS:g}s; outcome unknown",
        3,
        "Timeout",
    )


def _merge_stack_async(
    ctx: _MergeContext,
    subject: str,
    body: str,
    graphql_output: str,
) -> None:
    """Merge a stacked PR through the asynchronous endpoint (issue #5473).

    Gate the target and every unmerged downstack member, pin their heads,
    re-check the pins just before the request, request the merge pinned to the
    reviewed head, poll to a terminal status, then confirm the heads that landed.
    Returns when GitHub reports merged. Every failure raises _MergeFailureError
    carrying the original GraphQL refusal, so the caller's readback can still
    adjudicate, except a post-merge head mismatch, which no readback may recover.
    """
    stack: int | None = None
    pins: dict[int, str] | None = None
    try:
        stack = _stack_number(ctx.pr, ctx.repo_flag)
        pins = _assert_stack_ready(ctx, stack)
        _assert_pins_unchanged(ctx, stack, pins)
        accepted = _request_async_merge(ctx, subject, body)
        _wait_for_async_merge(ctx, accepted)
    except _MergeFailureError as failure:
        raise _MergeFailureError(
            f"PR #{ctx.pr} is part of a stack and the asynchronous merge did not "
            f"complete it: {failure.message}\nGraphQL said: {graphql_output}",
            failure.code,
            failure.error_type,
            approval=_APPROVAL_ASYNC,
            stack=stack,
            pins=pins,
        ) from failure
    _assert_heads_landed_as_gated(ctx, stack, pins)


def _handle_merge_failure(
    merge_result: subprocess.CompletedProcess[str],
    ctx: _MergeContext,
    subject: str,
    body: str,
) -> str:
    """Translate a non-zero gh-pr-merge return into an envelope or a failure.

    Conflicts and head-moved refusals emit their envelope and exit 100 directly.
    On a BLOCKED-keyword failure, retry once via the REST merge endpoint
    (issue #4362), pinned to the same head SHA.  REST enforces the same branch
    rules as GraphQL but resolves the policy check differently; a 200 with
    ``merged: true`` confirms the ruleset was satisfied and the GraphQL refusal
    was spurious.  A stack refusal skips that endpoint, which answers 403 for a
    stack, and goes to the asynchronous merge instead (issue #5473).  Returns
    the approval authority when REST or the asynchronous merge merged the PR:
    branch protection for REST, the script's own readiness gate for merge-async,
    which evaluates no branch protection.  Any other failure raises
    _MergeFailureError so the caller can read the PR back before reporting.
    """
    pr = ctx.pr
    output = merge_result.stderr or merge_result.stdout
    lowered = output.lower()
    # Refusals still go through the readback: gh can report an error after the
    # merge landed, and a landed merge must not be reported as refused.
    if any(kw in lowered for kw in _HEAD_MOVED_KEYWORDS):
        raise _MergeFailureError(
            f"PR #{pr} head moved after review; refusing the stale target "
            f"(pinned {ctx.head_sha or 'none'}): {output}",
            _EXIT_NOT_MERGEABLE,
            "General",
        )
    if any(kw in output for kw in ("not mergeable", "cannot be merged", "conflicts")):
        raise _MergeFailureError(
            f"PR #{pr} is not mergeable: {output}", _EXIT_NOT_MERGEABLE, "General"
        )
    if not ctx.auto and any(kw in output for kw in _STACK_KEYWORDS):
        # The synchronous REST endpoint refuses a stack, so go asynchronous.
        _merge_stack_async(ctx, subject, body, output)
        return _APPROVAL_ASYNC
    if not ctx.auto and any(kw in output for kw in _BLOCKED_KEYWORDS):
        # GraphQL refused with a BLOCKED policy error; retry via REST once.
        rest_result = _rest_merge(
            pr,
            ctx.repo_flag,
            ctx.strategy,
            ctx.head_sha,
            subject,
            body,
        )
        if rest_result.returncode == 0:
            try:
                rest_data = json.loads(rest_result.stdout)
            except json.JSONDecodeError:
                rest_data = {}
            if rest_data.get("merged") or _pr_is_merged(pr, ctx.repo_flag):
                return _APPROVAL
        # REST also failed; surface the original GraphQL error.
        raise _MergeFailureError(
            f"PR #{pr} is blocked by branch protection policy: {output}\n"
            "Hint: use --auto to enable auto-merge when checks pass.",
            _EXIT_NOT_MERGEABLE,
            "General",
        )
    raise _MergeFailureError(
        f"Failed to merge PR #{pr}: {sanitize_failure_detail(output)}", 3, "ApiError"
    )


def _run_merge(merge_args: list[str], pr: int) -> subprocess.CompletedProcess[str]:
    """Run gh pr merge; a timeout becomes _MergeFailureError (outcome unknown)."""
    try:
        return subprocess.run(
            merge_args,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=_MERGE_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise _MergeFailureError(
            f"gh pr merge for PR #{pr} timed out after {_MERGE_TIMEOUT_SECONDS}s "
            f"({exc}); outcome unknown",
            3,
            "Timeout",
        ) from exc


def _read_back(pr: int, repo_flag: str) -> dict[str, Any] | None:
    """Read the PR's post-merge state from GitHub.

    Returns None on any query, timeout, or parse failure so the caller can
    never report success from an unverified merge (issue #5767).
    """
    try:
        result = subprocess.run(
            ["gh", "pr", "view", str(pr), "--repo", repo_flag, "--json", _READBACK_FIELDS],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _login(node: Any) -> str | None:
    """Return the login of a gh user object, or None."""
    if isinstance(node, dict):
        login = node.get("login")
        return login if isinstance(login, str) and login else None
    return None


def _merge_commit_oid(readback: dict[str, Any] | None) -> str | None:
    """Return the merge commit oid from a readback, or None."""
    node = (readback or {}).get("mergeCommit")
    oid = node.get("oid") if isinstance(node, dict) else None
    return oid if isinstance(oid, str) and oid else None


def _actor(readback: dict[str, Any] | None) -> str | None:
    """Return who merged, or who enabled auto-merge, per the readback."""
    if not readback:
        return None
    merged_by = _login(readback.get("mergedBy"))
    if merged_by:
        return merged_by
    auto_request = readback.get("autoMergeRequest")
    if isinstance(auto_request, dict):
        return _login(auto_request.get("enabledBy"))
    return None


def _rollback_hint(strategy: str, merge_commit: str | None) -> str | None:
    """Return the command a human runs to undo a landed merge, or None.

    A merge commit has two parents, so its revert needs ``-m 1``. A rebase
    merge lands several commits and has no single commit to revert.
    """
    if not merge_commit:
        return None
    if strategy == "merge":
        return f"git revert -m 1 {merge_commit}"
    if strategy == "squash":
        return f"git revert {merge_commit}"
    return f"revert each commit the rebase merge landed, ending at {merge_commit}"


def _build_audit(
    ctx: _MergeContext,
    action: str,
    result: str,
    readback: dict[str, Any] | None = None,
    original_error: str | None = None,
    approval: str = _APPROVAL,
) -> dict[str, Any]:
    """Build the REQ-043 audit record for one merge attempt.

    ``approval`` names who approved the merge: branch protection unless the
    merge went through merge-async, which evaluates none.
    """
    merge_commit = _merge_commit_oid(readback)
    merged = (readback or {}).get("state") == "MERGED"
    audit: dict[str, Any] = {
        "actor": _actor(readback),
        "target": {
            "repo": ctx.repo_flag,
            "pull_request": ctx.pr,
            "head_sha": ctx.head_sha or None,
        },
        "action": action,
        "approval": approval,
        "result": result,
        "rollback": _rollback_hint(ctx.strategy, merge_commit) if merged else None,
        "residual_risk": _RESIDUAL_RISK,
    }
    if original_error:
        audit["original_error"] = original_error
    return audit


def _emit_merge_success(
    ctx: _MergeContext,
    readback: dict[str, Any],
    original_error: str | None,
    approval: str = _APPROVAL,
) -> int:
    """Emit the success envelope for a readback that shows MERGED or queued.

    The readback head must equal the pinned head. A missing or different head
    means GitHub merged or queued something other than what was reviewed, so
    the result is reported as unverified (exit 3), never as success.
    """
    pr = ctx.pr
    readback_head = str(readback.get("headRefOid") or "")
    if readback_head.lower() != ctx.head_sha.lower():
        _emit_error(
            f"PR #{pr} readback head {readback_head or 'unknown'} does not match "
            f"the pinned head {ctx.head_sha}; merge result is unverified",
            3,
            "ApiError",
            ctx.output_format,
            pr,
            audit=_build_audit(
                ctx,
                "merge",
                "unverified: readback head differs",
                readback,
                original_error,
                approval,
            ),
        )
    merged = readback.get("state") == "MERGED"
    recovered = original_error is not None
    if merged:
        action, state, message = "merged", "MERGED", "PR merged successfully"
        if recovered:
            message = "PR merged (recovered: merge command failed but readback shows MERGED)"
        result = "merged"
    else:
        action, state = "auto-merge-enabled", "PENDING"
        message = "Auto-merge enabled; PR is NOT merged yet"
        result = "queued, not merged"
    audit = _build_audit(ctx, action, result, readback, original_error, approval)
    write_skill_output(
        {
            "pull_request": pr,
            "number": pr,
            "state": state,
            "action": action,
            "strategy": ctx.strategy,
            "branch_deleted": ctx.delete_branch,
            "message": message,
            "recovered": recovered,
            "readback": {
                "state": readback.get("state"),
                "merge_commit": _merge_commit_oid(readback),
                "merged_by": _login(readback.get("mergedBy")),
                "auto_merge_enabled": bool(readback.get("autoMergeRequest")),
            },
            "audit": audit,
        },
        output_format=ctx.output_format,
        human_summary=f"{message} (PR #{pr}, strategy={ctx.strategy})",
        status="PASS",
        script_name=_SCRIPT_NAME,
    )
    return 0


def _finalize_after_success(ctx: _MergeContext, approval: str = _APPROVAL) -> int:
    """Read back after a zero-exit merge command; never report unverified success."""
    readback = _read_back(ctx.pr, ctx.repo_flag)
    if readback is None:
        _emit_error(
            f"merge command reported success but the readback query for PR "
            f"#{ctx.pr} failed; merge state is unverified",
            3,
            "ApiError",
            ctx.output_format,
            ctx.pr,
            audit=_build_audit(ctx, "merge", "unverified: readback failed", approval=approval),
        )
    state = readback.get("state")
    if state == "MERGED":
        return _emit_merge_success(ctx, readback, None, approval)
    if state == "OPEN" and readback.get("autoMergeRequest"):
        return _emit_merge_success(ctx, readback, None, approval)
    _emit_error(
        f"merge command reported success but readback shows state={state} "
        "with no auto-merge request; PR #"
        f"{ctx.pr} is not merged",
        3,
        "ApiError",
        ctx.output_format,
        ctx.pr,
        audit=_build_audit(
            ctx, "merge", f"not merged: readback state={state}", readback, approval=approval
        ),
    )


def _check_recovered_stack(ctx: _MergeContext, failure: _MergeFailureError) -> _MergeFailureError:
    """Run the post-merge head check for a merge-async failure the readback recovers.

    Returns ``failure`` unchanged when the failure did not come out of a gated
    merge-async (no pins), or when every gated head still matches its pin.
    Otherwise returns the landed failure the check raised.
    """
    if failure.stack is None or failure.pins is None:
        return failure
    try:
        _assert_heads_landed_as_gated(ctx, failure.stack, failure.pins)
    except _MergeFailureError as landed:
        return landed
    return failure


def _recover_or_fail(ctx: _MergeContext, failure: _MergeFailureError) -> int:
    """After a failed merge command, let the readback decide.

    MERGED means the command failed after the merge landed (or a retry raced
    it): report success with recovered=true and keep the original error in the
    audit record. Anything else, including a failed readback, reports the
    original failure.
    """
    readback = _read_back(ctx.pr, ctx.repo_flag)
    if failure.landed:
        _emit_error(
            failure.message,
            failure.code,
            failure.error_type,
            ctx.output_format,
            ctx.pr,
            audit=_build_audit(
                ctx,
                "merge",
                "merged, post-merge check failed",
                readback,
                failure.message,
                failure.approval,
            ),
        )
    if readback is not None and readback.get("state") == "MERGED":
        # A merge-async that errored after the gate may still have landed the
        # stack. The post-merge head check is what the success path runs, so a
        # recovered success runs it too before it reports anything.
        failure = _check_recovered_stack(ctx, failure)
        if failure.landed:
            return _recover_or_fail(ctx, failure)
        return _emit_merge_success(ctx, readback, failure.message, failure.approval)
    if (
        readback is not None
        and ctx.auto
        and readback.get("state") == "OPEN"
        and readback.get("autoMergeRequest")
    ):
        # The auto-merge request is armed despite the error; report it as
        # queued so a caller does not retry into a duplicate request.
        return _emit_merge_success(ctx, readback, failure.message, failure.approval)
    note = ""
    if readback is None:
        note = " (readback query also failed; merge state unverified)"
    _emit_error(
        failure.message + note,
        failure.code,
        failure.error_type,
        ctx.output_format,
        ctx.pr,
        audit=_build_audit(
            ctx,
            "merge",
            "failed" if readback is not None else "failed, state unverified",
            readback,
            failure.message,
            failure.approval,
        ),
    )


def _resolve_strategy(
    args: argparse.Namespace,
    repo_flag: str,
    pr: int,
) -> dict[str, bool] | None:
    """Pick args.strategy from repo policy when omitted; return the settings used."""
    if args.strategy is not None:
        # Issue #4490: an explicit strategy does not need repository-settings
        # discovery. The merge endpoint remains the authority for whether
        # GitHub permits that strategy.
        return None
    # Wrap REST failures in a structured envelope so consumers can parse.
    try:
        repo_settings = get_allowed_merge_methods(repo_flag)
    except (RuntimeError, ValueError) as exc:
        if is_pr_not_found(str(exc)):
            # repos/<owner>/<repo> answers 404 only when the repository is absent.
            # The REST "Not Found" wording is the one marker the classifier shares.
            _emit_error(
                f"Repository {repo_flag} not found: {sanitize_failure_detail(str(exc))}",
                2,
                "NotFound",
                args.output_format,
                pr,
            )
        _emit_error(sanitize_failure_detail(str(exc)), 3, "ApiError", args.output_format, pr)
    chosen = resolve_default_strategy(repo_settings)
    if chosen is None:
        _emit_error(
            f"No merge strategy allowed by {repo_flag}.",
            1,
            "InvalidParams",
            args.output_format,
            pr,
        )
    args.strategy = chosen
    return repo_settings


def _require_expected_head(
    pr_data: dict[str, Any],
    expected: str,
    ctx: _MergeContext,
) -> None:
    """Exit 1 when the PR head is not the reviewed SHA (wrong target or stale)."""
    if not expected:
        return
    actual = str(pr_data.get("headRefOid") or "")
    if actual.lower() == expected.lower():
        return
    _emit_error(
        f"PR #{ctx.pr} head does not match the reviewed commit: expected "
        f"{expected}, actual {actual or 'unknown'}. Wrong PR or the branch "
        "moved after review; no merge attempted.",
        1,
        "InvalidParams",
        ctx.output_format,
        ctx.pr,
        audit=_build_audit(ctx, "none", f"refused: head is {actual or 'unknown'}"),
    )


def _emit_already_merged(ctx: _MergeContext) -> int:
    """Report an already merged PR without a second merge call (retry-safe)."""
    pr = ctx.pr
    write_skill_output(
        {
            "pull_request": pr,
            "number": pr,
            "state": "MERGED",
            "action": "none",
            "message": "PR already merged",
            "audit": _build_audit(ctx, "none", "already merged; no merge call"),
        },
        output_format=ctx.output_format,
        human_summary=f"PR #{pr} already merged",
        status="PASS",
        script_name=_SCRIPT_NAME,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_format = args.output_format
    pr = args.pull_request
    if args.expected_head_sha and not _SHA_PATTERN.match(args.expected_head_sha):
        _emit_error(
            "--expected-head-sha must be a 40-character hex commit SHA",
            1,
            "InvalidParams",
            output_format,
            pr,
        )

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    repo_flag = f"{resolved.owner}/{resolved.repo}"

    repo_settings = _resolve_strategy(args, repo_flag, pr)
    validate_strategy(args.strategy, repo_settings, repo_flag, output_format)

    pr_data = _fetch_pr_state(pr, repo_flag, output_format)
    # Issue #5767: pin the merge to the reviewed head. An explicit expected SHA
    # wins; otherwise pin to the head just fetched.
    head_sha = args.expected_head_sha or str(pr_data.get("headRefOid") or "")
    ctx = _MergeContext(
        pr=pr,
        repo_flag=repo_flag,
        head_sha=head_sha,
        strategy=args.strategy,
        delete_branch=args.delete_branch,
        auto=args.auto,
        output_format=output_format,
    )
    _require_expected_head(pr_data, args.expected_head_sha, ctx)

    if pr_data.get("state") == "MERGED":
        return _emit_already_merged(ctx)

    if pr_data.get("state") == "CLOSED":
        _emit_error(
            f"PR #{pr} is closed and cannot be merged",
            _EXIT_NOT_MERGEABLE,
            "General",
            output_format,
            pr,
            audit=_build_audit(ctx, "none", "refused: PR is closed"),
        )

    if not head_sha:
        _emit_error(
            f"PR #{pr} head SHA is unknown, so the merge cannot be pinned to a "
            "reviewed commit; no merge attempted",
            3,
            "ApiError",
            output_format,
            pr,
            audit=_build_audit(ctx, "none", "refused: head SHA unknown"),
        )

    # Issue #2637: reject UNKNOWN mergeability on a direct merge. --auto is
    # exempt: it hands the merge decision to GitHub's own gate.
    if not args.auto:
        _reject_unknown_merge_state(pr_data, pr, output_format)

    approval = _APPROVAL
    try:
        merge_result = _run_merge(_build_merge_args(args, pr, repo_flag, head_sha), pr)
        if merge_result.returncode != 0:
            sanitized_body = filter_coauthor_trailers(args.body) if args.body else ""
            approval = _handle_merge_failure(merge_result, ctx, args.subject, sanitized_body)
    except _MergeFailureError as failure:
        return _recover_or_fail(ctx, failure)
    return _finalize_after_success(ctx, approval)


if __name__ == "__main__":
    raise SystemExit(main())

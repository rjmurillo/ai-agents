#!/usr/bin/env python3
"""Update a pull request's head branch with its base, server side.

Calls GitHub's update-branch endpoint
(``PUT /repos/{owner}/{repo}/pulls/{pull_number}/update-branch``), the API
behind the "Update branch" button. GitHub merges the base into the head on the
server and answers 202 Accepted before the merge commit exists, so the call is
asynchronous. No local git hook runs on that merge.

Behavior:
- A closed or merged PR is refused before any mutation (exit 1).
- A PR that is not behind its base (compare ``behind_by == 0``) is reported as
  success with ``already_up_to_date: true`` and no PUT. A 422 saying the base
  has no new commits is reported the same way.
- ``--expected-head-sha`` is checked against the PR head first, then forwarded
  as ``expected_head_sha``. A local mismatch, or GitHub's 422 when the head
  moved in between, maps to exit 1, error type VerificationFailed,
  ``reason: head_moved``.
- Without ``--wait`` the script returns after the 202 with the old head SHA and
  the API message. With ``--wait`` it polls until compare shows the PR is no
  longer behind, then reports the new head SHA. The deadline is
  ``--timeout-seconds``; a poll already in flight can overrun it by up to two
  gh calls of 30s each. A head change alone does not end the wait, since an unrelated push can
  move the head. A timeout exits 3 and says the update was already requested.
- Without ``--expected-head-sha`` the update applies to whatever head GitHub
  sees when it runs. Unattended callers should pass the SHA they reviewed.

All output goes through the standard skill envelope per ADR-056.

Exit codes follow ADR-035:
    0 - Success (update requested, completed, or already up to date)
    1 - Invalid parameters / logic error (closed or merged PR, head moved)
    2 - Not found
    3 - External error (API failure, wait timeout)
    4 - Auth error
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
from urllib.parse import quote

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
    check_gh_auth,
    describe_gh_auth_failure,
    is_auth_failure_text,
    resolve_repo_params,
    sanitize_failure_detail,
)
from github_core.output import (
    add_output_format_arg,
    write_skill_error,
    write_skill_output,
)

_SCRIPT_NAME = "update_pr_branch.py"
_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")
_GH_TIMEOUT_SECONDS = 30
_POLL_INTERVAL_SECONDS = 5.0
_DEFAULT_WAIT_SECONDS = 120

# Matched case-insensitively against the gh stdout and stderr of a failed PUT.
_HEAD_MOVED_MARKERS = ("expected head sha",)
_UP_TO_DATE_MARKERS = ("no new commits",)
_NOT_FOUND_MARKERS = ("not found", "could not resolve to a pullrequest")

# Injection points for tests; production uses the real clock.
_monotonic = time.monotonic
_sleep = time.sleep


@dataclass(frozen=True)
class _PrSnapshot:
    state: str
    head_sha: str
    base_ref: str


@dataclass(frozen=True)
class _Context:
    pr: int
    repo_flag: str
    expected_head_sha: str
    output_format: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Update a pull request's head branch with its base (server side).",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--pull-request", type=int, required=True, help="Pull request number",
    )
    parser.add_argument(
        "--expected-head-sha", default="",
        help=(
            "Head commit SHA (40 hex) you expect the PR to have. GitHub refuses "
            "the update when the head differs."
        ),
    )
    parser.add_argument(
        "--wait", action="store_true",
        help="Poll until the head SHA changes or the PR is no longer behind.",
    )
    parser.add_argument(
        "--timeout-seconds", type=int, default=None,
        help=f"Wait bound in seconds, with --wait (default {_DEFAULT_WAIT_SECONDS}).",
    )
    add_output_format_arg(parser)
    return parser


def _emit_error(
    message: str,
    code: int,
    error_type: str,
    ctx_format: str,
    pr: int,
    **extra: Any,
) -> NoReturn:
    """Emit the error envelope, then exit with ``code``."""
    write_skill_error(
        message,
        code,
        error_type=error_type,
        output_format=ctx_format,
        script_name=_SCRIPT_NAME,
        extra={"pull_request": pr, **extra},
    )
    raise SystemExit(code)


def _run_gh(args: list[str], ctx: _Context, what: str) -> subprocess.CompletedProcess[str]:
    """Run one gh command; a timeout becomes an exit-3 envelope."""
    try:
        return subprocess.run(
            args,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GH_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        _emit_error(
            f"{what} for PR #{ctx.pr} timed out after {_GH_TIMEOUT_SECONDS}s; "
            "outcome unknown",
            3,
            "Timeout",
            ctx.output_format,
            ctx.pr,
        )


def _fail_text(result: subprocess.CompletedProcess[str]) -> str:
    return f"{result.stdout or ''}\n{result.stderr or ''}"


def _has_marker(text: str, markers: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in markers)


def _fetch_pr(ctx: _Context) -> _PrSnapshot:
    """Read state, head SHA, and base ref; emit an envelope on failure."""
    result = _run_gh(
        [
            "gh", "pr", "view", str(ctx.pr), "--repo", ctx.repo_flag,
            "--json", "state,headRefOid,baseRefName",
        ],
        ctx,
        "Reading PR state",
    )
    if result.returncode != 0:
        _fail_lookup(result, ctx)
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict):
        _emit_error(
            f"PR #{ctx.pr} state response was not a JSON object",
            3, "ApiError", ctx.output_format, ctx.pr,
        )
    return _PrSnapshot(
        state=str(data.get("state") or ""),
        head_sha=str(data.get("headRefOid") or ""),
        base_ref=str(data.get("baseRefName") or ""),
    )


def _fail_lookup(result: subprocess.CompletedProcess[str], ctx: _Context) -> NoReturn:
    text = _fail_text(result)
    detail = sanitize_failure_detail(text)
    if is_auth_failure_text(text):
        _emit_error(
            f"Not authorized to read PR #{ctx.pr}: {detail}",
            4, "AuthError", ctx.output_format, ctx.pr,
        )
    if _has_marker(text, _NOT_FOUND_MARKERS):
        _emit_error(
            f"PR #{ctx.pr} not found in {ctx.repo_flag}",
            2, "NotFound", ctx.output_format, ctx.pr,
        )
    _emit_error(
        f"Failed to read PR #{ctx.pr}: {detail}",
        3, "ApiError", ctx.output_format, ctx.pr,
    )


def _behind_by(ctx: _Context, snap: _PrSnapshot) -> tuple[int | None, str]:
    """Return (commits the head is behind its base, precheck note).

    ``None`` means the compare could not be read. The caller still lets GitHub
    adjudicate the update, and the note says why the precheck is missing.
    """
    if not snap.head_sha or not snap.base_ref:
        return None, "unavailable: PR head SHA or base ref missing"
    result = _run_gh(
        [
            "gh", "api",
            f"repos/{ctx.repo_flag}/compare/{quote(snap.base_ref, safe='/')}...{snap.head_sha}",
            "--jq", ".behind_by",
        ],
        ctx,
        "Comparing head with base",
    )
    raw = (result.stdout or "").strip()
    if result.returncode != 0 or not raw.isdigit():
        reason = sanitize_failure_detail(_fail_text(result)) or "no output"
        return None, f"unavailable: compare failed ({reason})"
    return int(raw), "ok"


def _build_update_args(pr: int, repo_flag: str, expected_head_sha: str) -> list[str]:
    args = ["gh", "api", "-X", "PUT", f"repos/{repo_flag}/pulls/{pr}/update-branch"]
    if expected_head_sha:
        args += ["-f", f"expected_head_sha={expected_head_sha}"]
    return args


def _api_message(stdout: str) -> str:
    try:
        data = json.loads(stdout or "")
    except json.JSONDecodeError:
        return ""
    if isinstance(data, dict):
        return str(data.get("message") or "")
    return ""


def _request_update(ctx: _Context) -> tuple[bool, str]:
    """PUT update-branch. Return (already up to date, API message)."""
    result = _run_gh(
        _build_update_args(ctx.pr, ctx.repo_flag, ctx.expected_head_sha),
        ctx,
        "Update-branch request",
    )
    if result.returncode == 0:
        return False, sanitize_failure_detail(_api_message(result.stdout))
    text = _fail_text(result)
    if _has_marker(text, _UP_TO_DATE_MARKERS):
        message = sanitize_failure_detail(_api_message(result.stdout))
        return True, message or "No new commits on the base branch"
    _fail_update(result, text, ctx)


def _fail_update(
    result: subprocess.CompletedProcess[str],
    text: str,
    ctx: _Context,
) -> NoReturn:
    detail = sanitize_failure_detail(_api_message(result.stdout) or text)
    if _has_marker(text, _HEAD_MOVED_MARKERS):
        _head_moved(
            ctx,
            "",
            f"GitHub refused the update because the head is no longer {ctx.expected_head_sha}",
        )
    if is_auth_failure_text(text):
        _emit_error(
            f"Not authorized to update PR #{ctx.pr}: {detail}",
            4, "AuthError", ctx.output_format, ctx.pr,
        )
    if _has_marker(text, _NOT_FOUND_MARKERS):
        _emit_error(
            f"PR #{ctx.pr} not found in {ctx.repo_flag} when updating",
            2, "NotFound", ctx.output_format, ctx.pr,
        )
    _emit_error(
        f"Update-branch for PR #{ctx.pr} failed: {detail}",
        3, "ApiError", ctx.output_format, ctx.pr,
    )


def _wait_for_update(ctx: _Context, old_head: str, timeout: int) -> tuple[str, str]:
    """Poll until compare shows the PR is not behind. Return (head, why).

    A head change alone is not proof: an unrelated push can move the head
    while the PR stays behind. An unreadable compare never ends the wait; the
    timeout envelope carries the last precheck note instead.
    """
    deadline = _monotonic() + timeout
    while True:
        snap = _fetch_pr(ctx)
        behind, precheck = _behind_by(ctx, snap)
        moved = bool(snap.head_sha) and snap.head_sha != old_head
        if behind == 0:
            return snap.head_sha, "head_changed" if moved else "not_behind"
        remaining = deadline - _monotonic()
        if remaining <= 0:
            _emit_error(
                f"PR #{ctx.pr} was not confirmed up to date within {timeout}s "
                f"(last precheck: {precheck}). The update was requested (202); "
                "re-run with --wait to request and poll again.",
                3, "Timeout", ctx.output_format, ctx.pr,
                old_head_sha=old_head,
                last_head_sha=snap.head_sha or None,
                last_precheck=precheck,
                update_requested=True,
            )
        _sleep(min(_POLL_INTERVAL_SECONDS, remaining))


def _emit_result(ctx: _Context, data: dict[str, Any], summary: str) -> int:
    write_skill_output(
        {
            "pull_request": ctx.pr,
            "expected_head_sha": ctx.expected_head_sha or None,
            **data,
        },
        output_format=ctx.output_format,
        human_summary=summary,
        status="PASS",
        script_name=_SCRIPT_NAME,
    )
    return 0


def _validate_args(args: argparse.Namespace) -> None:
    fmt, pr = args.output_format, args.pull_request
    if args.expected_head_sha and not _SHA_PATTERN.match(args.expected_head_sha):
        _emit_error(
            "--expected-head-sha must be a 40-character hex commit SHA",
            1, "InvalidParams", fmt, pr,
        )
    if args.timeout_seconds is not None and not args.wait:
        _emit_error("--timeout-seconds requires --wait", 1, "InvalidParams", fmt, pr)
    if args.timeout_seconds is not None and args.timeout_seconds <= 0:
        _emit_error("--timeout-seconds must be positive", 1, "InvalidParams", fmt, pr)


def _require_auth(fmt: str, pr: int) -> None:
    auth = check_gh_auth()
    if not auth.is_authenticated:
        message, code, error_type = describe_gh_auth_failure(auth)
        _emit_error(message, code, error_type, fmt, pr)


def _require_open(ctx: _Context, snap: _PrSnapshot) -> None:
    if snap.state != "OPEN":
        shown = snap.state.lower() or "in an unknown state"
        _emit_error(
            f"PR #{ctx.pr} is {shown}; only an open PR can be updated",
            1, "InvalidParams", ctx.output_format, ctx.pr,
            state=snap.state or None,
        )


def _head_moved(ctx: _Context, current_head: str, source: str) -> NoReturn:
    """Exit 1 for a head that is not the pinned SHA.

    ``current_head`` is empty when GitHub refused the PUT: the head read
    before the call is stale by then, so it is reported as null, not guessed.
    """
    _emit_error(
        f"PR #{ctx.pr} head moved: {source}. Re-read the head and retry.",
        1, "VerificationFailed", ctx.output_format, ctx.pr,
        reason="head_moved",
        expected_head_sha=ctx.expected_head_sha,
        current_head_sha=current_head or None,
    )


def _require_expected_head(ctx: _Context, snap: _PrSnapshot) -> None:
    """Refuse locally when the pin already disagrees with the PR head."""
    if ctx.expected_head_sha and snap.head_sha.lower() != ctx.expected_head_sha.lower():
        _head_moved(
            ctx,
            snap.head_sha,
            f"the PR head is {snap.head_sha or 'unknown'}, not {ctx.expected_head_sha}",
        )


def _up_to_date_result(ctx: _Context, snap: _PrSnapshot, behind: int | None, msg: str) -> int:
    return _emit_result(
        ctx,
        {
            "action": "none",
            "already_up_to_date": True,
            "old_head_sha": snap.head_sha,
            "new_head_sha": snap.head_sha,
            "behind_by": behind,
            "message": msg,
        },
        f"PR #{ctx.pr} is already up to date with {snap.base_ref}",
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _validate_args(args)
    _require_auth(args.output_format, args.pull_request)
    resolved = resolve_repo_params(args.owner, args.repo)
    ctx = _Context(
        pr=args.pull_request,
        repo_flag=f"{resolved.owner}/{resolved.repo}",
        expected_head_sha=args.expected_head_sha,
        output_format=args.output_format,
    )

    snap = _fetch_pr(ctx)
    _require_open(ctx, snap)
    _require_expected_head(ctx, snap)
    behind, precheck = _behind_by(ctx, snap)
    if behind == 0:
        return _up_to_date_result(ctx, snap, behind, "Head already contains the base")

    up_to_date, message = _request_update(ctx)
    if up_to_date:
        return _up_to_date_result(ctx, snap, behind, message)

    data: dict[str, Any] = {
        "action": "update_requested",
        "already_up_to_date": False,
        "old_head_sha": snap.head_sha,
        "new_head_sha": None,
        "behind_by": behind,
        "precheck": precheck,
        "message": message,
    }
    if not args.wait:
        return _emit_result(ctx, data, f"PR #{ctx.pr} update requested")

    timeout = args.timeout_seconds or _DEFAULT_WAIT_SECONDS
    new_head, why = _wait_for_update(ctx, snap.head_sha, timeout)
    data.update(action="updated", new_head_sha=new_head, wait_result=why)
    return _emit_result(ctx, data, f"PR #{ctx.pr} head is now {new_head}")


if __name__ == "__main__":
    raise SystemExit(main())

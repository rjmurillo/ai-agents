#!/usr/bin/env python3
"""Mark a draft pull request ready for review, or convert it back to draft.

Wraps ``gh pr ready`` (GraphQL ``markPullRequestReadyForReview``) and
``gh pr ready --undo`` (``convertPullRequestToDraft``), so an agent that opens a
PR with ``new_pr.py --draft`` has a compliant way to take it out of draft.

Behavior:
- A PR that is not OPEN is refused before any mutation (exit 1).
- A PR already in the requested state is success with ``action: none``.
- ``--expected-head-sha`` is checked against the PR head before the mutation. A
  mismatch exits 1 with error type VerificationFailed and ``reason: head_moved``.
  Neither GitHub mutation accepts a head guard, so a push that lands between the
  read and the mutation is not caught. The read-back reports the head it saw.
- After the mutation the PR is read again. If ``isDraft`` is not the requested
  value the outcome is unverified and the script exits 3.
- ``--dry-run`` runs every read check and mutates nothing.

Output uses the standard skill envelope (ADR-056). Exit codes follow ADR-035:
    0 - Success (changed, or already in the requested state)
    1 - Invalid parameters / logic error (PR not open, head moved)
    2 - Not found
    3 - External error (API failure, timeout, unverified outcome)
    4 - Auth error
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, NoReturn

_plugin_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root and os.path.isdir(os.path.join(_plugin_root, "lib", "github_core")):
    _lib_dir = os.path.join(_plugin_root, "lib")
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
from github_core.not_found import is_pr_not_found
from github_core.output import (
    add_output_format_arg,
    write_skill_error,
    write_skill_output,
)

_SCRIPT_NAME = "set_pr_ready.py"
_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")
_GH_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class _PrSnapshot:
    state: str
    is_draft: bool
    head_sha: str


@dataclass(frozen=True)
class _Context:
    pr: int
    repo_flag: str
    expected_head_sha: str
    to_draft: bool
    output_format: str

    @property
    def target_label(self) -> str:
        return "draft" if self.to_draft else "ready"


_HELP_EPILOG = """\
examples:
  %(prog)s --pull-request 123
  %(prog)s --pull-request 123 --expected-head-sha 0123456789abcdef0123456789abcdef01234567
  %(prog)s --pull-request 123 --draft

exit codes:
  0  success (changed, or already in the requested state)
  1  invalid parameters / logic error (PR not open, head moved)
  2  not found
  3  external error (API failure, timeout, unverified outcome)
  4  auth error
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Mark a draft pull request ready for review, or convert it back to draft.",
        epilog=_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
        "--expected-head-sha",
        default="",
        help="Head commit SHA (40 hex) you expect the PR to have. Refuses when the head differs.",
    )
    parser.add_argument(
        "--draft",
        action="store_true",
        help="Convert the PR back to draft instead of marking it ready",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run every read check and report what would change; change nothing",
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
            f"{what} for PR #{ctx.pr} timed out after {_GH_TIMEOUT_SECONDS}s; outcome unknown",
            3,
            "Timeout",
            ctx.output_format,
            ctx.pr,
        )


def _fail_gh(result: subprocess.CompletedProcess[str], ctx: _Context, what: str) -> NoReturn:
    """Map a failed gh call to the ADR-035 auth, not-found, or external exit."""
    text = f"{result.stdout or ''}\n{result.stderr or ''}"
    detail = sanitize_failure_detail(text)
    if is_auth_failure_text(text):
        _emit_error(
            f"Not authorized to {what} PR #{ctx.pr}: {detail}",
            4,
            "AuthError",
            ctx.output_format,
            ctx.pr,
        )
    if is_pr_not_found(text):
        _emit_error(
            f"PR #{ctx.pr} not found in {ctx.repo_flag}",
            2,
            "NotFound",
            ctx.output_format,
            ctx.pr,
        )
    _emit_error(
        f"Failed to {what} PR #{ctx.pr}: {detail}",
        3,
        "ApiError",
        ctx.output_format,
        ctx.pr,
    )


def _fetch_pr(ctx: _Context) -> _PrSnapshot:
    """Read state, draft flag, and head SHA; emit an envelope on failure."""
    result = _run_gh(
        [
            "gh",
            "pr",
            "view",
            str(ctx.pr),
            "--repo",
            ctx.repo_flag,
            "--json",
            "state,isDraft,headRefOid",
        ],
        ctx,
        "Reading PR state",
    )
    if result.returncode != 0:
        _fail_gh(result, ctx, "read")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict) or not isinstance(data.get("isDraft"), bool):
        _emit_error(
            f"PR #{ctx.pr} state response had no boolean isDraft field",
            3,
            "ApiError",
            ctx.output_format,
            ctx.pr,
        )
    return _PrSnapshot(
        state=str(data.get("state") or ""),
        is_draft=data["isDraft"],
        head_sha=str(data.get("headRefOid") or ""),
    )


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
    if args.expected_head_sha and not _SHA_PATTERN.match(args.expected_head_sha):
        _emit_error(
            "--expected-head-sha must be a 40-character hex commit SHA",
            1,
            "InvalidParams",
            args.output_format,
            args.pull_request,
        )


def _require_auth(fmt: str, pr: int) -> None:
    auth = check_gh_auth()
    if not auth.is_authenticated:
        message, code, error_type = describe_gh_auth_failure(auth)
        _emit_error(message, code, error_type, fmt, pr)


def _require_open(ctx: _Context, snap: _PrSnapshot) -> None:
    if snap.state != "OPEN":
        shown = snap.state.lower() or "in an unknown state"
        _emit_error(
            f"PR #{ctx.pr} is {shown}; only an open PR can change draft state",
            1,
            "InvalidParams",
            ctx.output_format,
            ctx.pr,
            state=snap.state or None,
        )


def _require_expected_head(ctx: _Context, snap: _PrSnapshot) -> None:
    """Refuse when the pin disagrees with the PR head."""
    if ctx.expected_head_sha and snap.head_sha.lower() != ctx.expected_head_sha.lower():
        _emit_error(
            f"PR #{ctx.pr} head moved: the PR head is {snap.head_sha or 'unknown'}, "
            f"not {ctx.expected_head_sha}. Re-read the head and retry.",
            1,
            "VerificationFailed",
            ctx.output_format,
            ctx.pr,
            reason="head_moved",
            expected_head_sha=ctx.expected_head_sha,
            current_head_sha=snap.head_sha or None,
        )


def _apply(ctx: _Context) -> None:
    """Run the mutation; the caller reads the PR back to confirm it took."""
    args = ["gh", "pr", "ready", str(ctx.pr), "--repo", ctx.repo_flag]
    if ctx.to_draft:
        args.append("--undo")
    result = _run_gh(args, ctx, f"Marking {ctx.target_label}")
    if result.returncode != 0:
        _fail_gh(result, ctx, f"mark {ctx.target_label}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _validate_args(args)
    _require_auth(args.output_format, args.pull_request)
    resolved = resolve_repo_params(args.owner, args.repo)
    ctx = _Context(
        pr=args.pull_request,
        repo_flag=f"{resolved.owner}/{resolved.repo}",
        expected_head_sha=args.expected_head_sha,
        to_draft=args.draft,
        output_format=args.output_format,
    )

    snap = _fetch_pr(ctx)
    _require_open(ctx, snap)
    _require_expected_head(ctx, snap)

    if snap.is_draft == ctx.to_draft:
        data: dict[str, Any] = {
            "action": "none",
            "is_draft": snap.is_draft,
            "head_sha": snap.head_sha,
            "message": f"PR is already {ctx.target_label}",
        }
        if args.dry_run:
            data["dry_run"] = True
        return _emit_result(ctx, data, f"PR #{ctx.pr} is already {ctx.target_label}")

    if args.dry_run:
        data = {
            "action": "would_convert_to_draft" if ctx.to_draft else "would_mark_ready",
            "dry_run": True,
            "is_draft": snap.is_draft,
            "head_sha": snap.head_sha,
            "message": f"Dry run: PR not marked {ctx.target_label}",
        }
        return _emit_result(
            ctx, data, f"Dry run: PR #{ctx.pr} would become {ctx.target_label}; nothing changed"
        )

    _apply(ctx)
    after = _fetch_pr(ctx)
    if after.is_draft != ctx.to_draft:
        _emit_error(
            f"gh reported success but PR #{ctx.pr} is still "
            f"{'draft' if after.is_draft else 'ready'}; outcome unverified",
            3,
            "ApiError",
            ctx.output_format,
            ctx.pr,
            is_draft=after.is_draft,
        )
    data = {
        "action": "converted_to_draft" if ctx.to_draft else "marked_ready",
        "is_draft": after.is_draft,
        "head_sha": after.head_sha,
        "message": f"PR marked {ctx.target_label}",
    }
    return _emit_result(ctx, data, f"PR #{ctx.pr} is now {ctx.target_label}")


if __name__ == "__main__":
    raise SystemExit(main())

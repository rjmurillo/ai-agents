#!/usr/bin/env python3
"""Reopen a closed GitHub Pull Request with an optional comment.

Reopens the PR with ``gh pr reopen``, the counterpart of ``close_pr.py``. A
reopen fires the ``reopened`` pull_request event, which is how the close and
reopen recovery in ``fix-ci.md`` re-runs workflows that never reported.

Behavior:
- A PR that is already OPEN is success with ``action: none`` (idempotent).
- A MERGED PR, or one in an unknown state, cannot be reopened and exits 1.
- A CLOSED PR is reopened. ``--comment`` is posted with the reopen in one call.

Output uses the standard skill envelope (ADR-056). Exit codes follow ADR-035:
    0 - Success (reopened, or already open)
    1 - Invalid parameters / logic error (PR is merged or in an unknown state)
    2 - Not found
    3 - External error (API failure, timeout, head branch deleted)
    4 - Auth error
"""

from __future__ import annotations

import argparse
import json
import os
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

_SCRIPT_NAME = "reopen_pr.py"
_GH_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class _Context:
    pr: int
    repo_flag: str
    output_format: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reopen a closed GitHub Pull Request with an optional comment.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--pull-request",
        type=int,
        required=True,
        help="Pull request number",
    )
    parser.add_argument("--comment", default="", help="Comment to post with the reopen")
    add_output_format_arg(parser)
    return parser


def _emit_error(
    message: str,
    code: int,
    error_type: str,
    fmt: str,
    pr: int,
    **extra: Any,
) -> NoReturn:
    """Emit the error envelope, then exit with ``code``."""
    write_skill_error(
        message,
        code,
        error_type=error_type,
        output_format=fmt,
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


def _fail_text(result: subprocess.CompletedProcess[str]) -> str:
    return f"{result.stdout or ''}\n{result.stderr or ''}"


def _fail_gh(result: subprocess.CompletedProcess[str], ctx: _Context, what: str) -> NoReturn:
    """Map a failed gh call to the ADR-035 code: 4 auth, 2 missing PR, else 3."""
    text = _fail_text(result)
    detail = sanitize_failure_detail(text)
    if is_auth_failure_text(text):
        _emit_error(f"{what} not authorized: {detail}", 4, "AuthError", ctx.output_format, ctx.pr)
    if is_pr_not_found(text):
        _emit_error(
            f"PR #{ctx.pr} not found in {ctx.repo_flag}",
            2,
            "NotFound",
            ctx.output_format,
            ctx.pr,
        )
    _emit_error(f"{what} failed: {detail}", 3, "ApiError", ctx.output_format, ctx.pr)


def _require_auth(fmt: str, pr: int) -> None:
    auth = check_gh_auth()
    if not auth.is_authenticated:
        message, code, error_type = describe_gh_auth_failure(auth)
        _emit_error(message, code, error_type, fmt, pr)


def _fetch_state(ctx: _Context) -> str:
    """Read the PR state; emit an envelope on failure."""
    result = _run_gh(
        ["gh", "pr", "view", str(ctx.pr), "--repo", ctx.repo_flag, "--json", "state"],
        ctx,
        "Reading PR state",
    )
    if result.returncode != 0:
        _fail_gh(result, ctx, "Reading PR state")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict):
        _emit_error(
            f"PR #{ctx.pr} state response was not a JSON object",
            3,
            "ApiError",
            ctx.output_format,
            ctx.pr,
        )
    return str(data.get("state") or "")


def _emit_result(ctx: _Context, data: dict[str, Any], summary: str) -> int:
    write_skill_output(
        {"pull_request": ctx.pr, **data},
        output_format=ctx.output_format,
        human_summary=summary,
        status="PASS",
        script_name=_SCRIPT_NAME,
    )
    return 0


def _reopen(ctx: _Context, comment: str) -> None:
    command = ["gh", "pr", "reopen", str(ctx.pr), "--repo", ctx.repo_flag]
    if comment:
        command += ["--comment", comment]
    result = _run_gh(command, ctx, "Reopening PR")
    if result.returncode != 0:
        _fail_gh(result, ctx, "Reopening PR")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _require_auth(args.output_format, args.pull_request)
    resolved = resolve_repo_params(args.owner, args.repo)
    ctx = _Context(
        pr=args.pull_request,
        repo_flag=f"{resolved.owner}/{resolved.repo}",
        output_format=args.output_format,
    )

    state = _fetch_state(ctx)
    if state == "OPEN":
        return _emit_result(
            ctx,
            {"state": "OPEN", "action": "none", "message": "PR already open"},
            f"PR #{ctx.pr} already open",
        )
    if state != "CLOSED":
        shown = state.lower() or "in an unknown state"
        _emit_error(
            f"PR #{ctx.pr} is {shown}; only a closed PR can be reopened",
            1,
            "InvalidParams",
            ctx.output_format,
            ctx.pr,
            state=state or None,
        )

    _reopen(ctx, args.comment)
    return _emit_result(
        ctx,
        {"state": "OPEN", "action": "reopened", "message": "PR reopened successfully"},
        f"Reopened PR #{ctx.pr}",
    )


if __name__ == "__main__":
    raise SystemExit(main())

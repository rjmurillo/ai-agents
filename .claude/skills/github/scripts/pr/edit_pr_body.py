#!/usr/bin/env python3
"""Edit a pull request body with a stale-write guard.

Reads the current body, checks its SHA-256 hash against an expected value
(when provided), and only writes if the body changed. This detects edits made
between the caller's hash capture and this script's read. GitHub rejects
conditional headers on this PATCH endpoint, so it cannot prevent an edit made
between that read and the update request.

Safety behavior:
  - Rejects a body whose hash no longer matches the caller's expected hash.
  - No-ops when the new body is identical to the current body.
  - Warns when the resulting body contains em/en dashes, including retained
    bytes that were already present in the current body.
  - Warns when one closing keyword has multiple bare issue references. GitHub
    requires the full keyword syntax for each target.

Exit codes follow ADR-035:
    0 - Success (or no-op)
    1 - Logic or validation error, including a stale write
    2 - Usage, configuration, or not-found error
    3 - External service or API error
    4 - Auth error
"""

from __future__ import annotations

import argparse
import hashlib
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
    sys.exit(2)
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

_SCRIPT_NAME = "edit_pr_body.py"

# Prohibited characters: em dash (U+2014) and en dash (U+2013).
_DASH_RE = re.compile(r"[\u2013\u2014]")

_CLOSING_MULTI_RE = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+"
    r"#\d+(?:(?:[ \t]+|[ \t]*,[ \t]*|[ \t]+and[ \t]+)#\d+)+",
    re.IGNORECASE,
)


def body_hash(body: str) -> str:
    """Return SHA-256 hex of the body text (LF-normalised)."""
    normalised = body.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def validate_body(new_body: str) -> list[str]:
    """Return a list of validation warnings for the new body."""
    warnings: list[str] = []

    if _DASH_RE.search(new_body):
        positions = [m.start() for m in _DASH_RE.finditer(new_body)]
        warnings.append(
            f"Body contains em/en dash at position(s) {positions}; "
            "bot reviewers flag each occurrence"
        )

    for m in _CLOSING_MULTI_RE.finditer(new_body):
        warnings.append(
            f"Multiple bare issue references after one closing keyword: "
            f"'{m.group(0)}' - repeat the keyword for each target"
        )

    return warnings


def fetch_current_body(owner: str, repo: str, pr: int) -> str | None:
    """Return the current PR body, or None if not found."""
    result = subprocess.run(
        [
            "gh", "api",
            f"repos/{owner}/{repo}/pulls/{pr}",
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        if "404" in result.stderr or "Not Found" in result.stderr:
            return None
        # gh can exit non-zero with blank stderr (a signal kill, or a
        # failure mode that writes to stdout instead), in which case
        # result.stderr.strip() is "". Uncaught, str(RuntimeError(""))
        # is also "", and write_skill_error's caller-side guard
        # (ADR-103 Round 5) rejects an empty message with ValueError,
        # turning this external gh failure into an unhandled crash with
        # exit code 1 instead of the intended exit code 3 (adr-review
        # independent-thinker seat, ADR-103 Round 5 convergence check).
        # The "or" fallback mirrors the pattern already used in
        # claim_issue.py and check_existing_pr_for_issue.py in this
        # same skill directory.
        raise RuntimeError(
            result.stderr.strip() or f"gh api pulls/{pr} failed with no stderr output"
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to decode PR response: {exc}") from exc
    return payload.get("body") or ""


def update_body(owner: str, repo: str, pr: int, new_body: str) -> None:
    """Write the new body via the gh CLI."""
    result = subprocess.run(
        [
            "gh", "api",
            f"repos/{owner}/{repo}/pulls/{pr}",
            "--method", "PATCH",
            "--input", "-",
            "--jq", ".number",
        ],
        input=json.dumps({"body": new_body}),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        # See the matching comment in fetch_current_body above: an empty
        # stderr must not produce an empty RuntimeError message, or the
        # write_skill_error caller below crashes uncaught instead of
        # emitting an error envelope with exit code 3.
        raise RuntimeError(
            result.stderr.strip()
            or f"gh api pulls/{pr} PATCH failed with no stderr output"
        )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Edit a PR body with a stale-write guard.",
    )
    p.add_argument("--owner", default="")
    p.add_argument("--repo", default="")
    p.add_argument("--pull-request", type=int, required=True)
    body_group = p.add_mutually_exclusive_group(required=True)
    body_group.add_argument("--body", default=None, help="New body text")
    body_group.add_argument(
        "--body-file", default=None, help="Path to file containing new body",
    )
    p.add_argument(
        "--expected-hash", default="",
        help=(
            "SHA-256 hex of the current body (LF-normalised). "
            "When provided and the current body does not match, the edit "
            "is aborted (exit 1) to prevent clobbering a concurrent edit."
        ),
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be written without actually writing",
    )
    add_output_format_arg(p)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fmt = get_output_format(args.output_format)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo
    pr = args.pull_request

    if args.body_file:
        try:
            with open(args.body_file, encoding="utf-8") as f:
                new_body = f.read()
        except OSError as exc:
            write_skill_error(
                f"Cannot read --body-file: {exc}", 2, error_type="NotFound",
                output_format=fmt, script_name=_SCRIPT_NAME,
            )
            return 2
    else:
        new_body = args.body or ""

    try:
        current_body = fetch_current_body(owner, repo, pr)
    except (RuntimeError, subprocess.SubprocessError, OSError) as exc:
        write_skill_error(
            str(exc), 3, error_type="ApiError",
            output_format=fmt, script_name=_SCRIPT_NAME,
        )
        return 3

    if current_body is None:
        write_skill_error(
            f"PR #{pr} not found", 2, error_type="NotFound",
            output_format=fmt, script_name=_SCRIPT_NAME,
        )
        return 2

    current_hash = body_hash(current_body)

    # Stale-write guard: abort if the current body has changed since capture.
    if args.expected_hash and args.expected_hash != current_hash:
        write_skill_error(
            f"PR #{pr} body hash mismatch: expected {args.expected_hash[:12]}... "
            f"but current is {current_hash[:12]}...; concurrent edit detected, aborting",
            1,
            error_type="VerificationFailed",
            output_format=fmt,
            script_name=_SCRIPT_NAME,
            extra={
                "pull_request": pr,
                "expected_hash": args.expected_hash,
                "current_hash": current_hash,
            },
        )
        return 1

    # No-op when body is unchanged.
    new_hash = body_hash(new_body)
    if new_hash == current_hash:
        write_skill_output(
            {
                "Success": True,
                "pull_request": pr,
                "action": "no-op",
                "current_hash": current_hash,
                "message": "Body unchanged; no write needed",
            },
            output_format=fmt,
            human_summary=f"PR #{pr}: body unchanged, no write",
            status="PASS",
            script_name=_SCRIPT_NAME,
        )
        return 0

    warnings = validate_body(new_body)

    if args.dry_run:
        write_skill_output(
            {
                "Success": True,
                "pull_request": pr,
                "action": "dry-run",
                "new_hash": new_hash,
                "warnings": warnings,
                "new_body_preview": new_body[:200],
            },
            output_format=fmt,
            human_summary=f"PR #{pr}: dry-run (would write {len(new_body)} chars)",
            status="PASS",
            script_name=_SCRIPT_NAME,
        )
        return 0

    try:
        update_body(owner, repo, pr, new_body)
    except (RuntimeError, subprocess.SubprocessError, OSError) as exc:
        write_skill_error(
            str(exc), 3, error_type="ApiError",
            output_format=fmt, script_name=_SCRIPT_NAME,
        )
        return 3

    write_skill_output(
        {
            "Success": True,
            "pull_request": pr,
            "action": "updated",
            "previous_hash": current_hash,
            "new_hash": new_hash,
            "warnings": warnings,
        },
        output_format=fmt,
        human_summary=f"PR #{pr}: body updated ({len(warnings)} warning(s))",
        status="PASS",
        script_name=_SCRIPT_NAME,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

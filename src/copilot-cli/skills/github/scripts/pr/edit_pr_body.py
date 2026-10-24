#!/usr/bin/env python3
"""Edit a pull request body with a stale-write guard.

Reads the current body, checks its SHA-256 hash against an expected value
(when provided), and only writes if the body changed. This detects edits made
between the caller's hash capture and this script's read. GitHub rejects
conditional headers on this PATCH endpoint, so it cannot prevent an edit made
between that read and the update request.

Safety behavior:
  - Reads --body-file through the shared body-file containment rule
    (``github_core.validation.read_body_file_text``), the same rule that
    ``close_issue.py`` and ``post_issue_comment.py`` apply: the path must
    resolve under the repo root, a temp directory, or the git dir. A session
    scratchpad passes. Relative paths resolve against the repo root. The file
    is opened with O_NOFOLLOW, must be a regular file, and is refused while it
    still holds the placeholder line that ``new_pr.py --prepare-body-file``
    seeds. Prefer a unique name per caller: concurrent sessions that share a
    fixed name such as body.md can publish each other's text, and
    ``--prepare-body-file`` hands each caller a unique random name.
  - Rejects a body whose hash differs from the caller's expected hash.
  - No-ops when the new body equals the current body.
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
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

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
from github_core.not_found import is_pr_not_found
from github_core.output import (
    add_output_format_arg,
    get_output_format,
    write_skill_error,
    write_skill_output,
)
from github_core.repo import get_repo_root
from github_core.validation import read_body_file_text


def _load_prepare_module():
    """Load prepare_pr_body.py beside this script.

    Loaded by path, not by name, so the bundle works under ``python -I`` and a
    same-named module on sys.path cannot replace it. The alias is private so it
    does not collide with the one new_pr.py registers.
    """
    path = Path(__file__).resolve().with_name("prepare_pr_body.py")
    spec = importlib.util.spec_from_file_location("_edit_pr_body_prepare", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"cannot load required sibling module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_prepare = _load_prepare_module()
PreparePrBodyError = _prepare.PreparePrBodyError
reject_unreplaced_placeholder = _prepare.reject_unreplaced_placeholder

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


def hash_matches(expected: str, current_body: str) -> bool:
    """Return True when ``expected`` hashes the current body, ignoring one extra newline.

    A caller that captures the body with
    ``gh pr view <n> --json body --jq .body > f`` gets a
    file with one extra trailing newline, so its hash never equals the hash of
    the API body. Accept the exact body, the body plus one newline (the
    redirection case), and the body with trailing newlines removed.
    """
    accepted = {
        body_hash(current_body),
        body_hash(current_body + "\n"),
        body_hash(current_body.rstrip("\r\n")),
    }
    return expected in accepted


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
            "gh",
            "api",
            f"repos/{owner}/{repo}/pulls/{pr}",
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        if is_pr_not_found(result.stderr):
            return None
        # gh can exit non-zero with blank stderr (a signal kill, or a
        # failure mode that writes its diagnostic to stdout instead), in
        # which case result.stderr.strip() is "". Uncaught, that empty
        # string reaches write_skill_error's caller-side guard (ADR-103
        # Round 5), which rejects an empty message with ValueError,
        # turning this external gh failure into an unhandled crash with
        # exit code 1 instead of the intended exit code 3 (adr-review
        # independent-thinker seat, ADR-103 Round 5 convergence check).
        # Falling back to stdout before the generic message preserves
        # gh's actual diagnostic when it lands there instead of stderr;
        # this three-way fallback mirrors
        # get_pr_reviews.py:138, get_pr_reviewers.py:333,
        # check_suppressed_review_findings.py:122,134, and
        # get_thread_conversation_history.py:116, all in this same
        # skill/pr/ directory (Copilot review on PR #5283, correcting
        # an earlier version of this comment that cited a two-way
        # stderr-or-literal fallback in skill/issue/claim_issue.py,
        # a different directory whose pattern this one now improves on).
        raise RuntimeError(
            result.stderr.strip()
            or result.stdout.strip()
            or f"gh api pulls/{pr} failed with no stderr or stdout output"
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
            "gh",
            "api",
            f"repos/{owner}/{repo}/pulls/{pr}",
            "--method",
            "PATCH",
            "--input",
            "-",
            "--jq",
            ".number",
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
        # emitting an error envelope with exit code 3. Fall back to
        # stdout before the generic message for the same reason (gh can
        # write its diagnostic there instead of stderr).
        raise RuntimeError(
            result.stderr.strip()
            or result.stdout.strip()
            or f"gh api pulls/{pr} PATCH failed with no stderr or stdout output"
        )


def _read_new_body(args: argparse.Namespace) -> tuple[str, str | None]:
    """Return ``(body, error)``; ``--body-file`` follows the shared containment rule."""
    if not args.body_file:
        return args.body or "", None
    # A relative path resolves against the repo root when git can name one,
    # else against the working directory. An absolute path needs no root.
    root = get_repo_root()
    try:
        body = read_body_file_text(args.body_file, root)
        reject_unreplaced_placeholder(body)
    except (OSError, ValueError, PreparePrBodyError) as exc:
        return "", f"Invalid --body-file: {exc}"
    return body, None


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
        "--body-file",
        default=None,
        help=(
            "Path to a file holding the new body. It must resolve under the "
            "repo root, a temp directory, or the git dir, the same rule the "
            "other body-file scripts use. A path printed by new_pr.py "
            "--prepare-body-file works and avoids name collisions between "
            "concurrent sessions."
        ),
    )
    p.add_argument(
        "--expected-hash",
        default="",
        help=(
            "SHA-256 hex of the current body (LF-normalised; one extra "
            "trailing newline is ignored, so hashing a file saved with "
            "`gh pr view <n> --json body --jq .body > f` works when the "
            "body has LF line endings; convert CRLF to LF first). "
            "When provided and the current body does not match, the edit "
            "is aborted (exit 1) to prevent clobbering a concurrent edit."
        ),
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
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

    new_body, read_error = _read_new_body(args)
    if read_error is not None:
        write_skill_error(
            read_error,
            2,
            error_type="InvalidParams",
            output_format=fmt,
            script_name=_SCRIPT_NAME,
        )
        return 2

    try:
        current_body = fetch_current_body(owner, repo, pr)
    except (RuntimeError, subprocess.SubprocessError, OSError) as exc:
        write_skill_error(
            str(exc),
            3,
            error_type="ApiError",
            output_format=fmt,
            script_name=_SCRIPT_NAME,
        )
        return 3

    if current_body is None:
        write_skill_error(
            f"PR #{pr} not found",
            2,
            error_type="NotFound",
            output_format=fmt,
            script_name=_SCRIPT_NAME,
        )
        return 2

    current_hash = body_hash(current_body)

    # Stale-write guard: abort if the current body has changed since capture.
    if args.expected_hash and not hash_matches(args.expected_hash, current_body):
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
            str(exc),
            3,
            error_type="ApiError",
            output_format=fmt,
            script_name=_SCRIPT_NAME,
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

#!/usr/bin/env python3
"""Close a GitHub Issue with an optional closing comment.

Closes the issue via ``gh issue close --reason`` and posts an optional comment
from ``--comment`` or ``--comment-file``. On retry, an already-closed issue can
still receive a missing closing comment without duplicating an existing one.
Emits the standard ADR-056 skill output envelope ({Success, Data, Error,
Metadata}).

Exit codes follow ADR-035:
    0 - Success (issue closed, or already closed)
    1 - Invalid parameters / logic error
    2 - File not found / config error
    3 - External error (API failure)
    4 - Auth error (not authenticated)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

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
    sys.exit(2)  # Config error per ADR-035
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (  # noqa: E402
    assert_gh_authenticated,
    resolve_repo_params,
)
from github_core.output import (  # noqa: E402
    add_output_format_arg,
    get_output_format,
    write_skill_error,
    write_skill_output,
)

# gh issue close --reason accepts exactly these two values. "not planned" is the
# spelling gh expects (with a space), so we pass the value through verbatim.
_VALID_REASONS = ("completed", "not planned")
_AUTH_ERROR_MARKERS = (
    "credential",
    "not logged in",
    "bad credentials",
    "could not authenticate",
    "authentication",
    "requires authentication",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Close a GitHub Issue with an optional closing comment.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument("--issue", type=int, required=True, help="Issue number")
    parser.add_argument(
        "--reason",
        choices=list(_VALID_REASONS),
        default="completed",
        help="Close reason: 'completed' (default) or 'not planned'.",
    )

    comment_group = parser.add_mutually_exclusive_group()
    comment_group.add_argument(
        "--comment", default="", help="Closing comment body text",
    )
    comment_group.add_argument(
        "--comment-file", default="", help="Path to a file containing the comment body",
    )

    parser.add_argument(
        "--verify-claims",
        action="store_true",
        help=(
            "Before closing, scan the closing comment for cited commit SHAs "
            "and PR numbers and abort the close (exit code 1) when any cited "
            "commit does not exist or any cited PR is not merged. "
            "Prevents 'resolved by commit X' close comments that name a "
            "phantom commit or an unmerged PR (issue #2481)."
        ),
    )

    add_output_format_arg(parser)
    return parser


# ---------------------------------------------------------------------------
# Claim extraction + verification (issue #2481 gate)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Claims:
    """Commit SHAs and PR numbers cited in a closing comment.

    A "claim" is an artifact the comment says resolves the issue. The
    verifier asserts each claim exists on the remote before we let the
    close go through.
    """

    commits: tuple[str, ...]
    prs: tuple[int, ...]


@dataclass(frozen=True)
class VerificationResult:
    """Outcome of probing each cited claim. Empty failures = clean."""

    failures: tuple[str, ...]


# A 7-to-40 char hex token after a "commit" mention is treated as a SHA.
# Anchored to "commit\s+" so unrelated 7-char hex words are ignored.
_COMMIT_PATTERN = re.compile(
    r"\bcommit\s+([0-9a-f]{7,40})\b",
    re.IGNORECASE,
)

# A PR claim is any "PR #N" token in the comment body. Closing comments are
# already scoped to a resolution context, so any cited PR is implicitly being
# claimed as the resolver. This intentionally ignores bare "#N" tokens (which
# also reference unrelated context like the issue's own number or sibling
# issues) and "Closes #N" trailers (which point at the issue being closed,
# not at the fix source).
_PR_PATTERN = re.compile(
    r"\bPR\s*#(\d+)\b",
    re.IGNORECASE,
)


def extract_claims(comment_body: str) -> Claims:
    """Pull commit SHAs and PR numbers cited as resolving the issue.

    Returns a Claims tuple preserving first-seen order with duplicates
    removed. The matcher is intentionally narrow: it only recognizes the
    "resolved by commit X" / "fixed in PR #N" shape the bot's prior close
    comments used (issue #2481 audit). Comments that name no artifact
    return empty tuples and pass the gate trivially.
    """
    if not comment_body:
        return Claims(commits=(), prs=())

    seen_commits: list[str] = []
    for match in _COMMIT_PATTERN.finditer(comment_body):
        sha = match.group(1).lower()
        if sha not in seen_commits:
            seen_commits.append(sha)

    seen_prs: list[int] = []
    for match in _PR_PATTERN.finditer(comment_body):
        number = int(match.group(1))
        if number not in seen_prs:
            seen_prs.append(number)

    return Claims(commits=tuple(seen_commits), prs=tuple(seen_prs))


def _commit_exists(owner: str, repo: str, sha: str) -> bool:
    """Return True when ``gh api repos/<o>/<r>/commits/<sha>`` resolves."""
    result = subprocess.run(
        [
            "gh", "api",
            f"repos/{owner}/{repo}/commits/{sha}",
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    return result.returncode == 0


def _pr_is_merged(owner: str, repo: str, number: int) -> bool:
    """Return True when PR #N is closed AND merged on the remote."""
    result = subprocess.run(
        [
            "gh", "api",
            f"repos/{owner}/{repo}/pulls/{number}",
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        return False
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return False
    return isinstance(payload, dict) and payload.get("merged") is True


def verify_claims(claims: Claims, *, owner: str, repo: str) -> VerificationResult:
    """Probe each claim against the remote and return any failures.

    Each cited commit must resolve via the GitHub commits API; each cited
    PR must be merged (state=closed, merged=true). Failures collect into a
    list so a single close attempt that cites multiple bad claims surfaces
    every one of them, not just the first.
    """
    failures: list[str] = []
    for sha in claims.commits:
        if not _commit_exists(owner, repo, sha):
            failures.append(
                f"cited commit {sha} does not exist on {owner}/{repo}"
            )
    for pr_number in claims.prs:
        if not _pr_is_merged(owner, repo, pr_number):
            failures.append(
                f"cited PR #{pr_number} is not merged on {owner}/{repo}"
            )
    return VerificationResult(failures=tuple(failures))


def _comment_base_dir() -> Path:
    """Return the directory that comment files must stay under."""
    workspace = os.environ.get("GITHUB_WORKSPACE", "").strip()
    if workspace:
        return Path(workspace).expanduser().resolve()
    for parent in Path(__file__).resolve().parents:
        if (parent / ".git").exists():
            return parent
    return Path(__file__).resolve().parent


def _resolve_comment_file(comment_file: str, fmt: str) -> Path:
    base_dir = _comment_base_dir()
    raw_path = Path(comment_file)
    path = raw_path if raw_path.is_absolute() else base_dir / raw_path
    resolved = path.resolve()
    if not resolved.is_relative_to(base_dir):
        write_skill_error(
            f"Comment file must stay under {base_dir}: {comment_file}",
            2,
            error_type="InvalidParams",
            output_format=fmt,
            script_name="close_issue.py",
            extra={"issue": None},
        )
        raise SystemExit(2)
    if not resolved.is_file():
        write_skill_error(
            f"Comment file not found: {comment_file}",
            2,
            error_type="NotFound",
            output_format=fmt,
            script_name="close_issue.py",
            extra={"issue": None},
        )
        raise SystemExit(2)
    return resolved


def _resolve_comment(comment: str, comment_file: str, fmt: str) -> str:
    """Return the closing comment body, reading the file when one is given.

    Exits with code 2 (config error) when the comment file is missing. Returns
    an empty string when no comment was requested.
    """
    if comment_file:
        path = _resolve_comment_file(comment_file, fmt)
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            write_skill_error(
                f"Failed to read comment file {comment_file}: {exc}",
                2,
                error_type="InvalidParams",
                output_format=fmt,
                script_name="close_issue.py",
                extra={"issue": None},
            )
            raise SystemExit(2) from exc
    return comment


def _is_auth_error(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in _AUTH_ERROR_MARKERS)


def _write_subprocess_error(
    message: str, issue: int, fmt: str, *, not_found: bool = False
) -> int:
    if not_found:
        code = 2
        error_type = "NotFound"
    elif _is_auth_error(message):
        code = 4
        error_type = "AuthError"
    else:
        code = 3
        error_type = "ApiError"
    write_skill_error(
        message,
        code,
        error_type=error_type,
        output_format=fmt,
        script_name="close_issue.py",
        extra={"issue": issue},
    )
    return code


def _get_issue_state(owner: str, repo: str, issue: int, fmt: str) -> str:
    """Return the issue state from GitHub, lowercased."""
    result = subprocess.run(
        [
            "gh", "issue", "view", str(issue),
            "--repo", f"{owner}/{repo}",
            "--json", "state",
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        error_str = result.stderr.strip() or result.stdout.strip()
        code = _write_subprocess_error(
            f"Failed to get issue #{issue}: {error_str}",
            issue,
            fmt,
            not_found=(
                "Could not resolve" in error_str
                or "not found" in error_str.lower()
            ),
        )
        raise SystemExit(code)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        write_skill_error(
            f"Failed to parse issue #{issue} state: {exc}",
            3,
            error_type="ApiError",
            output_format=fmt,
            script_name="close_issue.py",
            extra={"issue": issue},
        )
        raise SystemExit(3) from exc
    if not isinstance(payload, dict):
        return ""
    state = payload.get("state")
    return "" if state is None else str(state).lower()


def _post_comment(owner: str, repo: str, issue: int, body: str, fmt: str) -> None:
    """Post a closing comment via gh api. Exits with code 3 on failure."""
    payload = json.dumps({"body": body})
    result = subprocess.run(
        [
            "gh", "api",
            f"repos/{owner}/{repo}/issues/{issue}/comments",
            "-X", "POST",
            "--input", "-",
        ],
        input=payload,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        error_str = result.stderr.strip() or result.stdout.strip()
        code = _write_subprocess_error(
            f"Failed to post closing comment: {error_str}",
            issue,
            fmt,
        )
        raise SystemExit(code)


def _comment_bodies(payload: object) -> list[str]:
    if isinstance(payload, dict):
        return _comment_bodies(payload.get("comments"))
    if not isinstance(payload, list):
        return []
    bodies: list[str] = []
    for item in payload:
        if isinstance(item, list):
            bodies.extend(_comment_bodies(item))
        elif isinstance(item, dict) and isinstance(item.get("body"), str):
            bodies.append(item["body"])
    return bodies


def _comment_exists(owner: str, repo: str, issue: int, body: str, fmt: str) -> bool:
    result = subprocess.run(
        [
            "gh", "api",
            f"repos/{owner}/{repo}/issues/{issue}/comments?per_page=100",
            "--paginate",
            "--slurp",
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        error_str = result.stderr.strip() or result.stdout.strip()
        code = _write_subprocess_error(
            f"Failed to inspect issue #{issue} comments: {error_str}",
            issue,
            fmt,
        )
        raise SystemExit(code)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        write_skill_error(
            f"Failed to parse issue #{issue} comments: {exc}",
            3,
            error_type="ApiError",
            output_format=fmt,
            script_name="close_issue.py",
            extra={"issue": issue},
        )
        raise SystemExit(3) from exc
    return body in _comment_bodies(payload)


def _close_issue(owner: str, repo: str, issue: int, reason: str) -> subprocess.CompletedProcess[str]:
    """Run gh issue close with the given reason. Returns the completed process."""
    return subprocess.run(
        [
            "gh", "issue", "close", str(issue),
            "--repo", f"{owner}/{repo}",
            "--reason", reason,
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fmt = get_output_format(args.output_format)
    body = _resolve_comment(args.comment, args.comment_file, fmt)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo
    issue: int = args.issue

    state = _get_issue_state(owner, repo, issue, fmt)
    if state == "closed":
        commented = False
        comment_already_present = False
        if body and body.strip():
            comment_already_present = _comment_exists(owner, repo, issue, body, fmt)
            if not comment_already_present:
                _post_comment(owner, repo, issue, body, fmt)
                commented = True
        data = {
            "issue": issue,
            "owner": owner,
            "repo": repo,
            "state": "closed",
            "reason": args.reason,
            "commented": commented,
            "commentAlreadyPresent": comment_already_present,
            "action": "already_closed",
        }
        write_skill_output(
            data,
            output_format=fmt,
            human_summary=f"Issue #{issue} is already closed",
            status="PASS",
            script_name="close_issue.py",
        )
        return 0

    # Verify any cited commit / PR claims BEFORE we run the close; a bad
    # claim aborts the entire operation so the bot cannot post "resolved by
    # commit X" when X does not exist (issue #2481).
    if args.verify_claims and body and body.strip():
        claims = extract_claims(body)
        verification = verify_claims(claims, owner=owner, repo=repo)
        if verification.failures:
            message = (
                "Closing comment cites unverifiable artifact(s); aborting "
                "close. " + "; ".join(verification.failures)
            )
            write_skill_error(
                message,
                1,
                error_type="VerificationFailed",
                output_format=fmt,
                script_name="close_issue.py",
                extra={
                    "issue": issue,
                    "claims": {
                        "commits": list(claims.commits),
                        "prs": list(claims.prs),
                    },
                    "failures": list(verification.failures),
                },
            )
            return 1

    result = _close_issue(owner, repo, issue, args.reason)
    if result.returncode != 0:
        error_str = result.stderr.strip() or result.stdout.strip()
        code = _write_subprocess_error(
            f"Failed to close issue #{issue}: {error_str}",
            issue,
            fmt,
        )
        return code

    commented = bool(body and body.strip())
    if commented:
        _post_comment(owner, repo, issue, body, fmt)

    data = {
        "issue": issue,
        "owner": owner,
        "repo": repo,
        "state": "closed",
        "reason": args.reason,
        "commented": commented,
        "action": "closed",
    }
    write_skill_output(
        data,
        output_format=fmt,
        human_summary=f"Closed issue #{issue} as '{args.reason}'",
        status="PASS",
        script_name="close_issue.py",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

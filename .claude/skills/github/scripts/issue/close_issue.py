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

``--verify-claims`` splits those last three deliberately (issue #4951). A
cited artifact that the remote *reports* as bad (a commit GitHub answers 404
for, a PR GitHub reports as unmerged) is a logic failure: exit 1. A cited
artifact the remote never answered about (transport error, timeout, malformed
payload) is exit 3, and a credential fault is exit 4. Both abort the close,
neither is allowed to say "not merged", because a probe that did not run
proves nothing about a pull request.
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
    is_auth_failure_text,
    resolve_repo_params,
    sanitize_failure_detail,
)
from github_core.output import (
    add_output_format_arg,
    get_output_format,
    write_skill_error,
    write_skill_output,
)
from github_core.pr_merge_state import (
    PrMergeState,
    PrMergeStatus,
    read_pr_merge_state,
)

# gh issue close --reason accepts exactly these two values. "not planned" is the
# spelling gh expects (with a space), so we pass the value through verbatim.
_VALID_REASONS = ("completed", "not planned")


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
            "and PR numbers and abort the close when a cited artifact is "
            "verifiably bad (exit code 1) or cannot be verified at all "
            "(exit code 3 external, 4 auth). "
            "Prevents 'resolved by commit X' close comments that name a "
            "phantom commit or an unmerged PR (issue #2481), without turning "
            "a failed probe into a not-merged finding (issue #4951)."
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
class ClaimCheck:
    """One claim's probe outcome, in exactly one of three shapes.

    - Verified good: both message fields empty.
    - Verified bad: ``failure`` set. The remote answered and the answer
      condemns the claim (ADR-035 exit 1, a logic failure).
    - Unverifiable: ``probe_error`` set with ``exit_code`` 3 (external) or 4
      (auth). The remote did not answer, so the claim is neither confirmed nor
      condemned.

    The third shape is the one issue #4951 added. Folding it into the second
    is what let a failed REST probe be published as "cited PR #N is not
    merged" for two pull requests that were merged weeks earlier.
    """

    failure: str = ""
    probe_error: str = ""
    exit_code: int = 0


# A claim whose probe answered and cleared it.
_CLAIM_VERIFIED = ClaimCheck()


@dataclass(frozen=True)
class VerificationResult:
    """Outcome of probing each cited claim. Empty failures = clean.

    ``failures`` holds verified-bad claims (exit 1). ``probe_errors`` holds
    claims whose evidence could not be obtained (exit 3 or 4, carried in
    ``probe_exit_code``). Both abort the close.
    """

    failures: tuple[str, ...] = ()
    probe_errors: tuple[str, ...] = ()
    probe_exit_code: int = 0

    @property
    def blocked(self) -> bool:
        """True when the close must not proceed."""
        return bool(self.failures or self.probe_errors)

    @property
    def exit_code(self) -> int:
        """ADR-035 code for the whole verification pass.

        A probe failure outranks a verified-bad claim, and auth (4) outranks
        external (3). Rationale: an incomplete pass cannot be reported as a
        finished judgment, and a credential fault is the operator-actionable
        root cause when both appear. No detail is lost by the precedence: the
        error envelope carries ``failures`` and ``probeErrors`` in full.
        """
        if self.probe_errors:
            return self.probe_exit_code
        return 1 if self.failures else 0


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


def _probe_detail(result: subprocess.CompletedProcess[str]) -> str:
    """Return a sanitized, bounded reason from a failed gh invocation."""
    raw = result.stderr.strip() or result.stdout.strip()
    return sanitize_failure_detail(raw) or "gh produced no error output"


def _unverifiable(artifact: str, owner: str, repo: str, detail: str) -> ClaimCheck:
    """Build the "evidence not obtained" outcome for one claim."""
    return ClaimCheck(
        probe_error=(
            f"could not verify {artifact} on {owner}/{repo}: {detail}"
        ),
        exit_code=4 if is_auth_failure_text(detail) else 3,
    )


# gh renders a missing commit as "gh: Not Found (HTTP 404)" and the REST body
# for an unknown SHA as {"message": "No commit found for SHA: ..."}. Only these
# shapes prove the commit is absent; every other nonzero exit (5xx, timeout,
# refused connection, revoked token) proves nothing and must not be published
# as "does not exist" (issue #4951).
_COMMIT_ABSENT_SIGNATURE = re.compile(
    r"HTTP 404|not found|no commit found",
    re.IGNORECASE,
)


def _check_commit(owner: str, repo: str, sha: str) -> ClaimCheck:
    """Probe ``gh api repos/<o>/<r>/commits/<sha>`` for one cited commit."""
    try:
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
    except subprocess.TimeoutExpired as exc:
        # Uncaught this would end the process with Python's exit 1, the code
        # ADR-035 reserves for a verified logic failure.
        return _unverifiable(
            f"cited commit {sha}", owner, repo, sanitize_failure_detail(exc)
        )
    if result.returncode == 0:
        return _CLAIM_VERIFIED

    detail = _probe_detail(result)
    if _COMMIT_ABSENT_SIGNATURE.search(detail):
        return ClaimCheck(
            failure=f"cited commit {sha} does not exist on {owner}/{repo}"
        )
    return _unverifiable(f"cited commit {sha}", owner, repo, detail)


def _check_pr(owner: str, repo: str, number: int) -> ClaimCheck:
    """Probe one cited PR through the shared tri-state merge-state reader."""
    state: PrMergeState = read_pr_merge_state(owner, repo, number)
    if state.status is PrMergeStatus.MERGED:
        return _CLAIM_VERIFIED
    if state.status is PrMergeStatus.UNMERGED:
        observed = f" (state {state.state})" if state.state else ""
        return ClaimCheck(
            failure=f"cited PR #{number} is not merged on {owner}/{repo}{observed}"
        )
    if state.status is PrMergeStatus.NOT_FOUND:
        return ClaimCheck(
            failure=f"cited PR #{number} does not exist on {owner}/{repo}"
        )
    return ClaimCheck(
        probe_error=(
            f"could not verify cited PR #{number} on {owner}/{repo}: "
            f"{state.detail}"
        ),
        exit_code=state.exit_code,
    )


def verify_claims(claims: Claims, *, owner: str, repo: str) -> VerificationResult:
    """Probe each claim against the remote and return what it found.

    Each cited commit must resolve via the GitHub commits API; each cited PR
    must be merged. Results split three ways per claim (see
    :class:`ClaimCheck`), and both failure lists collect every claim rather
    than stopping at the first, so one close attempt surfaces every problem.
    """
    failures: list[str] = []
    probe_errors: list[str] = []
    probe_exit_code = 0

    checks = [_check_commit(owner, repo, sha) for sha in claims.commits]
    checks.extend(_check_pr(owner, repo, number) for number in claims.prs)
    for check in checks:
        if check.failure:
            failures.append(check.failure)
        if check.probe_error:
            probe_errors.append(check.probe_error)
            # Auth (4) outranks external (3); see VerificationResult.exit_code.
            probe_exit_code = max(probe_exit_code, check.exit_code)

    return VerificationResult(
        failures=tuple(failures),
        probe_errors=tuple(probe_errors),
        probe_exit_code=probe_exit_code,
    )


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


def _write_subprocess_error(
    message: str, issue: int, fmt: str, *, not_found: bool = False
) -> int:
    if not_found:
        code = 2
        error_type = "NotFound"
    elif is_auth_failure_text(message):
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


def _close_issue(
    owner: str, repo: str, issue: int, reason: str
) -> subprocess.CompletedProcess[str]:
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


def _write_verification_error(
    claims: Claims, verification: VerificationResult, issue: int, fmt: str
) -> int:
    """Emit the claim-verification error envelope and return its exit code.

    Two headlines, because the two outcomes are different facts. The exit-1
    headline is kept verbatim from the original #2481 gate so anything that
    greps for it (and the operator note in
    `.serena/memories/github-skill/issue-comment-file-must-live-inside-the-repo.md`)
    keeps matching. The exit-3/4 headline is deliberately unlike it: it must
    never be mistaken for a statement about an artifact's state.
    """
    code = verification.exit_code
    if verification.probe_errors:
        headline = (
            "Could not verify closing comment claim(s) against GitHub; "
            "aborting close without judging them."
        )
        error_type = "AuthError" if code == 4 else "ApiError"
    else:
        headline = "Closing comment cites unverifiable artifact(s); aborting close."
        error_type = "VerificationFailed"

    details = "; ".join((*verification.probe_errors, *verification.failures))
    write_skill_error(
        f"{headline} {details}",
        code,
        error_type=error_type,
        output_format=fmt,
        script_name="close_issue.py",
        extra={
            "issue": issue,
            "claims": {
                "commits": list(claims.commits),
                "prs": list(claims.prs),
            },
            "failures": list(verification.failures),
            "probeErrors": list(verification.probe_errors),
        },
    )
    return code


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
    # commit X" when X does not exist (issue #2481). An unverifiable claim
    # aborts it too, under a different exit code and a message that does not
    # pretend to know the artifact's state (issue #4951).
    if args.verify_claims and body and body.strip():
        claims = extract_claims(body)
        verification = verify_claims(claims, owner=owner, repo=repo)
        if verification.blocked:
            return _write_verification_error(claims, verification, issue, fmt)

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

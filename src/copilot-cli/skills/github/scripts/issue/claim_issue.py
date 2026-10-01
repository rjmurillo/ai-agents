#!/usr/bin/env python3
"""Claim an issue by self-assigning, refusing if already claimed (issue #2477).

Pre-flight coordination for the competing-PR failure mode: a worker claims an
issue before starting development. If another login already holds the issue, the
claim is refused so two workers do not develop the same issue in parallel.

The assignee check is a cooperative signal: it only works when every worker
assigns itself first. A pushed branch is evidence, so a successful claim also
probes ``git ls-remote --heads origin`` for branches that name the issue, are
ahead of the origin default branch, and were not merged through a pull request.
Those are reported in ``in_flight_branches`` as a warning, never a refusal, so a
worker resuming its own branch is not blocked (issue #5428). A failed probe
degrades to a named ``warnings`` entry.

Exit codes follow ADR-035:
    0 - Claimed (now assigned to the current user) or already held by current user
    1 - Already claimed by a different login (do not start; coordinate)
    2 - Config error (plugin lib path missing)
    3 - External error (gh/API failure)
    4 - Auth error (not authenticated)
"""

from __future__ import annotations

import argparse
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
    sys.exit(2)  # Config error per ADR-035
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

_GH_TIMEOUT_SECONDS = 30
_BASE_CANDIDATES = ("main", "master", "develop", "trunk")
_HEADS_PREFIX = "refs/heads/"


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GH_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as err:
        raise RuntimeError(
            f"{cmd[0]} timed out after {_GH_TIMEOUT_SECONDS} seconds"
        ) from err
    except OSError as err:
        raise RuntimeError(f"failed to run {cmd[0]}: {err}") from err


def current_login() -> str:
    """Return the authenticated gh user login."""

    result = _run(["gh", "api", "user", "--jq", ".login"])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "gh api user failed")
    login = result.stdout.strip()
    if not login:
        raise RuntimeError("gh api user returned empty login")
    return login


def issue_assignees(owner: str, repo: str, issue: int) -> list[str]:
    """Return the current assignee logins for the issue."""

    result = _run(
        ["gh", "issue", "view", str(issue), "--repo", f"{owner}/{repo}",
         "--json", "assignees"],
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "gh issue view failed")
    try:
        data = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError) as err:
        raise RuntimeError("could not parse gh issue view output") from err
    assignees_value = data.get("assignees")
    assignees = [] if assignees_value is None else assignees_value
    if not isinstance(assignees, list):
        raise RuntimeError("gh issue view returned invalid assignees")
    return [
        login
        for assignee in assignees
        if isinstance(assignee, dict)
        for login in [assignee.get("login")]
        if isinstance(login, str) and login
    ]


def matching_remote_heads(ls_remote_output: str, issue: int) -> list[tuple[str, str]]:
    """Return ``(branch, sha)`` pairs whose branch name carries the issue number.

    The number must not touch another digit, so ``5420`` does not match
    ``54200`` or ``15420``. Lines that are not branch heads are skipped.
    """

    number = re.compile(rf"(?<!\d){issue}(?!\d)")
    matches: list[tuple[str, str]] = []
    for line in ls_remote_output.splitlines():
        sha, _, ref = line.partition("\t")
        if not ref.startswith(_HEADS_PREFIX):
            continue
        branch = ref[len(_HEADS_PREFIX):]
        if sha and number.search(branch):
            matches.append((branch, sha))
    return matches


def origin_base_ref() -> str | None:
    """Return the origin default branch as ``origin/<name>``, or ``None``.

    Reads ``refs/remotes/origin/HEAD`` first, then the common default names, so a
    consumer repository whose default branch is not ``main`` still classifies.
    """

    head = _run(["git", "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"])
    ref = head.stdout.strip()
    if head.returncode == 0 and ref.startswith("origin/"):
        return ref
    for name in _BASE_CANDIDATES:
        probe = _run(["git", "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{name}"])
        if probe.returncode == 0:
            return f"origin/{name}"
    return None


def commits_ahead(sha: str, base_ref: str | None) -> int | None:
    """Return how many commits ``sha`` has beyond ``base_ref``, or ``None``.

    This is an ancestry count. ``None`` means git could not count (object not
    fetched, no base ref). The caller treats that as unverified, not as zero.
    """

    if base_ref is None:
        return None
    result = _run(["git", "rev-list", "--count", sha, f"^{base_ref}"])
    if result.returncode != 0:
        return None
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


def merged_through_pr(owner: str, repo: str, branch: str, sha: str) -> bool:
    """Return true when a merged PR for ``branch`` had ``sha`` as its head.

    Squash merges never make the original commits reachable from the default
    branch, so ancestry alone reports a merged, retained branch as live work.
    A lookup failure returns false: an unverifiable branch stays in the warning.
    """

    result = _run(
        ["gh", "pr", "list", "--repo", f"{owner}/{repo}", "--head", branch,
         "--state", "merged", "--json", "headRefOid", "--jq", ".[].headRefOid"],
    )
    if result.returncode != 0:
        return False
    return sha in result.stdout.split()


def current_branch() -> str:
    """Return the checked-out branch name, or an empty string when unknown."""

    result = _run(["git", "branch", "--show-current"])
    return result.stdout.strip() if result.returncode == 0 else ""


def find_in_flight_branches(
    owner: str, repo: str, issue: int,
) -> tuple[list[dict[str, object]], list[str]]:
    """Probe origin for pushed branches that name the issue and carry unmerged work.

    Returns ``(in_flight, warnings)``. A branch with 0 commits ahead of the
    default branch, or whose head a merged PR already carried, is omitted. A
    branch whose count cannot be read is kept with ``ahead`` set to ``None``,
    since dropping it would hide possible live work. The caller's own branch is
    omitted. Any failure in the probe, from ``ls-remote`` through the per-branch
    checks, becomes a named warning and never fails the claim.
    """

    try:
        return _probe_in_flight(owner, repo, issue), []
    except RuntimeError as err:
        return [], [f"remote branch probe skipped: {err}"]


def _probe_in_flight(owner: str, repo: str, issue: int) -> list[dict[str, object]]:
    listing = _run(["git", "ls-remote", "--heads", "origin"])
    if listing.returncode != 0:
        reason = listing.stderr.strip() or f"git ls-remote exited {listing.returncode}"
        raise RuntimeError(reason)

    mine = current_branch()
    base_ref = origin_base_ref()
    in_flight: list[dict[str, object]] = []
    for branch, sha in matching_remote_heads(listing.stdout, issue):
        if branch == mine:
            continue
        ahead = commits_ahead(sha, base_ref)
        if ahead == 0 or merged_through_pr(owner, repo, branch, sha):
            continue
        in_flight.append({"branch": branch, "sha": sha, "ahead": ahead})
    return in_flight


def describe_in_flight(in_flight: list[dict[str, object]]) -> str:
    """Return a one-line warning naming each in-flight branch and its lead."""

    parts = [
        f"{item['branch']} ({'unverified' if item['ahead'] is None else str(item['ahead']) + ' ahead'})"
        for item in in_flight
    ]
    return f"WARNING: pushed branches already carry work on this issue: {', '.join(parts)}."


def write_claim_success(
    data: dict[str, object],
    summary: str,
    probe: tuple[list[dict[str, object]], list[str]],
    fmt: str,
) -> None:
    """Emit a PASS result with the remote-branch probe folded in."""

    in_flight, warnings = probe
    lines = [summary]
    if in_flight:
        lines.append(describe_in_flight(in_flight))
    lines.extend(f"WARNING: {warning}" for warning in warnings)
    write_skill_output(
        {**data, "in_flight_branches": in_flight, "warnings": warnings},
        output_format=fmt,
        human_summary="\n".join(lines),
        status="PASS", script_name="claim_issue.py",
    )


def write_already_claimed(
    issue: int,
    assignees: list[str],
    others: list[str],
    fmt: str,
) -> None:
    write_skill_error(
        f"Issue #{issue} already claimed by {', '.join(others)}. "
        "Do not start in parallel; coordinate with the assignee.",
        1, error_type="General",
        output_format=fmt, script_name="claim_issue.py",
        extra={"issue": issue, "assignees": assignees},
    )


def remove_self_assignment(owner: str, repo: str, issue: int) -> None:
    result = _run(
        ["gh", "issue", "edit", str(issue), "--repo", f"{owner}/{repo}",
         "--remove-assignee", "@me"],
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "gh issue edit remove-assignee failed")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Self-assign an issue, refusing if already claimed by another login.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument("--issue", type=int, required=True, help="Issue number")
    add_output_format_arg(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo
    fmt = get_output_format(args.output_format)

    try:
        me = current_login()
        assignees = issue_assignees(owner, repo, args.issue)
    except RuntimeError as err:
        write_skill_error(
            str(err), 3, error_type="ApiError",
            output_format=fmt, script_name="claim_issue.py",
        )
        raise SystemExit(3) from err

    others = [a for a in assignees if a != me]
    if others:
        write_already_claimed(args.issue, assignees, others, fmt)
        raise SystemExit(1)

    if me and me in assignees:
        write_claim_success(
            {"issue": args.issue, "assignees": assignees, "claimed": me},
            f"Issue #{args.issue} already held by {me}.",
            find_in_flight_branches(owner, repo, args.issue), fmt,
        )
        return 0

    try:
        assign = _run(
            ["gh", "issue", "edit", str(args.issue), "--repo", f"{owner}/{repo}",
             "--add-assignee", "@me"],
        )
    except RuntimeError as err:
        write_skill_error(
            str(err),
            3, error_type="ApiError",
            output_format=fmt, script_name="claim_issue.py",
        )
        raise SystemExit(3) from err
    if assign.returncode != 0:
        write_skill_error(
            assign.stderr.strip() or "gh issue edit failed",
            3, error_type="ApiError",
            output_format=fmt, script_name="claim_issue.py",
        )
        raise SystemExit(3)

    try:
        assignees_after_claim = issue_assignees(owner, repo, args.issue)
    except RuntimeError as err:
        write_skill_error(
            str(err), 3, error_type="ApiError",
            output_format=fmt, script_name="claim_issue.py",
        )
        raise SystemExit(3) from err
    if me not in assignees_after_claim:
        write_skill_error(
            f"Issue #{args.issue} assignment could not be confirmed for {me}.",
            3, error_type="ApiError",
            output_format=fmt, script_name="claim_issue.py",
            extra={"issue": args.issue, "assignees": assignees_after_claim},
        )
        raise SystemExit(3)
    others_after_claim = [a for a in assignees_after_claim if a != me]
    if others_after_claim:
        try:
            remove_self_assignment(owner, repo, args.issue)
        except RuntimeError as err:
            write_skill_error(
                str(err), 3, error_type="ApiError",
                output_format=fmt, script_name="claim_issue.py",
            )
            raise SystemExit(3) from err
        write_already_claimed(args.issue, assignees_after_claim, others_after_claim, fmt)
        raise SystemExit(1)

    write_claim_success(
        {"issue": args.issue, "claimed": me or "@me"},
        f"Claimed issue #{args.issue} for {me or '@me'}.",
        find_in_flight_branches(owner, repo, args.issue), fmt,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

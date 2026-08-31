#!/usr/bin/env python3
"""Claim an issue by self-assigning, refusing if already claimed (issue #2477).

Pre-flight coordination for the competing-PR failure mode: a worker claims an
issue before starting development. If another login already holds the issue, the
claim is refused so two workers do not develop the same issue in parallel.

An assignee is a cooperative signal a worker can forget to set; a pushed remote
branch is evidence of real in-flight work. On a successful claim we additionally
probe remote heads for branches that reference the issue number and carry commits
beyond origin/main, surfacing them as a WARNING (issue #5428). This is a warning,
not a refusal: a hard refusal would deadlock an agent resuming its own pushed
work, so the claim still succeeds with exit code 0 and an ``in_flight_branches``
field the caller can inspect.

Exit codes follow ADR-035:
    0 - Claimed (or already held by current user). May carry an
        ``in_flight_branches`` WARNING; the claim still succeeds.
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


def _branch_matches_issue(ref: str, issue: int) -> bool:
    """True when a ref name references the issue with digit boundaries.

    ``codex/5420-a-paths`` matches issue 5420; ``codex/54200-x`` and
    ``codex/15420-x`` do not, because an adjacent digit means a different
    issue number. Observed naming: ``<tool>/<issue>-<slug>`` and
    ``<tool>/fix-<issue>-<slug>``.
    """

    return re.search(rf"(?<!\d){issue}(?!\d)", ref) is not None


def remote_branches_for_issue(issue: int) -> list[tuple[str, str]]:
    """Return (ref, sha) pairs for remote heads whose name references the issue.

    Runs ``git ls-remote --heads origin`` once. Raises RuntimeError on failure so
    the caller can degrade to a warning (issue #5428).
    """

    result = _run(["git", "ls-remote", "--heads", "origin"])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git ls-remote failed")
    matches: list[tuple[str, str]] = []
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 2:
            continue
        sha, ref = parts[0].strip(), parts[1].strip()
        if sha and ref and _branch_matches_issue(ref, issue):
            matches.append((ref, sha))
    return matches


def commits_ahead_of_main(sha: str) -> int:
    """Return the commit count on ``sha`` that is not reachable from origin/main.

    A stale ancestor branch (already merged, not yet deleted) returns 0; live
    unmerged work returns a positive count. Raises RuntimeError on git failure.
    """

    result = _run(["git", "rev-list", "--count", sha, "^origin/main"])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git rev-list failed")
    text = result.stdout.strip()
    try:
        return int(text) if text else 0
    except ValueError as err:
        raise RuntimeError(f"git rev-list returned non-numeric count: {text!r}") from err


def probe_competing_branches(issue: int) -> tuple[list[dict[str, object]], list[str]]:
    """Probe remote heads for pushed, unmerged work on this issue.

    Returns (in_flight_branches, warnings). ``in_flight_branches`` holds only
    branches carrying commits beyond origin/main; stale ancestor branches (0
    commits ahead) are excluded so a merged-but-undeleted branch is not a false
    alarm. Never raises: a git failure (offline, no remote, missing origin/main)
    degrades to a named warning so the claim still proceeds (issue #5428).
    """

    try:
        refs = remote_branches_for_issue(issue)
    except RuntimeError as err:
        return [], [f"could not probe remote branches for issue #{issue}: {err}"]
    in_flight: list[dict[str, object]] = []
    warnings: list[str] = []
    for ref, sha in refs:
        try:
            ahead = commits_ahead_of_main(sha)
        except RuntimeError as err:
            warnings.append(f"could not count commits on {ref}: {err}")
            continue
        if ahead > 0:
            in_flight.append({"ref": ref, "sha": sha, "commits_ahead": ahead})
    return in_flight, warnings


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


def write_claim_success(issue: int, claimant: str, fmt: str) -> None:
    """Emit the successful-claim envelope, warning on any in-flight remote work.

    The branch probe is a warning, not a gate: status becomes WARNING when a
    competing branch or a degraded probe is found, but the claim still exits 0
    so it cannot deadlock an agent resuming its own pushed work (issue #5428).
    """

    in_flight, warnings = probe_competing_branches(issue)
    status = "WARNING" if (in_flight or warnings) else "PASS"
    summary = f"Claimed issue #{issue} for {claimant}."
    if in_flight:
        refs = ", ".join(
            f"{b['ref']} (+{b['commits_ahead']} commits ahead of main)"
            for b in in_flight
        )
        summary += f" WARNING: unmerged pushed work already exists on {refs}."
    for warning in warnings:
        summary += f" WARNING: {warning}"

    write_skill_output(
        {
            "issue": issue,
            "claimed": claimant,
            "in_flight_branches": in_flight,
            "warnings": warnings,
        },
        output_format=fmt,
        human_summary=summary,
        status=status, script_name="claim_issue.py",
    )


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
        write_skill_output(
            {"issue": args.issue, "assignees": assignees, "claimed": me},
            output_format=fmt,
            human_summary=f"Issue #{args.issue} already held by {me}.",
            status="PASS", script_name="claim_issue.py",
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

    write_claim_success(args.issue, me or "@me", fmt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

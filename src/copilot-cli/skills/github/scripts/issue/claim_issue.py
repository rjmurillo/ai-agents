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
    """True when a ref name references the issue with alphanumeric boundaries.

    ``codex/5420-a-paths`` matches issue 5420; a neighboring digit OR letter
    means a different token, so ``codex/54200-x`` (larger number),
    ``codex/15420-x`` (larger number), ``fix/deadbeef5420cafe`` (SHA fragment),
    and ``fix/issue5420work`` (letter-glued) do NOT match. ``feature/pr-1234-
    fixes-5420`` and ``5420`` DO match. Observed naming: ``<tool>/<issue>-
    <slug>`` and ``<tool>/fix-<issue>-<slug>``.
    """

    return re.search(rf"(?<![A-Za-z0-9]){issue}(?![A-Za-z0-9])", ref) is not None


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
    unmerged work returns a positive count. Raises RuntimeError on git failure
    (including a ``bad object`` when the advertised SHA is not in the local
    object store, e.g. a fresh clone or worktree).
    """

    result = _run(["git", "rev-list", "--count", sha, "^origin/main"])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git rev-list failed")
    text = result.stdout.strip()
    try:
        return int(text) if text else 0
    except ValueError as err:
        raise RuntimeError(f"git rev-list returned non-numeric count: {text!r}") from err


def _count_ahead_resilient(ref: str, sha: str) -> tuple[int | None, str | None]:
    """Count commits ahead of origin/main, fetching the ref on demand once.

    ``git ls-remote`` advertises SHAs but does not fetch their objects, so
    ``rev-list`` fails with ``bad object`` on a fresh clone/worktree. When the
    first count fails, fetch just this ref (bounded: only issue-matching refs
    reach here) and retry once. Returns ``(count, None)`` on success, or
    ``(None, warning)`` when the count still cannot be determined, so the caller
    surfaces the branch instead of silently dropping it (issue #5428).
    """

    try:
        return commits_ahead_of_main(sha), None
    except RuntimeError as first_err:
        error: RuntimeError = first_err
    fetch = _run(["git", "fetch", "--quiet", "origin", ref])
    if fetch.returncode == 0:
        try:
            return commits_ahead_of_main(sha), None
        except RuntimeError as retry_err:
            error = retry_err
    return None, (
        f"could not count commits on {ref}; the remote object may not be "
        f"fetched: {error}"
    )


def _origin_owner_repo() -> tuple[str, str] | None:
    """Return (owner, repo) for the checkout's ``origin`` remote, or None.

    None means there is no ``origin`` (or this is not a git repo, or the URL is
    unrecognized). Handles HTTPS (``https://github.com/o/r.git``) and SSH
    (``git@github.com:o/r.git``) forms.
    """

    result = _run(["git", "remote", "get-url", "origin"])
    if result.returncode != 0:
        return None
    match = re.search(r"[/:]([^/:]+)/([^/:]+?)(?:\.git)?/?$", result.stdout.strip())
    if match is None:
        return None
    return match.group(1), match.group(2)


def _probe_preconditions(owner: str, repo: str) -> str | None:
    """Return a named degradation warning if the probe cannot trust the remote.

    ``--owner``/``--repo`` select the GitHub issue, but ``origin`` comes from
    whatever repo contains cwd. If the checkout's origin is a different repo
    (or absent, or origin/main is missing) the probe would inspect the wrong
    remote, so it degrades to a warning and is skipped rather than reporting
    unrelated or missing branches (issue #5428). Returns None when safe.
    """

    origin = _origin_owner_repo()
    if origin is None:
        return (
            f"skipped remote-branch probe: current checkout has no 'origin' remote "
            f"(or is not a git repo); cannot verify in-flight work for {owner}/{repo}"
        )
    if (origin[0].lower(), origin[1].lower()) != (owner.lower(), repo.lower()):
        return (
            f"skipped remote-branch probe: checkout origin is {origin[0]}/{origin[1]}, "
            f"not the requested {owner}/{repo}"
        )
    if _run(["git", "rev-parse", "--verify", "--quiet", "origin/main"]).returncode != 0:
        return f"skipped remote-branch probe: origin/main not found for {owner}/{repo}"
    return None


def probe_competing_branches(
    issue: int, owner: str, repo: str
) -> tuple[list[dict[str, object]], list[str]]:
    """Probe remote heads for pushed, unmerged work on this issue.

    Returns (in_flight_branches, warnings). ``in_flight_branches`` holds
    branches carrying commits beyond origin/main; a stale ancestor branch (0
    commits ahead) is excluded so a merged-but-undeleted branch is not a false
    alarm. A branch whose count cannot be determined is included with
    ``commits_ahead: None`` and a ``reason`` so a collision is never silently
    dropped. Never raises: an unusable remote (offline, wrong origin, missing
    origin/main) degrades to a named warning so the claim still proceeds.
    """

    precondition_warning = _probe_preconditions(owner, repo)
    if precondition_warning:
        return [], [precondition_warning]
    try:
        refs = remote_branches_for_issue(issue)
    except RuntimeError as err:
        return [], [f"could not probe remote branches for issue #{issue}: {err}"]
    in_flight: list[dict[str, object]] = []
    warnings: list[str] = []
    for ref, sha in refs:
        ahead, warning = _count_ahead_resilient(ref, sha)
        if warning:
            warnings.append(warning)
        if ahead is None:
            in_flight.append(
                {
                    "ref": ref,
                    "sha": sha,
                    "commits_ahead": None,
                    "reason": "commit count undetermined; remote object not fetched",
                }
            )
        elif ahead > 0:
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


def write_claim_success(
    issue: int,
    claimant: str,
    owner: str,
    repo: str,
    fmt: str,
    *,
    already_held: bool = False,
    assignees: list[str] | None = None,
) -> None:
    """Emit the successful-claim envelope, warning on any in-flight remote work.

    Both exit-0 success paths route through here: a fresh claim and resuming an
    issue already held by the current user (``already_held=True``). The branch
    probe is a warning, not a gate: status becomes WARNING when a competing
    branch or a degraded probe is found, but the claim still exits 0 so it
    cannot deadlock an agent resuming its own pushed work (issue #5428). Wiring
    the probe into only the fresh path left a resuming agent unqualified-green
    while a different party held unmerged work.
    """

    in_flight, warnings = probe_competing_branches(issue, owner, repo)
    status = "WARNING" if (in_flight or warnings) else "PASS"
    if already_held:
        summary = f"Issue #{issue} already held by {claimant}."
    else:
        summary = f"Claimed issue #{issue} for {claimant}."
    if in_flight:
        refs = ", ".join(_describe_in_flight(b) for b in in_flight)
        summary += f" WARNING: unmerged pushed work already exists on {refs}."
    for warning in warnings:
        summary += f" WARNING: {warning}"

    data: dict[str, object] = {
        "issue": issue,
        "claimed": claimant,
        "in_flight_branches": in_flight,
        "warnings": warnings,
    }
    if assignees is not None:
        data["assignees"] = assignees

    write_skill_output(
        data,
        output_format=fmt,
        human_summary=summary,
        status=status, script_name="claim_issue.py",
    )


def _describe_in_flight(branch: dict[str, object]) -> str:
    """Human phrase for one in-flight branch, including the unknown-count case."""

    ahead = branch["commits_ahead"]
    if ahead is None:
        return f"{branch['ref']} (commit count undetermined)"
    return f"{branch['ref']} (+{ahead} commits ahead of main)"


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
            args.issue, me, owner, repo, fmt,
            already_held=True, assignees=assignees,
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

    write_claim_success(args.issue, me or "@me", owner, repo, fmt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

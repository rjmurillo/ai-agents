#!/usr/bin/env python3
"""Check whether the current branch's open PR carries a bypass label.

Mirrors the canonical commit-limit-bypass gate in
``.github/workflows/pr-validation.yml`` ("Enforce Blocking Issues" step), which
fetches the PR labels with::

gh pr view $env:PR_NUMBER --repo $env:GITHUB_REPOSITORY --json labels --jq '.labels[].name' 2>$null

and allows the over-limit push when that label list contains
``commit-limit-bypass``. The pre-push hook calls this helper so a local repair
push to an already-over-limit PR honors the SAME override CI honors, instead of
forcing ``--no-verify`` (Issue #2456).

Stricter/looser/different than canonical: label SEMANTICS are identical (a label
membership test against ``commit-limit-bypass``). Two intentional differences,
both forced by the pre-push context rather than by a policy change:

- The PR is resolved from the CURRENT BRANCH (no PR-number argument). At
  pre-push time the PR number is not in the environment the way it is in the CI
  job; ``gh pr view`` with no number infers the PR from the checked-out branch.
- On any gh failure (not authenticated, network error, gh missing) this helper
  FAILS CLOSED: it exits non-zero so the caller keeps blocking. A transient gh
  hiccup must not silently lift the commit-count limit. CI does not need this
  fallback because the PR is guaranteed to exist when its workflow runs.

Exit codes (ADR-035):
    0 - bypass label present on the current branch's open PR
    1 - no bypass label, or no open PR for the branch (block stays)
    3 - external error (gh unavailable / API failure / not authenticated)

stdout carries a single human-readable status line for the hook to echo, e.g.
``commit-limit-bypass present on PR #2337`` or ``no commit-limit-bypass label
(PR #2337)`` or ``no open PR for branch fix/foo``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import urllib.parse

DEFAULT_LABEL = "commit-limit-bypass"
# Bounded timeout on the outbound gh call (release-it.md: every outbound call
# sets an explicit timeout). A pre-push hook must not hang on a slow API.
GH_TIMEOUT_SECONDS = 15

EXIT_PRESENT = 0
EXIT_ABSENT = 1
EXIT_EXTERNAL = 3



# GitHub owner and repository names allow letters, digits, hyphen, underscore,
# and period; nothing else, and neither part may be empty.
_OWNER_REPO_PATTERN = re.compile(r"[\w.-]+/[\w.-]+")

# git-check-ref-format is broader than this, but every ref this tool queries is
# an ordinary branch name. Refusing the rest costs nothing real and keeps a
# crafted ref out of the query string.
_GIT_REF_PATTERN = re.compile(r"[\w./-]+")

def _run_gh_pr_view(branch: str | None) -> subprocess.CompletedProcess[str]:
    """Fetch the current (or named) branch PR's labels.

    Uses the REST list-pulls endpoint rather than ``gh pr view``.

    ``gh pr view`` goes through GraphQL, and GraphQL is the first budget to
    exhaust when several agents work a repository at once. Measured during a
    fleet session: graphql 0 of 5000 remaining while core REST still had 4921.
    In that state ``gh pr view`` fails, this helper fails closed by design, and
    the commit-limit ceiling loses its only sanctioned relief precisely when
    parallel work makes long branches most likely. Refs #4690.

    The output is normalised to the same shape the caller already parses, so
    the decision logic below is unchanged.
    """
    if branch:
        head = branch
    else:
        rev = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=GH_TIMEOUT_SECONDS,
            check=False,
        )
        if rev.returncode != 0:
            return rev
        head = rev.stdout.strip()

    owner_repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not owner_repo:
        # Derive from the git remote rather than `gh repo view`, which is also
        # GraphQL and therefore fails in the exact conditions this change
        # exists to survive.
        remote = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=GH_TIMEOUT_SECONDS,
            check=False,
        )
        if remote.returncode != 0:
            return remote
        url = remote.stdout.strip()
        if url.endswith(".git"):
            url = url[: -len(".git")]
        if ":" in url and "//" not in url:  # git@host:owner/repo
            url = url.split(":", 1)[1]
        else:  # https://host/owner/repo
            # Take the path after the host rather than the last two slash
            # separated segments. Counting segments turns a URL with no
            # repository, such as https://github.com/owner, into the
            # valid-looking but wrong "github.com/owner", because the scheme
            # and host inflate the count. Parsing the path makes a truncated
            # remote produce an empty value that the check below rejects.
            path = urllib.parse.urlparse(url).path.strip("/")
            segments = [segment for segment in path.split("/") if segment]
            url = "/".join(segments[-2:]) if len(segments) >= 2 else ""
        owner_repo = url

    owner = owner_repo.split("/")[0] if "/" in owner_repo else ""

    # owner_repo comes from GITHUB_REPOSITORY or a parsed remote URL, and head
    # from a branch name. All three are attacker-influenceable in a fork or a
    # hostile checkout, and all three are interpolated into the request path and
    # query. Command injection is not the reachable risk, since gh is invoked as
    # an argument list with no shell, so a metacharacter arrives as a literal
    # argument. What validation prevents is a crafted value steering the request
    # at a different repository, or smuggling a second query parameter through
    # the head filter. Refs #4672.
    if not _OWNER_REPO_PATTERN.fullmatch(owner_repo):
        return subprocess.CompletedProcess(
            ["gh"], 2, "", f"refusing to query malformed repository {owner_repo!r}"
        )
    if not _GIT_REF_PATTERN.fullmatch(head):
        return subprocess.CompletedProcess(
            ["gh"], 2, "", f"refusing to query malformed branch {head!r}"
        )

    proc = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{owner_repo}/pulls",
            "-X",
            "GET",
            "-f",
            f"head={owner}:{head}",
            "-f",
            "state=all",
            "--jq",
            # Collapse the list to the single-object shape `gh pr view` returns.
            "if length == 0 then empty else "
            "{number: .[0].number, state: (.[0].state | ascii_upcase), "
            "labels: [.[0].labels[] | {name: .name}]} end",
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=GH_TIMEOUT_SECONDS,
        check=False,
    )
    # An empty body means no PR for this branch, which the caller must be able
    # to tell apart from a failed call. Mirror the "no PR" signal gh emits.
    if proc.returncode == 0 and not proc.stdout.strip():
        # A literal argv rather than proc.args. The caller only reads the
        # returncode and streams, so echoing the real command back buys
        # nothing, and proc.args carries the environment-derived repository
        # and branch into a value that flows on to other code. Keeping those
        # out of the returned object means a reader does not have to re-derive
        # that they were validated above.
        return subprocess.CompletedProcess(
            ["gh", "api"], 1, "", "no pull requests found for branch"
        )
    return proc


def _describe_gh_failure(proc: subprocess.CompletedProcess[str]) -> str:
    """Return an actionable one-line reason the label lookup failed.

    The previous message was ``gh pr view failed (exit N)``, which was wrong on
    both halves and told the reader nothing they could act on. This helper does
    not change the verdict: an unverifiable label still blocks, because a local
    check cannot confirm a permission only a maintainer can grant. It changes
    what the reader is told, so a denied session is not mistaken for a missing
    label.

    Two corrections and one addition:

    1. This module stopped using ``gh pr view`` (GraphQL) for the REST
       list-pulls endpoint in issue #4690. Naming the wrong command sent a
       reader to the wrong place. Every operator-facing string in this module
       says "gh label lookup" for the same reason: an earlier fix corrected
       only this function and left the timeout and unparseable-JSON paths
       naming the old command, which the regression test did not catch because
       it exercised one path. Refs #5130 review.
    2. An authentication or egress-policy denial is not a transient failure and
       will not pass on a retry. It is called out by name so the reader stops
       re-running the push.
    3. The two sanctioned routes are named. CONTRIBUTING.md:875 reads,
       verbatim: "You MUST split the PR, or ask a human maintainer to decide
       on the ``commit-limit-bypass`` label." An earlier revision of this
       message also suggested landing the commits on another pushed branch so
       they stop counting as new. That is a real effect of
       ``_unpushed_commit_count``, but that function exists for genuine stacked
       PRs (issue #3610), and describing it here read as instructions for
       defeating the ceiling with a throwaway remote branch. Removed: an error
       message from the enforcement mechanism itself is the last place that
       should teach an evasion. Refs #5130 review (Copilot).

    Measured on a Claude Code cloud session, 2026-08-20: ``gh auth status``
    reported "The token in GH_TOKEN is invalid", and every REST call returned
    HTTP 403 "GitHub access is not enabled for this session". The old message
    rendered that as ``gh pr view failed (exit 1)``.
    """
    stderr = (proc.stderr or "") + (proc.stdout or "")
    lowered = stderr.lower()
    detail = f"exit {proc.returncode}"

    # Order matters, and 403 must not be the first test. GitHub answers an
    # exhausted rate limit with 403 too ("API rate limit exceeded", HTTP 403),
    # so keying on the status code first labels a retryable condition
    # "will not pass on retry", which is the opposite of the truth and the one
    # thing this helper exists to get right. Match on the distinguishing
    # wording, most specific first, and treat the status code only as a
    # fallback signal. Refs #5130 review (Cursor Bugbot).
    if "rate limit" in lowered or "secondary rate" in lowered:
        reason = "gh hit a rate limit; this succeeds once the window resets"
    elif "not enabled for this session" in lowered or "403" in lowered:
        reason = "gh is denied by policy (HTTP 403); this will not pass on retry"
    elif "401" in lowered or ("invalid" in lowered and "token" in lowered):
        reason = "gh is not authenticated; check GH_TOKEN"
    else:
        reason = "gh label lookup failed"

    return (
        f"{reason} ({detail}). "
        "The label cannot be verified locally, so the commit limit still "
        "applies. Split the PR, or ask a human maintainer to decide on the "
        "commit-limit-bypass label (CONTRIBUTING.md, 'Bypassing the Limit'); "
        "that label is human-only, so do not apply it yourself."
    )


def check_bypass_label(label: str, branch: str | None) -> tuple[int, str]:
    """Return (exit_code, status_line) for the bypass-label check.

    Pure decision logic over the gh result so tests can exercise every branch
    without a live network. I/O is isolated in ``_run_gh_pr_view``.
    """
    try:
        proc = _run_gh_pr_view(branch)
    except FileNotFoundError:
        return EXIT_EXTERNAL, (
            "gh CLI not found, so the label cannot be verified locally and the "
            "commit limit still applies. Split the PR, or ask a human maintainer "
            "to decide on the commit-limit-bypass label; that label is human-only."
        )
    except subprocess.TimeoutExpired:
        return EXIT_EXTERNAL, (
            f"gh label lookup timed out after {GH_TIMEOUT_SECONDS}s. "
            "The label cannot be verified locally, so the commit limit still "
            "applies. Split the PR, or ask a human maintainer to decide on the "
            "commit-limit-bypass label; that label is human-only."
        )

    if proc.returncode != 0:
        stderr = (proc.stderr or "").lower()
        # gh emits "no pull requests found" / "no open pull requests" when the
        # branch has no associated PR. That is a definitive "no bypass", not an
        # error: the limit must still apply (acceptance criterion: PRs without
        # the label still block; a branch with no PR cannot carry the label).
        if "no pull request" in stderr or "no open pull request" in stderr:
            target = branch or "current branch"
            return EXIT_ABSENT, f"no open PR for {target}"
        return EXIT_EXTERNAL, _describe_gh_failure(proc)

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return EXIT_EXTERNAL, (
            "gh label lookup returned unparseable JSON. "
            "The label cannot be verified locally, so the commit limit still "
            "applies. Split the PR, or ask a human maintainer to decide on the "
            "commit-limit-bypass label; that label is human-only."
        )

    number = payload.get("number")
    state = payload.get("state")
    if state != "OPEN":
        target = branch or "current branch"
        return EXIT_ABSENT, f"no open PR for {target}"

    labels_field = payload.get("labels")
    # Collapse only explicit null (python.md): a present-but-null labels field
    # means "no labels", not an error.
    labels = labels_field if isinstance(labels_field, list) else []
    names = {
        item.get("name")
        for item in labels
        if isinstance(item, dict) and item.get("name")
    }

    if label in names:
        return EXIT_PRESENT, f"{label} present on PR #{number}"
    return EXIT_ABSENT, f"no {label} label (PR #{number})"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Exit 0 when the current branch's open PR carries the bypass "
            "label; mirrors pr-validation.yml commit-limit-bypass gate."
        )
    )
    parser.add_argument(
        "--label",
        default=DEFAULT_LABEL,
        help=f"Label to check for (default: {DEFAULT_LABEL})",
    )
    parser.add_argument(
        "--branch",
        default=None,
        help="Branch to resolve the PR from (default: current branch)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    exit_code, status = check_bypass_label(args.label, args.branch)
    print(status)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

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
import subprocess

DEFAULT_LABEL = "commit-limit-bypass"
# Bounded timeout on the outbound gh call (release-it.md: every outbound call
# sets an explicit timeout). A pre-push hook must not hang on a slow API.
GH_TIMEOUT_SECONDS = 15

EXIT_PRESENT = 0
EXIT_ABSENT = 1
EXIT_EXTERNAL = 3


def _run_gh_pr_view(branch: str | None) -> subprocess.CompletedProcess[str]:
    """Fetch the current (or named) branch PR's labels via gh.

    Returns the completed process. The caller interprets returncode/stderr to
    distinguish "no PR" from "gh failed".
    """
    cmd = ["gh", "pr", "view"]
    if branch:
        cmd.append(branch)
    cmd += ["--json", "number,labels,state"]
    return subprocess.run(
        cmd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=GH_TIMEOUT_SECONDS,
        check=True,
    )


def check_bypass_label(label: str, branch: str | None) -> tuple[int, str]:
    """Return (exit_code, status_line) for the bypass-label check.

    Pure decision logic over the gh result so tests can exercise every branch
    without a live network. I/O is isolated in ``_run_gh_pr_view``.
    """
    try:
        proc = _run_gh_pr_view(branch)
    except FileNotFoundError:
        return EXIT_EXTERNAL, "gh CLI not found; cannot check bypass label"
    except subprocess.TimeoutExpired:
        return EXIT_EXTERNAL, f"gh pr view timed out after {GH_TIMEOUT_SECONDS}s"
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").lower()
        if "no pull request" in stderr or "no open pull request" in stderr:
            target = branch or "current branch"
            return EXIT_ABSENT, f"no open PR for {target}"
        return EXIT_EXTERNAL, f"gh pr view failed (exit {exc.returncode})"

    if proc.returncode != 0:
        stderr = (proc.stderr or "").lower()
        # gh emits "no pull requests found" / "no open pull requests" when the
        # branch has no associated PR. That is a definitive "no bypass", not an
        # error: the limit must still apply (acceptance criterion: PRs without
        # the label still block; a branch with no PR cannot carry the label).
        if "no pull request" in stderr or "no open pull request" in stderr:
            target = branch or "current branch"
            return EXIT_ABSENT, f"no open PR for {target}"
        return EXIT_EXTERNAL, f"gh pr view failed (exit {proc.returncode})"

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return EXIT_EXTERNAL, "gh pr view returned unparseable JSON"

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

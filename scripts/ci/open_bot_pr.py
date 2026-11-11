#!/usr/bin/env python3
"""Commit generated files on a bot branch and open a pull request.

Scheduled workflows cannot push to a protected default branch unless their
identity is on the ruleset bypass list (issue #7287). This script commits the
given paths on a fixed bot branch, pushes that branch, and opens a pull
request against the base branch. It reuses the git helpers of
`commit_and_push.py`, which pushes in place and so suits only unprotected
branches.

Rules:
  - A clean tree is a no-op. The examined path count is printed.
  - An open same-repository pull request already tracking the branch is left
    alone and the run exits 0, so an unmerged pull request never gathers a
    second one. Fork pull requests that reuse the branch name are ignored.
  - A remote branch with no open pull request is stale: it is deleted and
    recreated from the current checkout. The caller regenerates its content on
    every run, so the delete loses nothing. Nothing is force-pushed.
  - A pull request opened with `GITHUB_TOKEN` starts no `pull_request` runs, so
    a human must close and reopen it, or push to it, before required checks
    report.

Authentication is the caller's job (`gh auth setup-git` and `GH_TOKEN`).

EXIT CODES (ADR-035):
  0  - Success: published, nothing to commit, or a pull request already tracks the branch
  1  - Error: a git command failed
  2  - Error: usage/configuration (git or gh binary missing)
  3  - Error: external service failure (`gh` could not list or create the pull request)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

from commit_and_push import _git, _run, dirty

EXIT_SUCCESS = 0
EXIT_GIT_FAILED = 1
EXIT_USAGE = 2
EXIT_EXTERNAL = 3

_LS_REMOTE_NO_MATCH = 2  # `git ls-remote --exit-code`: no matching ref
_PR_LIST_LIMIT = 100


class GhQueryError(RuntimeError):
    """`gh` could not answer a pull request query. Maps to EXIT_EXTERNAL."""


def _gh(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a gh command, capturing combined output as UTF-8 text."""
    return subprocess.run(
        ["gh", *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def open_pr_url(branch: str) -> str | None:
    """Return the URL of the open same-repository pull request headed at `branch`.

    `gh pr list --head` matches the head ref name only, so a fork pull request
    that reuses the branch name would match too and stop the job for good.
    Rows with `isCrossRepository` true are ignored. Raises GhQueryError when
    `gh` cannot answer, or the page is full, so a lookup failure or a truncated
    list is never read as "no pull request".
    """
    result = _gh(
        [
            "pr",
            "list",
            "--head",
            branch,
            "--state",
            "open",
            "--limit",
            str(_PR_LIST_LIMIT),
            "--json",
            "url,isCrossRepository",
        ]
    )
    if result.returncode != 0:
        raise GhQueryError(result.stdout)
    try:
        rows = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise GhQueryError(f"unparseable gh output: {result.stdout!r}") from exc
    if not isinstance(rows, list) or any(
        not isinstance(r, dict)
        or "url" not in r
        or not isinstance(r.get("isCrossRepository"), bool)
        for r in rows
    ):
        raise GhQueryError(f"unexpected gh output shape: {result.stdout!r}")
    if len(rows) >= _PR_LIST_LIMIT:
        raise GhQueryError(f"pull request list may be truncated at {_PR_LIST_LIMIT} rows")
    own = [r for r in rows if not r["isCrossRepository"]]
    return str(own[0]["url"]) if own else None


def remote_branch_exists(branch: str) -> bool:
    """Return True when `origin` holds `branch`. Raises RuntimeError on a git failure."""
    result = _git(["ls-remote", "--exit-code", "--heads", "origin", branch])
    if result.returncode == 0:
        return True
    if result.returncode == _LS_REMOTE_NO_MATCH:
        return False
    raise RuntimeError(f"git ls-remote failed: {result.stdout}")


def pr_body(paths: list[str], issue: str | None) -> str:
    """Build the pull request body. `## Changes` lists exactly the staged paths."""
    changes = "\n".join(f"- `{path}`" for path in paths)
    reference = f"Refs #{issue}" if issue else "none"
    lines = [
        "## Summary",
        "",
        "### What",
        "",
        "Scheduled workflow output committed on a bot branch.",
        "",
        "### Why",
        "",
        "The default branch is protected, so the workflow cannot push to it.",
        "Merge this pull request to publish the update.",
        "",
        "## Specification References",
        "",
        "| Type | Reference | Description |",
        "|------|-----------|-------------|",
        f"| **Issue** | {reference} | Scheduled workflow output |",
        "",
        "## Changes",
        "",
        changes,
        "",
        "## Type of Change",
        "",
        "- [x] Infrastructure/CI change",
    ]
    if issue:
        lines += ["", "## Related Issues", "", f"Refs #{issue}"]
    return "\n".join(lines) + "\n"


def _message_flags(messages: list[str]) -> list[str]:
    """Map each message paragraph to its own `-m` flag, in order."""
    return [flag for message in messages for flag in ("-m", message)]


def publish(args: argparse.Namespace) -> int:
    """Commit on the bot branch, push it, and open the pull request."""
    existing = open_pr_url(args.branch)
    if existing:
        print(f"Open pull request already tracks {args.branch}: {existing}")
        return EXIT_SUCCESS

    if remote_branch_exists(args.branch):
        print(f"Deleting stale remote branch {args.branch} (no open pull request)")
        if _run(["push", "origin", "--delete", args.branch]) != 0:
            return EXIT_GIT_FAILED

    for command in (
        ["checkout", "-B", args.branch],
        ["add", "--", *args.path],
        ["commit", *_message_flags(args.message)],
        ["push", "--set-upstream", "origin", args.branch],
    ):
        if _run(command) != 0:
            return EXIT_GIT_FAILED

    created = _gh(
        [
            "pr",
            "create",
            "--base",
            args.base,
            "--head",
            args.branch,
            "--title",
            args.pr_title or args.message[0],
            "--body",
            pr_body(args.path, args.issue),
        ]
    )
    if created.returncode != 0:
        print("ERROR: gh pr create failed:", file=sys.stderr)
        print(created.stdout, file=sys.stderr)
        return EXIT_EXTERNAL
    print(created.stdout.strip())
    return EXIT_SUCCESS


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the bot pull request helper."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--path",
        action="append",
        required=True,
        help="Path to stage and watch for changes. Repeatable.",
    )
    parser.add_argument(
        "--message",
        action="append",
        required=True,
        help="Commit message paragraph, in order. Repeatable (maps to git -m).",
    )
    parser.add_argument("--user-name", required=True, help="git user.name to set.")
    parser.add_argument("--user-email", required=True, help="git user.email to set.")
    parser.add_argument("--branch", required=True, help="Bot branch to publish on.")
    parser.add_argument("--base", default="main", help="Pull request base branch.")
    parser.add_argument("--pr-title", help="Pull request title. Defaults to the first --message.")
    parser.add_argument(
        "--issue", help="Issue number for a `Refs #N` line in the pull request body."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Publish the given paths through a pull request. Returns an ADR-035 code."""
    args = build_parser().parse_args(argv)

    try:
        for key, value in (("user.name", args.user_name), ("user.email", args.user_email)):
            if _run(["config", key, value]) != 0:
                return EXIT_GIT_FAILED

        if not dirty(args.path):
            print(f"No changes to commit (examined {len(args.path)} path(s))")
            return EXIT_SUCCESS

        return publish(args)
    except FileNotFoundError as exc:
        print(f"ERROR: git or gh not available: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except GhQueryError as exc:
        print(f"ERROR: gh pr list failed: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_GIT_FAILED


if __name__ == "__main__":
    sys.exit(main())

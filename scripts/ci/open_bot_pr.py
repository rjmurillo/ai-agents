#!/usr/bin/env python3
"""Commit generated files on a bot branch and open a pull request.

Scheduled workflows cannot push to a protected default branch unless their
identity is on the ruleset bypass list (issue #7287). This script commits the
given paths on a fixed bot branch, pushes that branch, and opens a pull
request against the base branch. `commit_and_push.py` pushes in place and so
suits only unprotected branches. This script has its own git helpers because
every call here needs a timeout.

Rules:
  - A clean tree is a no-op. The examined path count is printed. Only the
    paths with changes are staged and named in the pull request body.
  - An open same-repository pull request already tracking the branch is left
    alone and the run exits 0, so an unmerged pull request never gathers a
    second one. Fork pull requests that reuse the branch name are ignored.
  - A remote branch with no open pull request is stale: it is deleted and
    recreated from the current checkout. The caller regenerates the content on
    every run, so the delete loses only a commit someone added to the branch by
    hand. Do not commit there. Nothing is force-pushed.
  - A pull request opened with `GITHUB_TOKEN` starts no `pull_request` runs, so
    a human must close and reopen it before required checks report.
  - The branch must start with `automation/` so a caller cannot name the base or
    a human branch. The checkout must be an ancestor of `origin/<base>`, so a
    `workflow_dispatch` from a feature ref cannot publish that ref's commits.
  - Every git and gh call has a timeout. A timeout counts as that call failing.
  - Output carries one `outcome=noop|skipped|published` line, and a skip also
    prints a `::notice::` annotation so the run page shows a stalled update.

Authentication is the caller's job (`gh auth setup-git` and `GH_TOKEN`).

EXIT CODES (ADR-035):
  0  - Success: published, nothing to commit, or a pull request already tracks the branch
  1  - Error: a git command failed
  2  - Error: usage/configuration (git or gh binary missing, or HEAD not on origin/<base>)
  3  - Error: external service failure (`gh` could not list or create the pull request)

Keep the output files in one invocation: a second invocation would find the
first one's open pull request and skip.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

EXIT_SUCCESS = 0
EXIT_GIT_FAILED = 1
EXIT_USAGE = 2
EXIT_EXTERNAL = 3

_LS_REMOTE_NO_MATCH = 2  # `git ls-remote --exit-code`: no matching ref
_PR_LIST_LIMIT = 100
_TIMEOUT_SECONDS = 120
_TIMED_OUT = 124  # the `timeout(1)` convention


class GhError(RuntimeError):
    """A `gh` call failed. The message names the operation. Maps to EXIT_EXTERNAL."""


def _exec(tool: str, args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run `tool args`, capturing combined output as UTF-8 text, with a timeout.

    A timeout returns exit code 124 instead of raising, so it takes the same
    failure path as any other non-zero exit.
    """
    argv = [tool, *args]
    try:
        return subprocess.run(
            argv,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(argv, _TIMED_OUT, f"timed out after {_TIMEOUT_SECONDS}s")


def _run(args: list[str]) -> int:
    """Run a git command and report failures. Returns the git exit code."""
    result = _exec("git", args)
    if result.returncode != 0:
        print(f"ERROR: git {' '.join(args)} failed:", file=sys.stderr)
        print(result.stdout, file=sys.stderr)
    return result.returncode


def dirty(paths: list[str]) -> bool:
    """Return True when `git status --porcelain` reports changes under paths."""
    result = _exec("git", ["status", "--porcelain", "--", *paths])
    if result.returncode != 0:
        raise RuntimeError(f"git status failed: {result.stdout}")
    return bool(result.stdout.strip())


def _is_pr_row(row: object) -> bool:
    """Return True when `row` carries a url and a boolean isCrossRepository."""
    return isinstance(row, dict) and "url" in row and isinstance(row.get("isCrossRepository"), bool)


def open_pr_url(branch: str, base: str) -> str | None:
    """Return the URL of the open same-repository pull request from `branch` into `base`.

    `gh pr list --head` matches the head ref name only, so a fork pull request
    that reuses the branch name would match too and stop the job for good.
    Rows with `isCrossRepository` true are ignored. Raises GhError when
    `gh` cannot answer, or the page is full, so a lookup failure or a truncated
    list is never read as "no pull request".
    """
    result = _exec(
        "gh",
        [
            "pr",
            "list",
            "--head",
            branch,
            "--base",
            base,
            "--state",
            "open",
            "--limit",
            str(_PR_LIST_LIMIT),
            "--json",
            "url,isCrossRepository",
        ],
    )
    if result.returncode != 0:
        raise GhError(f"gh pr list failed: {result.stdout}")
    try:
        rows = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise GhError(f"gh pr list gave unparseable output: {result.stdout!r}") from exc
    if not isinstance(rows, list) or not all(_is_pr_row(row) for row in rows):
        raise GhError(f"gh pr list gave an unexpected shape: {result.stdout!r}")
    if len(rows) >= _PR_LIST_LIMIT:
        raise GhError(f"gh pr list may be truncated at {_PR_LIST_LIMIT} rows")
    own = [r for r in rows if not r["isCrossRepository"]]
    return str(own[0]["url"]) if own else None


def remote_branch_exists(branch: str) -> bool:
    """Return True when `origin` holds `branch`. Raises RuntimeError on a git failure."""
    result = _exec("git", ["ls-remote", "--exit-code", "origin", f"refs/heads/{branch}"])
    if result.returncode == 0:
        return True
    if result.returncode == _LS_REMOTE_NO_MATCH:
        return False
    raise RuntimeError(f"git ls-remote failed: {result.stdout}")


def pr_body(paths: list[str], issue: str) -> str:
    """Build the pull request body. `## Changes` lists exactly the staged paths."""
    changes = "\n".join(f"- `{path}`" for path in paths)
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
        f"| **Issue** | Refs #{issue} | Scheduled workflow output |",
        "",
        "## Changes",
        "",
        changes,
        "",
        "## Type of Change",
        "",
        "- [x] Infrastructure/CI change",
        "",
        "## Related Issues",
        "",
        f"Refs #{issue}",
    ]
    return "\n".join(lines) + "\n"


def _message_flags(messages: list[str]) -> list[str]:
    """Map each message paragraph to its own `-m` flag, in order."""
    return [flag for message in messages for flag in ("-m", message)]


def checkout_is_on_base(base: str) -> bool:
    """Return True when HEAD is an ancestor of `origin/<base>`.

    Raises RuntimeError when git cannot answer, so a failed check is never read
    as "on base".
    """
    result = _exec("git", ["merge-base", "--is-ancestor", "HEAD", f"origin/{base}"])
    if result.returncode in (0, 1):
        return result.returncode == 0
    raise RuntimeError(f"git merge-base failed: {result.stdout}")


def publish(args: argparse.Namespace, changed: list[str]) -> int:
    """Commit on the bot branch, push it, and open the pull request."""
    if not checkout_is_on_base(args.base):
        print(
            f"ERROR: HEAD is not an ancestor of origin/{args.base}; "
            "refusing to publish its commits",
            file=sys.stderr,
        )
        return EXIT_USAGE
    existing = open_pr_url(args.branch, args.base)
    if existing:
        notice = f"Open pull request still tracks {args.branch}: {existing}"
        print(f"::notice title=Stats update skipped::{notice}")
        print(f"outcome=skipped branch={args.branch} pr={existing}")
        return EXIT_SUCCESS

    if remote_branch_exists(args.branch):
        print(f"Deleting stale remote branch {args.branch} (no open pull request)")
        if _run(["push", "origin", "--delete", args.branch]) != 0:
            return EXIT_GIT_FAILED

    for command in (
        ["checkout", "-B", args.branch],
        ["add", "--", *changed],
        ["commit", *_message_flags(args.message)],
        ["push", "--set-upstream", "origin", args.branch],
    ):
        if _run(command) != 0:
            return EXIT_GIT_FAILED

    print(f"Pushed {args.branch}; staged {len(changed)} of {len(args.path)} path(s)")
    created = _exec(
        "gh",
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
            pr_body(changed, args.issue),
        ],
    )
    if created.returncode != 0:
        raise GhError(
            f"gh pr create failed: {created.stdout}\n"
            f"Branch {args.branch} is already pushed; the next run deletes and recreates it."
        )
    # stderr is merged into stdout, so a gh warning can precede the URL.
    url = (created.stdout.strip().splitlines() or [""])[-1]
    print(f"outcome=published branch={args.branch} pr={url}")
    return EXIT_SUCCESS


_BRANCH_PATTERN = re.compile(r"automation/[A-Za-z0-9][A-Za-z0-9._/-]*")


def _bot_branch(value: str) -> str:
    """Accept only a name under `automation/`. It feeds `git push --delete`."""
    if not _BRANCH_PATTERN.fullmatch(value):
        raise argparse.ArgumentTypeError(f"{value!r} must match automation/<name>")
    return value


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
    parser.add_argument(
        "--branch",
        required=True,
        type=_bot_branch,
        help="Bot branch to publish on (automation/<name>).",
    )
    parser.add_argument("--base", default="main", help="Pull request base branch.")
    parser.add_argument("--pr-title", help="Pull request title. Defaults to the first --message.")
    parser.add_argument(
        "--issue", required=True, help="Issue number for the `Refs #N` lines in the body."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Publish the given paths through a pull request. Returns an ADR-035 code."""
    args = build_parser().parse_args(argv)

    try:
        for key, value in (("user.name", args.user_name), ("user.email", args.user_email)):
            if _run(["config", key, value]) != 0:
                return EXIT_GIT_FAILED

        changed = [path for path in args.path if dirty([path])]
        if not changed:
            print(f"No changes to commit (examined {len(args.path)} path(s))")
            print("outcome=noop")
            return EXIT_SUCCESS

        return publish(args, changed)
    except FileNotFoundError as exc:
        print(f"ERROR: git or gh not available: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except GhError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_GIT_FAILED


if __name__ == "__main__":
    sys.exit(main())

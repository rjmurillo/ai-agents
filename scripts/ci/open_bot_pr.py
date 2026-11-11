#!/usr/bin/env python3
"""Commit generated files on a bot branch and open a pull request.

Scheduled workflows cannot push to a protected default branch unless their
identity is on the ruleset bypass list (issue #7287). This script commits the
given paths on a fixed bot branch, pushes that branch, and opens a pull
request against the base branch. It replaces the earlier `commit_and_push.py`,
which pushed in place and so failed on any protected branch.

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
  - A pull request opened with `GITHUB_TOKEN` starts no `pull_request` runs. A
    human pushes a commit to the branch (an empty one will do) to start the
    required checks. Do not close the pull request: a scheduled run that finds
    no open pull request deletes the branch, and a closed pull request on a
    deleted branch cannot be reopened.
  - The branch must start with `automation/` so a caller cannot name the base or
    a human branch. The checkout must be an ancestor of `origin/<base>`, so an
    accidental `workflow_dispatch` from a feature ref cannot publish that ref's
    commits. This guards against accidents, not a hostile ref: whoever dispatches
    a ref also controls that ref's copy of this script.
  - `--artifact-dir` names a directory a download step filled. For each `--path`,
    a regular file at `<dir>/<path>` (or `<dir>/<basename>`, the layout an upload
    takes when only one file's directory is the artifact root) is copied to
    `<path>`. Nothing else in the directory is read, so a forged artifact cannot
    replace this script or any other file. A symlink source is skipped. A symlink
    destination, a source outside the directory, an oversized file, a non-UTF-8
    file, and a file with control, format, separator, combining or blank-lookalike
    characters (bidi overrides, zero-width marks) are refused. A named path with no
    usable file fails the run. A human still reads and merges the pull request; no
    CI check covers it.
  - Every git and gh call has a timeout. A timeout counts as that call failing.
  - Output carries one `outcome=noop|skipped|published` line, and a skip also
    prints a `::notice::` annotation so the run page shows a stalled update.

Authentication is the caller's job (`gh auth setup-git` and `GH_TOKEN`).

EXIT CODES (ADR-035):
  0  - Success: published, nothing to commit, or a pull request already tracks the branch
  1  - Error: a git command failed, or a precondition failed (the artifact held no
       usable file, or an entry was refused)
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
import unicodedata
from pathlib import Path

EXIT_SUCCESS = 0
EXIT_GIT_FAILED = 1
EXIT_USAGE = 2
EXIT_EXTERNAL = 3

_LS_REMOTE_NO_MATCH = 2  # `git ls-remote --exit-code`: no matching ref
_PR_LIST_LIMIT = 100
_MAX_ARTIFACT_BYTES = 1024 * 1024
_PROTECTED_PARTS = frozenset({".git", ".github"})
_LONE_CR = re.compile(r"\r(?!\n)")
_TIMEOUT_SECONDS = 120
_TIMED_OUT = 124  # the `timeout(1)` convention


class GhError(RuntimeError):
    """A `gh` call failed. The message names the operation. Maps to EXIT_EXTERNAL."""


def _exec(
    tool: str, args: list[str], *, split_stderr: bool = False
) -> subprocess.CompletedProcess[str]:
    """Run `tool args`, capturing UTF-8 text, with a timeout.

    Output is combined by default. With `split_stderr`, stdout holds only the
    tool's stdout, so a warning on stderr cannot corrupt a JSON parse. A timeout
    returns exit code 124 instead of raising, so it takes the same failure path
    as any other non-zero exit.
    """
    argv = [tool, *args]
    try:
        return subprocess.run(
            argv,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE if split_stderr else subprocess.STDOUT,
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


def dirty(path: str) -> bool:
    """Return True when `git status --porcelain` reports changes under `path`."""
    result = _exec("git", ["status", "--porcelain", "--", path])
    if result.returncode != 0:
        raise RuntimeError(f"git status failed: {result.stdout}")
    return bool(result.stdout.strip())


def _is_pr_row(row: object) -> bool:
    """Return True when `row` carries a url and a boolean isCrossRepository."""
    return isinstance(row, dict) and "url" in row and isinstance(row.get("isCrossRepository"), bool)


def open_pr_url(branch: str) -> str | None:
    """Return the URL of the open same-repository pull request from `branch`, into any base.

    The base is not filtered: a human pull request from this branch into another
    base must block the stale-branch delete, because deleting the head closes it.

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
            "--state",
            "open",
            "--limit",
            str(_PR_LIST_LIMIT),
            "--json",
            "url,isCrossRepository",
        ],
        split_stderr=True,
    )
    if result.returncode != 0:
        raise GhError(f"gh pr list failed: {result.stdout}{result.stderr or ''}")
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


_HIDDEN_CATEGORIES = frozenset({"Cc", "Cf", "Zl", "Zp", "Mn", "Me", "Co", "Cs"})
# Letters and symbols that render blank: Hangul fillers and the empty braille cell.
_BLANK_LOOKALIKES = frozenset("\u115f\u1160\u3164\uffa0\u2800")


def _is_hidden_char(char: str) -> bool:
    """Return True for a character that can hide text from a reviewer reading the diff.

    Tab and newlines are fine. Control, format (bidi overrides, zero-width marks),
    line and paragraph separators, combining and variation marks, and private-use
    and surrogate code points are refused, as are the blank lookalikes above. A
    lone carriage return is refused by the caller: a terminal redraws the line.
    """
    if char in "\n\r\t":
        return False
    return char in _BLANK_LOOKALIKES or unicodedata.category(char) in _HIDDEN_CATEGORIES


def _copy_artifact_file(source: Path, root: Path, destination: Path) -> bool:
    """Copy `source` to `destination` when it is a regular file inside `root`.

    A symlink or non-regular source is skipped (returns False). An escaping
    source, an oversized or non-UTF-8 file, a symlink destination, and a
    destination outside the checkout raise before anything is written.
    """
    if source.is_symlink() or not source.is_file():
        return False
    if not source.resolve().is_relative_to(root):
        raise RuntimeError(f"artifact entry escapes its directory: {source}")
    if source.stat().st_size > _MAX_ARTIFACT_BYTES:
        raise RuntimeError(f"artifact file is over {_MAX_ARTIFACT_BYTES} bytes: {source}")
    data = source.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"artifact file is not UTF-8: {source}") from exc
    hidden = sorted({c for c in text if _is_hidden_char(c)})
    if _LONE_CR.search(text):
        hidden.append("\r")
    if hidden:
        names = ", ".join(f"U+{ord(c):04X}" for c in hidden[:5])
        raise RuntimeError(f"artifact file holds control or format characters ({names}): {source}")
    if destination.is_symlink():
        raise RuntimeError(f"refusing to write through a symlink: {destination}")
    if not destination.parent.resolve().is_relative_to(Path.cwd().resolve()):
        raise RuntimeError(f"destination leaves the checkout: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return True


def import_artifact(artifact_dir: str, paths: list[str]) -> list[str]:
    """Copy each allowlisted `paths` entry from `artifact_dir` into the checkout.

    Only the named paths are read. The artifact may hold anything else; it is
    ignored. A path is taken from `<dir>/<path>` (two-file upload, rooted at the
    repository) or `<dir>/<basename>` (one-file upload, rooted at its directory).
    Raises RuntimeError on a symlink destination, an escaping source, an
    oversized or non-UTF-8 file, or an I/O failure. A symlink source is skipped.
    """
    root = Path(artifact_dir).resolve()
    imported: list[str] = []
    try:
        for path in paths:
            for source in (root / path, root / Path(path).name):
                if _copy_artifact_file(source, root, Path(path)):
                    imported.append(path)
                    break
    except OSError as exc:
        raise RuntimeError(f"artifact import failed: {exc}") from exc
    print(f"Imported {len(imported)} of {len(paths)} path(s) from the artifact")
    return imported


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
    existing = open_pr_url(args.branch)
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


_BRANCH_PATTERN = re.compile(r"automation/[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)*")


def _bot_branch(value: str) -> str:
    """Accept only a name under `automation/`. It feeds `git push --delete`."""
    parts = value.split("/")
    if (
        not _BRANCH_PATTERN.fullmatch(value)
        or ".." in value
        or any(part.endswith((".", ".lock")) for part in parts)
    ):
        raise argparse.ArgumentTypeError(f"{value!r} must be a valid automation/<name> ref")
    return value


def _issue_number(value: str) -> str:
    """Accept only digits, so the value cannot reshape the pull request body."""
    if not value.isascii() or not value.isdigit():
        raise argparse.ArgumentTypeError(f"{value!r} must be an issue number")
    return value


def _repo_path(value: str) -> str:
    """Accept only a relative path that stays inside the checkout."""
    path = Path(value)
    if not value or path.is_absolute() or ".." in path.parts or _PROTECTED_PARTS & set(path.parts):
        raise argparse.ArgumentTypeError(
            f"{value!r} must be a relative path inside the checkout, outside .git and .github"
        )
    return value


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the bot pull request helper."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--path",
        action="append",
        required=True,
        type=_repo_path,
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
    parser.add_argument(
        "--artifact-dir",
        help="Directory a download step filled; each --path is copied from it first.",
    )
    parser.add_argument("--pr-title", help="Pull request title. Defaults to the first --message.")
    parser.add_argument(
        "--issue",
        required=True,
        type=_issue_number,
        help="Issue number for the `Refs #N` lines in the body.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Publish the given paths through a pull request. Returns an ADR-035 code."""
    args = build_parser().parse_args(argv)

    try:
        for key, value in (("user.name", args.user_name), ("user.email", args.user_email)):
            if _run(["config", key, value]) != 0:
                return EXIT_GIT_FAILED

        if args.artifact_dir:
            imported = import_artifact(args.artifact_dir, args.path)
            missing = [path for path in args.path if path not in imported]
            if missing:
                raise RuntimeError(
                    f"the artifact is missing named paths: {', '.join(missing)}; its layout "
                    "changed or it was replaced, so nothing can be published"
                )
        changed = [path for path in args.path if dirty(path)]
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

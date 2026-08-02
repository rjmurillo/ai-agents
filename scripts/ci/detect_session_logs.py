"""Select the session logs in a pull request that are subject to validation.

Two filters apply. The path pattern keeps only real session logs: tally files
such as ``STEP-0-METRICS.md`` live in the same directory and are not sessions.
The date cutoff keeps only logs written after the Session End checklist
requirement landed (issue #215); older logs predate the rule and cannot satisfy
it retroactively.

Writes ``has_sessions`` and ``session_files`` (a JSON array, consumed as a
matrix) to ``GITHUB_OUTPUT``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

_SESSION_RE = re.compile(r"^\.agents/sessions/\d{4}-\d{2}-\d{2}-session-\d+.*\.(?:md|json)$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


class GhApiError(RuntimeError):
    """The files API could not be read."""


def changed_files(repo: str, pr_number: str) -> list[str]:
    """Return every file in the PR, from the files API.

    ``gh pr diff`` truncates on large pull requests (issue #468); the files API
    paginates instead.

    Raises ``GhApiError`` when the API call fails. The shell original piped
    ``gh api`` into ``grep ... || true``, so a failed call produced an empty
    list and the gate reported "no session files changed" -- a silent pass on
    an unreadable pull request. An unreadable pull request is unknown, not
    clean.
    """
    completed = _run(
        [
            "gh",
            "api",
            f"repos/{repo}/pulls/{pr_number}/files",
            "--paginate",
            "--jq",
            ".[].filename",
        ]
    )
    if completed.returncode != 0:
        raise GhApiError(completed.stderr.strip() or "gh api returned no diagnostics")
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def session_logs(paths: list[str]) -> list[str]:
    """Keep only paths that name a session log."""
    return [path for path in paths if _SESSION_RE.match(path)]


def partition_by_cutoff(paths: list[str], cutoff: str) -> tuple[list[str], list[str]]:
    """Split session logs into (validate, skip) around the cutoff date.

    A filename whose leading 10 characters are not a date is validated rather
    than skipped: an unparseable name is a reason to look, not to look away.
    """
    validate: list[str] = []
    skip: list[str] = []
    for path in paths:
        stamp = Path(path).name[:10]
        if _DATE_RE.match(stamp) and stamp < cutoff:
            skip.append(path)
        else:
            validate.append(path)
    return validate, skip


def _emit(has_sessions: bool, files: list[str]) -> None:
    output = os.environ.get("GITHUB_OUTPUT")
    if not output:
        return
    with open(output, "a", encoding="utf-8") as handle:
        handle.write(f"has_sessions={'true' if has_sessions else 'false'}\n")
        handle.write(f"session_files={json.dumps(files, separators=(',', ':'))}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=os.environ.get("GH_REPO", ""))
    parser.add_argument("--pr-number", default=os.environ.get("PR_NUMBER", ""))
    parser.add_argument("--cutoff", default=os.environ.get("CUTOFF_DATE", ""))
    args = parser.parse_args(argv)

    if not args.repo or not args.pr_number or not args.cutoff:
        print("::error::repo, pr-number and cutoff are all required", file=sys.stderr)
        return 2

    try:
        found = session_logs(changed_files(args.repo, args.pr_number))
    except GhApiError as exc:
        print(f"::error::Cannot enumerate pull request files: {exc}", file=sys.stderr)
        return 3
    if not found:
        print("No session files changed")
        _emit(False, [])
        return 0

    print("All changed session files:")
    for path in found:
        print(path)

    validate, skipped = partition_by_cutoff(found, args.cutoff)

    if skipped:
        print("")
        print(f"Skipped historical sessions (before {args.cutoff}):")
        for path in skipped:
            print(path)

    if not validate:
        print("")
        print("No validatable session files (all historical)")
        _emit(False, [])
        return 0

    print("")
    print("Session files to validate:")
    for path in validate:
        print(path)
    _emit(True, validate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

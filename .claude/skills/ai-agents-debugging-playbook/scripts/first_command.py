#!/usr/bin/env python3
"""First commands for the shared-checkout rows of the debugging playbook.

`stash` classifies each `git stash list` entry as own or foreign. An entry is
foreign when its WIP branch is not checked out in any worktree of this clone.
`lag` reports the left and right commit counts of `origin/main...HEAD`.
Neither subcommand fetches or mutates anything. Run `git fetch origin main`
first when the lag number must be current.

Exit codes: 0 ok, 1 findings (a foreign stash, or left count above zero),
2 bad arguments or not a git repository, 3 git missing or failed.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

_STASH_RE = re.compile(r"^(?:WIP on|On) (?P<branch>[^:]+): ")


class GitError(Exception):
    """git is missing or a git command failed."""


def _git(repo: Path, *args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
        )
    except OSError as exc:
        raise GitError(f"git failed to start: {exc}") from exc
    if proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} exited {proc.returncode}: {proc.stderr.strip()}")
    return proc.stdout


def checked_out_branches(repo: Path) -> set[str]:
    """Branch names checked out in any worktree of this clone."""
    out = _git(repo, "worktree", "list", "--porcelain")
    prefix = "branch refs/heads/"
    return {ln[len(prefix) :] for ln in out.splitlines() if ln.startswith(prefix)}


def classify_stashes(repo: Path) -> dict:
    live = checked_out_branches(repo)
    out = _git(repo, "stash", "list", "--format=%gd%x09%gs")
    entries = []
    for ln in out.splitlines():
        ref, _, subject = ln.partition("\t")
        m = _STASH_RE.match(subject)
        branch = m.group("branch") if m else None
        if branch is None:
            status = "unknown"
        elif branch in live:
            status = "own"
        else:
            status = "foreign"
        entries.append({"ref": ref, "branch": branch, "subject": subject, "status": status})
    foreign = [e["ref"] for e in entries if e["status"] == "foreign"]
    return {
        "stashes": entries,
        "foreign": foreign,
        "worktree_branches": sorted(live),
        "examined": len(entries),
    }


def base_lag(repo: Path, base: str = "origin/main") -> dict:
    out = _git(
        repo, "rev-list", "--left-right", "--count", "--end-of-options", f"{base}...HEAD"
    ).split()
    if len(out) != 2:
        raise GitError(f"unexpected rev-list output: {out!r}")
    left, right = int(out[0]), int(out[1])
    return {"base": base, "left": left, "right": right, "examined": 1}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--repo", default=".", help="repository root (default: .)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("stash", help="classify each stash entry as own or foreign")
    lag = sub.add_parser("lag", help="left/right counts of BASE...HEAD")
    lag.add_argument("--base", default="origin/main")
    a = p.parse_args(argv)
    repo = Path(a.repo).resolve()
    if not repo.is_dir():
        print(json.dumps({"error": f"not a directory: {repo}"}), file=sys.stderr)
        return 2
    if a.cmd == "lag" and a.base.startswith("-"):
        print(json.dumps({"error": f"--base must not start with '-': {a.base}"}), file=sys.stderr)
        return 2
    try:
        if a.cmd == "stash":
            result = classify_stashes(repo)
            findings = bool(result["foreign"])
        else:
            result = base_lag(repo, a.base)
            findings = result["left"] > 0
    except GitError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 3
    print(json.dumps(result, indent=2))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())

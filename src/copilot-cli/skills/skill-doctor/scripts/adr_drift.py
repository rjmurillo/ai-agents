#!/usr/bin/env python3
"""Check a git repository's ADRs for drift: numbering, links, and git history.

Subcommands:

  locate --repo PATH
      Print JSON: ADR folders and their convention, `primary` (the folder when
      exactly one exists, else null), `next_number`, `template_headings`, and
      `markers`. Reads only.

  scan --repo PATH --out FILE [--max-commits N] [--since DATE]
      Run the numbering, link, supersession, cited-path, and git-history checks
      and write one JSON result to FILE. FILE must be outside the repository.
      Reads git history and working-tree ADR files. Never uses the network.

Exit codes: 0 ok, 2 bad arguments, unreadable input, `--out` not allowed, or not
a git repository, 3 a git command failed.

python3, stdlib only.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from adr_checks import (
    check_cited_paths,
    check_links,
    check_numbering,
    check_supersession,
)
from adr_corpus import (
    GROUPS,
    SETUP,
    AdrDoc,
    Finding,
    GitError,
    find_adr_dirs,
    locate,
    make_finding,
    read_docs,
    run_git,
    within,
)
from adr_history import head_commit, history_findings, read_commits

SCHEMA_VERSION = 1
DEFAULT_MAX_COMMITS = 300
GROUP_ORDER = {group: index for index, group in enumerate(GROUPS)}


class ExitError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def repo_root(path_arg: str) -> Path:
    """Resolve the git top level for PATH. Exit 2 when it is not a repository."""
    path = Path(path_arg).expanduser()
    if not path.is_dir():
        raise ExitError(2, f"--repo {path_arg} is not a directory")
    if shutil.which("git") is None:
        raise ExitError(3, "git is not on PATH")
    try:
        top = run_git(path, ["rev-parse", "--show-toplevel"]).strip()
    except GitError as exc:
        if exc.timed_out:
            raise ExitError(3, f"git could not read {path_arg}: {exc}") from exc
        raise ExitError(2, f"{path_arg} is not a git repository ({exc})") from exc
    return Path(top).resolve()


def _sort_key(finding: Finding) -> tuple[Any, ...]:
    evidence = finding["evidence"]
    where = str(evidence.get("path") or evidence.get("sha") or "")
    return (
        GROUP_ORDER.get(finding["group"], 9),
        finding["kind"],
        where,
        evidence.get("line") or 0,
        finding["id"],
    )


def _counts(findings: Sequence[Finding]) -> dict[str, Any]:
    by_kind: dict[str, int] = {}
    by_group: dict[str, int] = {}
    for finding in findings:
        by_kind[finding["kind"]] = by_kind.get(finding["kind"], 0) + 1
        by_group[finding["group"]] = by_group.get(finding["group"], 0) + 1
    return {"total": len(findings), "by_kind": by_kind, "by_group": by_group}


def _no_directory_finding() -> Finding:
    fix = "Create docs/adr/ and record the decisions the repository has already made there."
    return make_finding(
        "no-adr-directory",
        SETUP,
        "info",
        "deterministic",
        {"searched": "known ADR folders"},
        fix,
        ("none",),
    )


def _history(repo: Path, args: argparse.Namespace, docs: Sequence[AdrDoc]) -> dict[str, Any]:
    head = head_commit(repo)
    if head is None:
        return {"head": None, "examined": 0, "truncated": False, "findings": []}
    commits, truncated = read_commits(repo, args.max_commits, args.since)
    return {
        "head": head,
        "examined": len(commits),
        "truncated": truncated,
        "findings": history_findings(commits, docs),
    }


def run_scan(args: argparse.Namespace) -> int:
    if args.max_commits < 1:
        raise ExitError(2, "--max-commits must be at least 1")
    repo = repo_root(args.repo)
    out = Path(args.out).expanduser().resolve()
    if within(out, repo):
        raise ExitError(2, f"--out {args.out} is inside the repository; scan never writes there")
    dirs, markers = find_adr_dirs(repo)
    docs = read_docs(dirs)
    findings: list[Finding] = [] if dirs else [_no_directory_finding()]
    findings += check_numbering(dirs, docs) + check_links(docs, dirs)
    findings += check_supersession(docs) + check_cited_paths(repo, docs)
    try:
        history = _history(repo, args, docs)
    except GitError as exc:
        raise ExitError(3, str(exc)) from exc
    findings += history["findings"]
    findings.sort(key=_sort_key)
    result = {
        "schema_version": SCHEMA_VERSION,
        "repo": str(repo),
        "head": history["head"],
        "examined": history["examined"],
        "truncated": history["truncated"],
        "max_commits": args.max_commits,
        "since": args.since,
        "locate": locate(repo, dirs, markers),
        "findings": findings,
        "counts": _counts(findings),
    }
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise ExitError(2, f"cannot write {args.out}: {exc}") from exc
    print(
        f"adr drift: {result['counts']['total']} finding(s), {result['examined']} commit(s) examined: {out}"
    )
    return 0


def run_locate(args: argparse.Namespace) -> int:
    repo = repo_root(args.repo)
    dirs, markers = find_adr_dirs(repo)
    print(json.dumps(locate(repo, dirs, markers), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    loc = sub.add_parser("locate", help="print ADR folders and conventions as JSON")
    loc.add_argument("--repo", default=".", metavar="PATH", help="repository path (default: .)")
    scan = sub.add_parser("scan", help="check numbering, links, and history; write JSON to --out")
    scan.add_argument("--repo", default=".", metavar="PATH", help="repository path (default: .)")
    scan.add_argument(
        "--out", required=True, metavar="FILE", help="result file, outside the repository"
    )
    scan.add_argument(
        "--max-commits",
        type=int,
        default=DEFAULT_MAX_COMMITS,
        metavar="N",
        help=f"commits to read from HEAD (default {DEFAULT_MAX_COMMITS})",
    )
    scan.add_argument("--since", metavar="DATE", help="only commits after DATE (git --since)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {"locate": run_locate, "scan": run_scan}
    try:
        return handlers[args.command](args)
    except ExitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main())

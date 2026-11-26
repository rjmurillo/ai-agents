#!/usr/bin/env python3
"""Check a git repository's ADRs for drift: numbering, links, and git history.

Subcommands:

  locate --repo PATH
      Print JSON: ADR folders and their convention, `primary` (the folder when
      exactly one exists, else null), `next_number`, `template_headings`,
      `markers`, `rejected`, and `read_errors`. Reads only.

  scan --repo PATH --out FILE [--max-commits N] [--since DATE]
      Run the numbering, link, supersession, cited-path, and git-history checks
      and write one JSON result to FILE. FILE must be outside the repository.
      Reads git history and working-tree ADR files. Never uses the network.

Exit codes: 0 ok, 2 bad arguments, unreadable input, `--out` not allowed, a
result over 5,000,000 bytes, or not a git repository, 3 a git command failed,
timed out, or could not run (git not on PATH).

python3, stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
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
    AdrDoc,
    Finding,
    find_adr_dirs,
    locate,
    make_finding,
    path_exists,
    path_is_dir,
    read_docs,
    within,
)
from adr_git import GitError, partial_clone_refusal, run_git
from adr_history import head_commit, history_findings, read_commits
from adr_text import GROUPS, SCAN_MAX_BYTES, SETUP

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
    if not path_is_dir(path):
        raise ExitError(2, f"--repo {path_arg} is not a directory")
    if shutil.which("git") is None:
        raise ExitError(3, "git is not on PATH")
    try:
        top = run_git(path, ["rev-parse", "--show-toplevel"]).strip()
    except GitError as exc:
        if exc.timed_out:
            raise ExitError(3, f"git could not read {path_arg}: {exc}") from exc
        raise ExitError(2, f"{path_arg} is not a git repository ({exc})") from exc
    root = Path(top).resolve()
    # A `core.worktree` setting in the scanned repository's own config can point
    # the top level at any folder, a parent or `/` included. Every containment
    # check anchors on this root. So walk up from the named folder to the nearest
    # one that holds a `.git` entry (a folder, or a file in linked worktrees and
    # submodules), and require git's top level to be exactly that folder.
    start = path.resolve()
    holder = next((p for p in (start, *start.parents) if path_exists(p / ".git")), None)
    if holder is None:
        raise ExitError(2, f"{path_arg} has no .git entry in it or any parent folder")
    if holder != root:
        raise ExitError(2, f"{path_arg} reports a git top level outside itself ({root})")
    return root


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


def _write_json(out: Path, text: str) -> None:
    """Write TEXT to a temp file beside OUT, then replace OUT, so a failure leaves no partial file."""
    out.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=out.parent, prefix=f".{out.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(temp_name, out)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def run_scan(args: argparse.Namespace) -> int:
    if args.max_commits < 1:
        raise ExitError(2, "--max-commits must be at least 1")
    repo = repo_root(args.repo)
    out = Path(args.out).expanduser().resolve()
    if within(out, repo):
        raise ExitError(2, f"--out {args.out} is inside the repository; scan never writes there")
    try:
        refusal = partial_clone_refusal(repo)
    except GitError as exc:
        raise ExitError(3, str(exc)) from exc
    if refusal is not None:
        raise ExitError(2, refusal)
    survey = find_adr_dirs(repo)
    docs = read_docs(survey)
    findings: list[Finding] = []
    if not survey.dirs and not survey.read_errors and not survey.adrs_refused:
        findings.append(_no_directory_finding())
    findings += check_numbering(survey.dirs, docs) + check_links(docs, survey.dirs)
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
        "locate": locate(repo, survey),
        "read_errors": survey.read_errors,
        "findings": findings,
        "counts": _counts(findings),
    }
    text = json.dumps(result, indent=2) + "\n"
    size = len(text.encode("utf-8"))
    if size > SCAN_MAX_BYTES:
        raise ExitError(
            2,
            f"scan result is {size} bytes, over the {SCAN_MAX_BYTES}-byte limit the renderer "
            "reads; narrow it with --since or --max-commits",
        )
    try:
        _write_json(out, text)
    except OSError as exc:
        raise ExitError(2, f"cannot write {args.out}: {exc}") from exc
    print(
        f"adr drift: {result['counts']['total']} finding(s), {result['examined']} commit(s) "
        f"examined, truncated: {str(result['truncated']).lower()}, "
        f"read_errors: {len(survey.read_errors)}, rejected: {len(survey.rejected)}: {out}"
    )
    return 0


def run_locate(args: argparse.Namespace) -> int:
    repo = repo_root(args.repo)
    survey = find_adr_dirs(repo)
    result = {**locate(repo, survey), "read_errors": survey.read_errors}
    print(json.dumps(result, indent=2))
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

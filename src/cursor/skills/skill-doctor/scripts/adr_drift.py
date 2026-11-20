#!/usr/bin/env python3
"""Find ADR drift in a git repository, and draft ADRs for undocumented decisions.

Subcommands:

  locate --repo PATH
      Print JSON: ADR folders and their convention, `primary` (the one folder to
      write to, or null), `next_number` (informational), `template_headings`,
      and `markers`. Reads only.

  scan --repo PATH --out FILE [--max-commits N] [--since DATE]
       [--prs-json FILE] [--with-align]
      Run the numbering, link, supersession, cited-path, and git-history checks
      and write one JSON result to FILE. FILE must be outside the repository.
      Reads git history and working-tree ADR files. Never uses the network.
      `--prs-json` takes the list shape `bootstrap_mine.py --prs-json` reads.
      `--with-align` is the opt-in to run `align adr` (see references/adr-drift.md).

  draft --scan FILE --id ID --out DIR [--status Proposed]
      Write one ADR draft for an `undocumented-decision` finding. The number is
      assigned at write time. Inside the repository, DIR must be an ADR folder.
      An existing target is never replaced.

Exit codes: 0 ok, 1 logic error or `draft` target exists, 2 bad arguments,
unreadable input, `--out` not allowed, or not a git repository, 3 a git command
failed.

python3, stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from adr_checks import (
    NUMBERING,
    check_cited_paths,
    check_links,
    check_numbering,
    check_supersession,
)
from adr_corpus import (
    Finding,
    GitError,
    find_adr_dirs,
    locate,
    make_finding,
    read_docs,
    run_git,
    within,
)
from adr_draft import DraftError, write_draft
from adr_history import history_findings, pr_number_of, read_commits, read_prs

SCHEMA_VERSION = 1
DEFAULT_MAX_COMMITS = 300
ALIGN_TIMEOUT_SECONDS = 60
ALIGN_TEXT_CAP = 20000
ALIGN_HINT = "DO_NOT_TRACK=1 align adr"
ALIGN_NOTE = (
    "advisory; align does not recognize `ADR-NNN-slug.md` naming or "
    "ADR folders outside its own list"
)
GROUP_ORDER = {"Numbering": 0, "Links": 1, "History": 2}


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
        raise ExitError(2, f"{path_arg} is not a git repository ({exc})") from exc
    return Path(top).resolve()


def align_result(repo: Path, with_align: bool) -> dict[str, Any]:
    """Detect align, and run `align adr` only with the opt-in and an existing graph."""
    result: dict[str, Any] = {
        "status": "absent",
        "version": None,
        "text": "",
        "exit_code": None,
        "command_hint": ALIGN_HINT,
        "advisory_note": ALIGN_NOTE,
    }
    exe = shutil.which("align")
    if exe is None:
        return result
    if not with_align:
        return {**result, "status": "detected"}
    if not (Path(os.path.expanduser("~")) / ".align" / "local.db").is_file():
        return {**result, "status": "no_graph"}
    env = dict(os.environ)
    env["DO_NOT_TRACK"] = "1"
    try:
        proc = subprocess.run(
            [exe, "adr"],
            cwd=str(repo),
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=ALIGN_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {**result, "status": "failed", "text": f"timed out after {ALIGN_TIMEOUT_SECONDS} s"}
    except OSError as exc:
        return {**result, "status": "failed", "text": f"could not run align: {exc}"}
    if proc.returncode != 0:
        tail = proc.stderr.strip()[-2000:]
        return {**result, "status": "failed", "exit_code": proc.returncode, "text": tail}
    return {**result, "status": "ran", "exit_code": 0, "text": proc.stdout[:ALIGN_TEXT_CAP]}


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
    fix = (
        "Create docs/adr/ and record decisions there. `draft` can seed the first records "
        "from the history findings."
    )
    return make_finding(
        "no-adr-directory",
        NUMBERING,
        "info",
        "deterministic",
        {"searched": "known ADR folders"},
        fix,
        ("none",),
    )


def _history(
    repo: Path, args: argparse.Namespace, dirs: Any, docs: Any, prs: dict[int, Any]
) -> dict[str, Any]:
    try:
        head = run_git(repo, ["rev-parse", "--verify", "--quiet", "HEAD^{commit}"]).strip()
    except GitError:
        return {
            "head": None,
            "examined": 0,
            "truncated": False,
            "findings": [],
            "suppressed": 0,
            "matched": 0,
        }
    commits, truncated = read_commits(repo, args.max_commits, args.since)
    findings, suppressed = history_findings(repo, dirs, docs, commits, prs)
    matched = sum(1 for c in commits if pr_number_of(c) in prs)
    return {
        "head": head,
        "examined": len(commits),
        "truncated": truncated,
        "findings": findings,
        "suppressed": suppressed,
        "matched": matched,
    }


def run_scan(args: argparse.Namespace) -> int:
    if args.max_commits < 1:
        raise ExitError(2, "--max-commits must be at least 1")
    repo = repo_root(args.repo)
    out = Path(args.out).expanduser().resolve()
    if within(out, repo):
        raise ExitError(2, f"--out {args.out} is inside the repository; scan never writes there")
    try:
        prs = read_prs(args.prs_json) if args.prs_json else {}
    except ValueError as exc:
        raise ExitError(2, str(exc)) from exc
    dirs, _ = find_adr_dirs(repo)
    docs = read_docs(dirs)
    findings: list[Finding] = [] if dirs else [_no_directory_finding()]
    findings += check_numbering(dirs, docs) + check_links(docs, dirs)
    findings += check_supersession(docs, dirs) + check_cited_paths(repo, docs)
    try:
        history = _history(repo, args, dirs, docs, prs)
    except GitError as exc:
        raise ExitError(3, str(exc)) from exc
    findings += history["findings"]
    findings.sort(key=_sort_key)
    for finding in findings:
        if finding["fix"]:
            finding["fix"] = [str(out) if p == "<SCAN_JSON>" else p for p in finding["fix"]]
    result = {
        "schema_version": SCHEMA_VERSION,
        "repo": str(repo),
        "head": history["head"],
        "examined": history["examined"],
        "truncated": history["truncated"],
        "max_commits": args.max_commits,
        "since": args.since,
        "locate": locate(repo),
        "findings": findings,
        "counts": _counts(findings),
        "suppressed": history["suppressed"],
        "prs_json": {"items": len(prs), "matched": history["matched"]} if args.prs_json else None,
        "align": align_result(repo, args.with_align),
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
    print(json.dumps(locate(repo_root(args.repo)), indent=2))
    return 0


def run_draft(args: argparse.Namespace) -> int:
    try:
        written = write_draft(args.scan, args.id, args.out, args.status)
    except DraftError as exc:
        raise ExitError(exc.code, str(exc)) from exc
    print(json.dumps(written))
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
    scan.add_argument("--prs-json", metavar="FILE", help="caller-supplied PR export (JSON list)")
    scan.add_argument(
        "--with-align",
        action="store_true",
        help="opt in to running `align adr` when align and its graph exist",
    )
    draft = sub.add_parser("draft", help="write one ADR draft for a scan finding")
    draft.add_argument("--scan", required=True, metavar="FILE", help="scan result from `scan`")
    draft.add_argument("--id", required=True, metavar="ID", help="finding id to draft")
    draft.add_argument("--out", required=True, metavar="DIR", help="folder for the draft")
    draft.add_argument("--status", default="Proposed", help="status text (default Proposed)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {"locate": run_locate, "scan": run_scan, "draft": run_draft}
    try:
        return handlers[args.command](args)
    except ExitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main())

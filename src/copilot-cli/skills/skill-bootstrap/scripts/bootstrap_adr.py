#!/usr/bin/env python3
# Port of aligndottech/align-cli at commit 8d758e9899677b61442b08ffda74b74887bfc42a
# Ported upstream files: src/commands/adr.ts (the list-then-accept flow, lines 25-48) and,
#   through the sibling modules, src/lib/adr-writer.ts, src/lib/first-run-pr-import.ts and
#   src/lib/fetchers/docs-decision-log.ts. This file adds the command line around them.
# Sibling ports: adr_locate.py, adr_scan.py, adr_draft.py, adr_prs.py, adr_log.py, adr_git.py.
# MIT, Copyright (c) 2026 Align Tech Ltd, see LICENSE-align
"""Find the decisions in a repository that have no ADR, and draft one ADR for each you accept.

Standard library only. Subcommands:

``locate --repo PATH``
    Print the ADR folders (path, count, prefix, width, highest number, H1 form, headings),
    the single ``primary`` folder (null for none or several), and ``next_number``.

``scan --repo PATH [--rev HEAD] [--max-commits 300] [--since DATE] [--prs-json FILE] --out FILE``
    List candidate decisions as JSON. Reads git and the working tree, makes no network call,
    and writes nothing in the repository. ``--out`` must resolve outside it. ``--prs-json`` is an
    offline export (see ``adr_prs.py`` for its shape).

``draft --scan FILE --id ID --out DIR [--status Proposed]``
    Render one candidate as an ADR and create it with mode ``x``. Inside the repository, DIR
    must be a located ADR folder and the file must not be ignored by git.

Every command prints JSON. Exit codes: 0 done; 1 the draft target exists or another ADR took
its number (``error`` is ``exists``); 2 bad arguments, unreadable or malformed input, or a
refused ``--out`` (``config`` or ``io``); 3 git is missing, failed, or timed out (``git``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from adr_draft import ExistsError, draft
from adr_git import ConfigError, GitError, repo_root
from adr_locate import locate
from adr_scan import scan

DEFAULT_MAX_COMMITS = 300

_HELP_EPILOG = """\
examples:
  %(prog)s locate --repo .
  %(prog)s scan --repo . --prs-json ~/prs.json --out ~/scan.json
  %(prog)s draft --scan ~/scan.json --id c-1a2b3c4 --out docs/adr
exit codes:
  0  done
  1  the draft target exists, or another ADR took its number
  2  bad arguments, unreadable or malformed input, or a refused --out
  3  git is missing, failed, or timed out
"""


def _positive(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        value = 0
    if value < 1:
        raise argparse.ArgumentTypeError(f"{text!r} is not a positive integer")
    return value


def _read_prs(path: str | None) -> list[Any] | None:
    if path is None:
        return None
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError) as exc:
        raise ConfigError(f"cannot read --prs-json {path}: {exc}") from exc
    if not isinstance(data, list):
        raise ConfigError(f"--prs-json {path} must hold a JSON list")
    return data


def _out_outside_repo(root: Path, out: str) -> Path:
    """Resolve ``--out`` once and refuse a path inside the repository, a directory, or an existing file."""
    target = Path(out).resolve()
    if target == root or root in target.parents:
        raise ConfigError(f"--out {target} is inside the repository {root}; write it elsewhere")
    if target.is_dir():
        raise ConfigError(f"--out {target} is a directory")
    if target.exists():
        raise ConfigError(f"--out {target} already exists; it is never overwritten")
    return target


def _write_new(target: Path, text: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(target, "x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    except FileExistsError as exc:
        raise ConfigError(f"--out {target} already exists; it is never overwritten") from exc


def _cmd_locate(args: argparse.Namespace) -> dict[str, Any]:
    return locate(repo_root(Path(args.repo)))


def _cmd_scan(args: argparse.Namespace) -> dict[str, Any]:
    root = repo_root(Path(args.repo))
    target = _out_outside_repo(root, args.out)
    if args.since is not None and args.since.startswith("-"):
        raise ConfigError(f"--since may not start with '-': {args.since!r}")
    payload = scan(root, args.rev, args.max_commits, args.since, _read_prs(args.prs_json))
    _write_new(target, json.dumps(payload, indent=2) + "\n")
    return {**payload, "out": str(target)}


def _cmd_draft(args: argparse.Namespace) -> dict[str, Any]:
    return draft(args.scan, args.id, args.out, args.status)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n", 1)[0],
        epilog=_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p_locate = sub.add_parser("locate", help="find the ADR folders")
    p_locate.add_argument("--repo", required=True)
    p_scan = sub.add_parser("scan", help="list decisions with no ADR")
    p_scan.add_argument("--repo", required=True)
    p_scan.add_argument("--rev", default="HEAD")
    p_scan.add_argument("--max-commits", type=_positive, default=DEFAULT_MAX_COMMITS)
    p_scan.add_argument("--since", metavar="DATE")
    p_scan.add_argument("--prs-json", metavar="FILE", help="offline pull request export")
    p_scan.add_argument("--out", required=True, metavar="FILE", help="outside the repository")
    p_draft = sub.add_parser("draft", help="write one ADR")
    p_draft.add_argument("--scan", required=True, metavar="FILE")
    p_draft.add_argument("--id", required=True)
    p_draft.add_argument("--out", required=True, metavar="DIR")
    p_draft.add_argument("--status", default="Proposed")
    return parser


_HANDLERS = {"locate": _cmd_locate, "scan": _cmd_scan, "draft": _cmd_draft}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = _HANDLERS[args.command](args)
    except ExistsError as exc:
        body = {"error": "exists", "message": str(exc), "path": str(exc.path), "others": exc.others}
        print(json.dumps(body))
        return 1
    except ConfigError as exc:
        print(json.dumps({"error": "config", "message": str(exc)}))
        return 2
    except GitError as exc:
        print(json.dumps({"error": "git", "message": str(exc)}))
        return 3
    except OSError as exc:
        print(json.dumps({"error": "io", "message": str(exc)}))
        return 2
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

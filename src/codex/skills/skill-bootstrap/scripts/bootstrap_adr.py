#!/usr/bin/env python3
# Port of aligndottech/align-cli at commit 8d758e9899677b61442b08ffda74b74887bfc42a
# Ported upstream files: src/commands/adr.ts (the list-then-accept flow, lines 25-48) and,
#   through the sibling modules, src/lib/first-run-pr-import.ts and
#   src/lib/fetchers/docs-decision-log.ts. This file adds the command line around them.
#   src/lib/adr-writer.ts (renderAdr, slug and writeAdr, lines 52-84 and 137-148) is ported
#   here. The trailing "Drafted by" comment of renderAdr is not ported.
# Sibling ports: adr_locate.py, adr_scan.py, adr_commits.py, adr_docs.py.
# MIT, Copyright (c) 2026 Align Tech Ltd, see LICENSE-align
"""Find the decisions in a repository that have no ADR, and draft one ADR for each you accept.

Standard library only. Subcommands:

``locate --repo PATH``
    Print the ADR folders (path, count, prefix, width, highest number, H1 form, headings),
    the single ``primary`` folder (null for none or several), and ``next_number``.

``scan --repo PATH [--rev HEAD] [--max-commits 300] [--since DATE] [--prs-json FILE] --out FILE``
    List candidate decisions as JSON. Reads git and the working tree, makes no network call,
    and writes nothing in the repository. ``--out`` must resolve outside it. ``--prs-json`` is an
    offline export (see ``adr_commits.py`` for its shape).

``draft --scan FILE --id ID --out DIR [--status Proposed]``
    Render one candidate as an ADR and create it with mode ``x``. Inside the repository, DIR
    must be a located ADR folder and the file must not be ignored by git.

Every command prints JSON. Exit codes: 0 done; 1 the draft target exists or another ADR took
its number (``error`` is ``exists``); 2 bad arguments, unreadable or malformed input, or a
refused ``--out`` (``config`` or ``io``); 3 git is missing, failed, or timed out (``git``).

Drafting an ADR from a scan candidate:

Render one candidate from a scan file as an ADR and create it. Never replaces a file.

Everything in the draft comes from the source: its title, the reason it stated, an excerpt
of its text, and a link to where it was decided. Nothing is generated, so a section the
source never covered says so.

Departures from the upstream source, each pinned by a test:

- The status is ``Proposed`` by default. A person accepts the ADR through review. Upstream
  wrote ``Accepted``.
- The H1 copies the newest ADR's form (``# ADR-123: Title``) and the file name keeps its
  prefix and zero padding. Upstream wrote ``# 123. Title`` and a bare number.
- The headings follow the newest ADR in the folder. A heading the source does not fill says
  ``Not recorded in the source.`` Upstream wrote fixed Nygard headings.
- The number is chosen at write time from the folder, then the file is created with mode
  ``x``. A name that exists is reported and never retried with another number.
- A title with no ASCII letter or digit gives the slug ``decision-<sha7>`` (or the id), not ``""``.
- A target inside the repository must be one of the located ADR folders and must not be
  ignored by git.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from adr_commits import sanitize, slugify
from adr_locate import (
    MAX_READ_BYTES,
    NOT_RECORDED,
    Style,
    adr_files,
    adr_title,
    folder_style,
    is_draft_target,
    locate,
    locate_folders,
    render,
)
from adr_scan import ConfigError, GitError, git_bytes, git_text, repo_root, scan

__all__ = [
    "DEFAULT_MAX_COMMITS",
    "NOT_RECORDED",
    "ExistsError",
    "build_parser",
    "draft",
    "load_candidate",
    "main",
    "render",
]

# ---------------------------------------------------------------------------
# ADR drafting (src/lib/adr-writer.ts)
# ---------------------------------------------------------------------------

_KINDS = frozenset({"commit", "pr", "decision-log"})
_STATUS = re.compile(r"[A-Za-z][A-Za-z -]{0,39}\Z", re.ASCII)


class ExistsError(Exception):
    """The target exists, or another ADR took the same number. Exit 1."""

    def __init__(self, message: str, path: Path, others: list[str] | None = None) -> None:
        super().__init__(message)
        self._path = path
        self._others = tuple(others or ())

    @property
    def path(self) -> Path:
        """The draft target that already existed or that this run wrote."""
        return self._path

    @property
    def others(self) -> list[str]:
        """Names of other ADRs that took the same number."""
        return list(self._others)


def _text(value: object, name: str, required: bool = False) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or (required and not value.strip()):
        raise ConfigError(f"scan file candidate field {name!r} must be a string")
    return sanitize(value)


def load_candidate(path: str, ident: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read a scan file and return ``(scan, candidate)`` for ``ident``, or raise ConfigError."""
    target = Path(path)
    try:
        if target.stat().st_size > 16 * MAX_READ_BYTES:
            raise ConfigError(f"scan file {path} is too large")
        data = json.loads(target.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError) as exc:
        raise ConfigError(f"cannot read scan file {path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("candidates"), list):
        raise ConfigError(f"scan file {path} is not a scan result")
    if not isinstance(data.get("repo"), str):
        raise ConfigError(f"scan file {path} does not name its repository")
    for item in data["candidates"]:
        if isinstance(item, dict) and item.get("id") == ident:
            return data, item
    raise ConfigError(f"no candidate with id {ident!r} in {path}")


def _clean_source(source: object) -> dict[str, Any]:
    cleaned = source if isinstance(source, dict) else {}
    return {
        key: sanitize(value) if isinstance(value, str) else value for key, value in cleaned.items()
    }


def _check_candidate(candidate: dict[str, Any]) -> None:
    if candidate.get("kind") not in _KINDS:
        raise ConfigError(f"candidate {candidate.get('id')!r} has an unknown kind")
    title = (_text(candidate.get("title"), "title", True) or "").strip()
    candidate["title"] = adr_title(candidate["kind"], title)
    for key in ("reason", "excerpt"):
        candidate[key] = _text(candidate.get(key), key)
    candidate["source"] = _clean_source(candidate.get("source"))


def _git_path(directory: Path, flag: str) -> Path | None:
    proc = git_bytes(directory, "rev-parse", flag)
    text = proc.stdout.decode("utf-8", "replace").strip()
    return (directory / text).resolve() if proc.returncode == 0 and text else None


def _gate_tree(root: Path, out_dir: Path) -> Path | None:
    """The work tree that ``out_dir`` lies in, when draft must gate on it.

    That is the scanned work tree, or another work tree of the same repository (a linked
    worktree), found by asking git where the nearest existing ancestor of ``out_dir`` lives.
    An unrelated repository or a plain folder gives None: a scratch folder.
    """
    if out_dir == root or root in out_dir.parents:
        return root
    ancestor = next((path for path in (out_dir, *out_dir.parents) if path.is_dir()), None)
    top = _git_path(ancestor, "--show-toplevel") if ancestor else None
    if ancestor is None or top is None:
        return None
    common = _git_path(ancestor, "--git-common-dir")
    return top if common is not None and common == _git_path(root, "--git-common-dir") else None


def _gate_target(root: Path, out_dir: Path) -> Path | None:
    """The work tree to gate on, or None for a scratch folder. In a work tree, ``out_dir``
    must be one of its located ADR folders."""
    tree = _gate_tree(root, out_dir)
    if tree is not None:
        allowed = {
            (tree / rel).resolve() for rel, _source in locate_folders(tree) if is_draft_target(rel)
        }
        if out_dir not in allowed:
            raise ConfigError(
                f"{out_dir} is inside the repository {tree} and is not an ADR folder that takes drafts"
            )
    return tree


def _refuse_ignored(root: Path, target: Path) -> None:
    proc = git_text(
        root, "check-ignore", "-q", "--", target.relative_to(root).as_posix(), ok=(0, 1)
    )
    if proc.returncode == 0:
        raise ConfigError(f"{target} is ignored by git; the ADR would not be committed")


def _file_name(style: Style, number: int, candidate: dict[str, Any]) -> str:
    slug = slugify(candidate["title"])
    if not slug:
        source = candidate.get("source")
        sha = source.get("sha") if isinstance(source, dict) else None
        base = f"decision-{sha[:7]}" if isinstance(sha, str) and sha else None
        slug = base or f"decision-{slugify(str(candidate['id'])) or 'unnamed'}"
    return f"{style.prefix}{number:0{style.width}d}-{slug}.md"


def draft(scan_path: str, ident: str, out: str, status: str) -> dict[str, Any]:
    """Write one ADR for candidate ``ident`` into ``out`` and return the ``draft`` payload."""
    if not _STATUS.fullmatch(status):
        raise ConfigError(f"--status {status!r} must be a short plain word or phrase")
    scan, candidate = load_candidate(scan_path, ident)
    _check_candidate(candidate)
    root = repo_root(Path(scan["repo"]))
    out_dir = Path(out).resolve()
    tree = _gate_target(root, out_dir)
    if out_dir.exists() and not out_dir.is_dir():
        raise ConfigError(f"--out {out_dir} is not a directory")
    out_dir.mkdir(parents=True, exist_ok=True)
    style = folder_style(out_dir)
    number = style.highest + 1
    target = out_dir / _file_name(style, number, candidate)
    if tree is not None:
        _refuse_ignored(tree, target)
    text = render(style, number, candidate, status)
    try:
        with open(target, "x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    except FileExistsError as exc:
        raise ExistsError(f"{target} already exists; it is never replaced", target) from exc
    twins = [
        item.name
        for item in adr_files(out_dir)
        if item.number == number and item.name != target.name
    ]
    if twins:
        raise ExistsError(f"another ADR took number {number}", target, twins)
    return {
        "path": str(target),
        "number": number,
        "id": ident,
        "status": status,
        "in_repo": tree is not None,
    }


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

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

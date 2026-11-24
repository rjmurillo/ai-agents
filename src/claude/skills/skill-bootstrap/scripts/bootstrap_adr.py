#!/usr/bin/env python3
# Port of aligndottech/align-cli at commit 8d758e9899677b61442b08ffda74b74887bfc42a
# Ported upstream files:
#   src/commands/adr.ts   (runAdr, the list-then-accept flow, lines 25-48; this file adds the
#                          command line around it)
#   src/lib/adr-writer.ts (writeAdr, lines 137-148; renderAdr and slug live in adr_locate.py
#                          and adr_commits.py. The trailing "Drafted by" comment is not ported.)
# Sibling ports: adr_shape.py, adr_reason.py, adr_commits.py, adr_docs.py, adr_locate.py,
# adr_log.py, adr_scan.py, bootstrap_adr.py.
# MIT, Copyright (c) 2026 Align Tech Ltd, see LICENSE-align
"""Find the decisions in a repository that have no ADR, and draft one ADR for each you accept.

Standard library only. Subcommands:

``locate --repo PATH``
    Print the ADR folders (path, count, prefix, width, highest number, H1 form, headings),
    the single ``primary`` folder (null for none or several), ``next_number``, and
    ``walk_truncated``.

``scan --repo PATH [--rev HEAD] [--max-commits 300] [--since DATE] [--prs-json FILE] --out FILE``
    List candidate decisions as JSON. Reads git and the working tree, makes no network call,
    and writes nothing in the repository. ``--out`` must resolve outside every work tree of the
    repository. ``--prs-json`` is an offline export (see ``adr_commits.py`` for its shape).

``draft --scan FILE --id ID --out DIR [--status Proposed]``
    Create one ADR from a candidate, published create-only, never replacing a file. Its text comes
    from the source: title, stated reason, excerpt, and a link back. Inside a work tree, DIR
    must be a located ADR folder of that tree and the file must not be ignored by git.

The checks on ``--out`` go by path, so its folder must not change during a run. A successful
payload's ``leftover`` key names a temporary file that could not be removed after publication.

Every command prints JSON. Exit codes: 0 done; 1 the draft target exists or another ADR took
its number (``error`` is ``exists``, and ``written`` is true when the draft stays on disk); 2 bad
arguments, unreadable or malformed input, a refused ``--out`` (``config`` or ``io``), or an
internal error (``internal``); 3 git is missing, failed, or timed out (``git``).

Departures from the upstream source, each pinned by a test:

- The status is ``Proposed`` by default, never ``Accepted``, which upstream wrote.
- The H1 copies the newest ADR's form (``# ADR-123: Title``), and the file name keeps its
  prefix and padding. Upstream wrote ``# 123. Title`` and a bare number.
- The headings follow the newest ADR in the folder. A heading the source does not fill says
  ``Not recorded in the source.`` Upstream wrote fixed Nygard headings.
- The number is taken at write time and the file published create-only. A name that
  exists is reported, never retried with another number. Past ``MAX_ADR_NUMBER`` the draft is
  refused, because the locator reads only one to six digits.
- A title with no ASCII letter or digit gives the slug ``decision-<sha7>`` (or the id), not ``""``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, NoReturn

from adr_commits import sanitize, slugify
from adr_locate import (
    FULL_SHA,
    MAX_READ_BYTES,
    NOT_RECORDED,
    Style,
    adr_files,
    adr_title,
    clean_source,
    folder_style,
    locate,
    render,
)
from adr_scan import (
    ConfigError,
    GitError,
    git_text,
    repo_root,
    scan,
)
from adr_shape import flat
from adr_write import create_new, encode, gate_target, out_outside_repo, refuse_ignored

__all__ = [
    "DEFAULT_MAX_COMMITS",
    "MAX_ADR_NUMBER",
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

MAX_JSON_BYTES = 16 * MAX_READ_BYTES
# scan refuses to write a report over this, so draft can always read what scan wrote.
MAX_SCAN_BYTES = 128 * MAX_READ_BYTES
_KINDS = frozenset({"commit", "pr", "decision-log"})
# The highest number ``adr_locate.adr_files`` reads: its ``_ADR_NAME`` takes one to six digits.
# A seven-digit draft would be invisible to the next ``locate`` and to the twin check below.
MAX_ADR_NUMBER = 999_999
# ADR-073's status enum, without "accepted": a draft never asserts its own approval.
# Acceptance needs a review, so a person sets it after the draft is written. Superseded is
# allowed on a draft for compatibility, but a person must add the superseding reference by
# hand, because a draft has no front matter.
DRAFT_STATUSES: tuple[str, ...] = ("Proposed", "Rejected", "Deprecated", "Superseded")


class ExistsError(Exception):
    """The target exists, or another ADR took the same number. Exit 1."""

    def __init__(
        self, message: str, path: Path, others: list[str] | None = None, written: bool = False
    ) -> None:
        super().__init__(message)
        self._path = path
        self._others = tuple(others or ())
        self._written = written

    @property
    def path(self) -> Path:
        """The draft target that already existed or that this run wrote."""
        return self._path

    @property
    def others(self) -> list[str]:
        """Names of other ADRs that took the same number."""
        return list(self._others)

    @property
    def written(self) -> bool:
        """True when this run wrote the draft before it found a twin number."""
        return self._written


def _text(value: object, name: str, required: bool = False) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or (required and not value.strip()):
        raise ConfigError(f"scan file candidate field {name!r} must be a string")
    return sanitize(value)


def _read_json(path: str, label: str, limit: int) -> Any:
    """Parse a regular JSON file of at most ``limit`` bytes, or raise ConfigError.

    The file opens without blocking and ``fstat`` checks the open descriptor, so a named pipe is
    refused, never waited on. The read stops one byte past the limit, whatever size the file
    reports.
    """
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(fd, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise ConfigError(f"{label} {path} is not a regular file")
            data = handle.read(limit + 1)
        if len(data) > limit:
            raise ConfigError(f"{label} {path} is too large")
        return json.loads(data.decode("utf-8"))  # strict: a bad byte is bad input, not U+FFFD
    except (OSError, ValueError, RecursionError) as exc:
        raise ConfigError(f"cannot read {label} {path}: {exc}") from exc


def load_candidate(path: str, ident: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read a scan file and return ``(scan, candidate)`` for ``ident``, or raise ConfigError."""
    data = _read_json(path, "scan file", MAX_SCAN_BYTES)
    if not isinstance(data, dict) or not isinstance(data.get("candidates"), list):
        raise ConfigError(f"scan file {path} is not a scan result")
    if not isinstance(data.get("repo"), str):
        raise ConfigError(f"scan file {path} does not name its repository")
    for item in data["candidates"]:
        if isinstance(item, dict) and item.get("id") == ident:
            return data, item
    raise ConfigError(f"no candidate with id {ident!r} in {path}")


def _prepare_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    """A cleaned copy of a scan candidate, or ConfigError. The scan data is left as it was.

    Every text field is stripped of control bytes. The title, the reason and every ``source``
    string also lose each line break, so none of them can start a new line of the draft. The
    renderer escapes a title that starts with Markdown syntax. The excerpt keeps its lines,
    because the renderer quotes every one of them.
    """
    kind = candidate.get("kind")
    if not isinstance(kind, str) or kind not in _KINDS:
        raise ConfigError(f"candidate {candidate.get('id')!r} has an unknown kind")
    title = flat(_text(candidate.get("title"), "title", True) or "")
    if not title:
        raise ConfigError(f"candidate {candidate.get('id')!r} has no title once cleaned")
    reason = _text(candidate.get("reason"), "reason")
    return {
        **candidate,
        "title": adr_title(kind, title),
        "reason": None if reason is None else flat(reason),
        "excerpt": _text(candidate.get("excerpt"), "excerpt"),
        "source": clean_source(candidate.get("source")),
    }


def _file_name(style: Style, number: int, candidate: dict[str, Any]) -> str:
    slug = slugify(candidate["title"])
    if not slug:
        source = candidate.get("source")
        sha = source.get("sha") if isinstance(source, dict) else None
        base = (
            f"decision-{sha[:7].lower()}"
            if isinstance(sha, str) and FULL_SHA.fullmatch(sha)
            else None
        )
        slug = base or f"decision-{slugify(str(candidate['id'])) or 'unnamed'}"
    return f"{style.prefix}{number:0{style.width}d}-{slug}.md"


def draft(scan_path: str, ident: str, out: str, status: str) -> dict[str, Any]:
    """Write one ADR for candidate ``ident`` into ``out`` and return the ``draft`` payload."""
    matched = [name for name in DRAFT_STATUSES if name.lower() == status.strip().lower()]
    if not matched:
        allowed = ", ".join(DRAFT_STATUSES)
        raise ConfigError(
            f"--status {status!r} must be one of {allowed}; a draft is never Accepted"
        )
    status = matched[0]
    candidate = _prepare_candidate(load_candidate(scan_path, ident)[1])
    tree, out_dir = gate_target(Path(out).resolve())
    if out_dir.exists() and not out_dir.is_dir():
        raise ConfigError(f"--out {out_dir} is not a directory")
    style = folder_style(out_dir)
    number = style.highest + 1
    if number > MAX_ADR_NUMBER:
        raise ConfigError(
            f"{out_dir} has ADR {style.highest}; the numbers stop at {MAX_ADR_NUMBER}"
        )
    target = out_dir / _file_name(style, number, candidate)
    if tree is not None:
        refuse_ignored(tree, target)
    data = encode(render(style, number, candidate, status), target)
    if len(data) > MAX_READ_BYTES:  # the scan reads no ADR over this, so it would miss the draft
        raise ConfigError(f"the draft is over {MAX_READ_BYTES >> 20} MiB; shorten the excerpt")
    leftover = _publish_draft(target, data, out_dir, number)
    result = {"path": str(target), "number": number, "id": ident, "status": status}
    return {**result, "in_repo": tree is not None, **leftover}


def _leftover(temp: Path | None) -> dict[str, str]:
    return {} if temp is None else {"leftover": str(temp)}


def _publish_draft(target: Path, data: bytes, out_dir: Path, number: int) -> dict[str, str]:
    """Create ``target``, then raise ExistsError if another ADR took ``number`` meanwhile."""
    try:
        leftover = _leftover(create_new(target, data))
    except FileExistsError as exc:
        raise ExistsError(f"{target} already exists; it is never replaced", target) from exc
    twins = [
        item.name
        for item in adr_files(out_dir)
        if item.number == number and item.name != target.name
    ]
    if twins:
        raise ExistsError(
            f"the draft was written to {target}, but another ADR has number {number} "
            f"({', '.join(twins)}); renumber or remove one of the two files",
            target,
            twins,
            written=True,
        )
    return leftover


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
  1  the draft target exists, or another ADR took its number (in the second case
     the draft stays on disk: renumber or remove one file)
  2  bad arguments, unreadable or malformed input, a refused --out, or an internal
     error (the error field is "internal")
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
    data = _read_json(path, "--prs-json", MAX_JSON_BYTES)
    if not isinstance(data, list):
        raise ConfigError(f"--prs-json {path} must hold a JSON list")
    return data


def _cmd_locate(args: argparse.Namespace) -> dict[str, Any]:
    return locate(repo_root(Path(args.repo)))


# A date, or a date and time. git reads a compact or week date (20260131, 2026-W05-1) as now,
# and ignores an offset with 60 or more minutes.
_SINCE = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}(?:[T ][0-9]{2}:[0-9]{2}(?::[0-9]{2})?(?:Z|[+-][0-9]{2}:?[0-5][0-9])?)?",
    re.ASCII,
)


def _check_since(since: str | None) -> str | None:
    """``--since`` as git should read it, else exit 2. git reads a word it cannot parse as now,
    and a bare date as that day at the current time, so a bare date gets local midnight."""
    if since is None:
        return None
    try:
        if not _SINCE.fullmatch(since):
            raise ValueError(since)
        datetime.fromisoformat(since.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ConfigError(
            f"--since must be an ISO 8601 date such as 2026-01-31: {since!r}"
        ) from exc
    return since if len(since) > 10 else f"{since}T00:00:00"


# GIT_NO_LAZY_FETCH, which stops a partial clone fetching a missing object, came in git 2.45.1
# and the May 2024 security releases of 2.39 to 2.44.
_NO_LAZY_FETCH_GIT = (2, 45, 1)
_NO_LAZY_FETCH_BACKPORTS = {(2, 39): 4, (2, 40): 2, (2, 41): 1, (2, 42): 2, (2, 43): 4, (2, 44): 1}
# A line of ``git config --get-regexp`` that makes the repository a partial clone. git 2.37
# reads a filter key as a promisor whatever its value, even empty or bare (no space follows).
_PROMISOR = re.compile(
    r"extensions\.partialclone \S|remote\..*\.partialclonefilter(?: |\Z)"
    r"|remote\..*\.promisor(?:\Z| (?!false|no|off|0\b)\S)"  # a bare key means true
)


def _git_version(root: Path) -> tuple[int, int, int]:
    found = re.match(r"git version ([0-9]+)\.([0-9]+)\.([0-9]+)", git_text(root, "version").stdout)
    major, minor, patch = (int(part) for part in found.groups()) if found else (0, 0, 0)
    return major, minor, patch


def _refuse_lazy_fetch(root: Path) -> None:
    """Refuse a partial clone on a git that may fetch, so ``scan`` never reaches the network."""
    keys = r"^(extensions\.partialclone|remote\..*\.(promisor|partialclonefilter))$"
    config = git_text(root, "config", "--get-regexp", keys, ok=(0, 1)).stdout.lower()
    version = _git_version(root)
    floor = _NO_LAZY_FETCH_BACKPORTS.get((version[0], version[1]))
    honored = version >= _NO_LAZY_FETCH_GIT or (floor is not None and version[2] >= floor)
    if not honored and any(_PROMISOR.match(line) for line in config.splitlines()):
        raise ConfigError(
            "this is a partial clone, and a git without GIT_NO_LAZY_FETCH (before 2.45.1 or"
            " its May 2024 backports) may fetch a missing commit;"
            " upgrade git or scan a full clone"
        )


def _cmd_scan(args: argparse.Namespace) -> dict[str, Any]:
    root = repo_root(Path(args.repo))
    target = out_outside_repo(root, args.out)
    since = _check_since(args.since)
    _refuse_lazy_fetch(root)
    payload = scan(root, args.rev, args.max_commits, since, _read_prs(args.prs_json))
    text = json.dumps(payload, indent=2) + "\n"  # ASCII, so characters count bytes
    if len(text) > MAX_SCAN_BYTES:
        raise ConfigError(f"scan report over {MAX_SCAN_BYTES >> 20} MiB; narrow --max-commits")
    data = encode(text, target)
    # Again, and write where this check resolved: a work tree or a link may have appeared.
    target = out_outside_repo(root, str(target))
    try:
        leftover = _leftover(create_new(target, data))
    except FileExistsError as exc:
        raise ConfigError(f"--out {target} already exists; it is never overwritten") from exc
    return {**payload, "out": str(target), **leftover}


def _cmd_draft(args: argparse.Namespace) -> dict[str, Any]:
    return draft(args.scan, args.id, args.out, args.status)


class _Parser(argparse.ArgumentParser):
    """A bad argument raises ConfigError, so it prints JSON and exits 2 like any other input
    error. ``--help`` still prints text and exits 0. Subparsers inherit this class."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("allow_abbrev", False)  # --ou must not mean --out
        super().__init__(*args, **kwargs)

    def error(self, message: str) -> NoReturn:
        raise ConfigError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
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
    p_draft.add_argument(
        "--status",
        default="Proposed",
        help="one of " + ", ".join(DRAFT_STATUSES) + "; a draft is never Accepted",
    )
    return parser


_HANDLERS = {"locate": _cmd_locate, "scan": _cmd_scan, "draft": _cmd_draft}


def _fail(code: int, error: str, message: str, **extra: Any) -> int:
    print(json.dumps({"error": error, "message": message, **extra}))
    return code


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        payload = _HANDLERS[args.command](args)
    except ExistsError as exc:
        return _fail(
            1, "exists", str(exc), path=str(exc.path), others=exc.others, written=exc.written
        )
    except ConfigError as exc:
        return _fail(2, "config", str(exc))
    except GitError as exc:
        return _fail(3, "git", str(exc))
    except OSError as exc:
        return _fail(2, "io", str(exc))
    except (RecursionError, ValueError) as exc:  # UnicodeError is a ValueError
        return _fail(2, "config", f"bad input: {type(exc).__name__}: {exc}")
    except Exception as exc:  # last resort: JSON on stdout, never a traceback
        # The standard's logic-error code, 1, is reserved here for ``exists``, and 3 and 4 mean
        # external and auth. Nothing fits, so an internal error shares exit 2 and says so.
        return _fail(2, "internal", f"{type(exc).__name__}: {exc}")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

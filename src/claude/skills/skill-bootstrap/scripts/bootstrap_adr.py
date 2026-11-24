#!/usr/bin/env python3
# Port of aligndottech/align-cli at commit 8d758e9899677b61442b08ffda74b74887bfc42a
# Ported upstream files:
#   src/commands/adr.ts   (runAdr, the list-then-accept flow, lines 25-48; this file adds the
#                          command line around it)
#   src/lib/adr-writer.ts (writeAdr, lines 137-148; renderAdr and slug live in adr_locate.py
#                          and adr_commits.py. The trailing "Drafted by" comment is not ported.)
# Sibling ports: adr_shape.py, adr_reason.py, adr_commits.py, adr_docs.py, adr_locate.py,
# adr_scan.py, bootstrap_adr.py.
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
    Render one candidate as an ADR and create it with mode ``x``, never replacing a file.
    Everything in the draft comes from the source: its title, the reason it stated, an
    excerpt of its text, and a link to where it was decided. A section the source never
    covered says so. If git finds a work tree around DIR, DIR must be one of that work
    tree's located ADR folders and the file must not be ignored by git, whatever repository
    the scan file names.

Every command prints JSON. Exit codes: 0 done; 1 the draft target exists or another ADR took
its number (``error`` is ``exists``, and ``written`` is true when the draft stays on disk); 2 bad
arguments, unreadable or malformed input, a refused ``--out`` (``config`` or ``io``), or an
internal error (``internal``); 3 git is missing, failed, or timed out (``git``).

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
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

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
    is_draft_target,
    locate,
    locate_folders,
    render,
)
from adr_scan import (
    ConfigError,
    GitError,
    git_bytes,
    git_text,
    refusal,
    repo_root,
    scan,
    stderr_text,
)
from adr_shape import flat

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

MAX_JSON_BYTES = 16 * MAX_READ_BYTES
_KINDS = frozenset({"commit", "pr", "decision-log"})
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


def _read_json(path: str, label: str) -> Any:
    """Parse a regular JSON file of at most ``MAX_JSON_BYTES``, or raise ConfigError.

    The file opens without blocking and ``fstat`` checks the open descriptor, so a named pipe is
    refused, never waited on. The read stops one byte past the limit, whatever size the file
    reports.
    """
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(fd, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise ConfigError(f"{label} {path} is not a regular file")
            data = handle.read(MAX_JSON_BYTES + 1)
        if len(data) > MAX_JSON_BYTES:
            raise ConfigError(f"{label} {path} is too large")
        return json.loads(data.decode("utf-8", errors="replace"))
    except (OSError, ValueError, RecursionError) as exc:
        raise ConfigError(f"cannot read {label} {path}: {exc}") from exc


def load_candidate(path: str, ident: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read a scan file and return ``(scan, candidate)`` for ``ident``, or raise ConfigError."""
    data = _read_json(path, "scan file")
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
    reason = _text(candidate.get("reason"), "reason")
    return {
        **candidate,
        "title": adr_title(kind, title),
        "reason": None if reason is None else flat(reason),
        "excerpt": _text(candidate.get("excerpt"), "excerpt"),
        "source": clean_source(candidate.get("source")),
    }


def _same_file(first: Path, second: Path) -> bool:
    """Do two paths name one file or folder? True for links and for case variants."""
    try:
        return os.path.samefile(first, second)
    except OSError:
        return False


def _git_path(directory: Path, flag: str) -> Path | None:
    proc = git_bytes(directory, "rev-parse", "--path-format=absolute", flag)
    text = proc.stdout.decode("utf-8", "replace").strip()
    return Path(text).resolve() if proc.returncode == 0 and text else None


def _enclosing_tree(path: Path) -> Path | None:
    """The git work tree that holds ``path`` or its nearest existing ancestor, else None.

    None means no work tree encloses it. Any other git failure (the ``.git`` folder, a bare
    repository, a dubious-ownership refusal) is an error and never a scratch folder.
    """
    ancestor = next(item for item in (path, *path.parents) if item.is_dir())
    proc = git_bytes(ancestor, "rev-parse", "--path-format=absolute", "--show-toplevel")
    top = proc.stdout.decode("utf-8", "replace").strip()
    if proc.returncode == 0 and top:
        return Path(top).resolve()
    if "not a git repository" in stderr_text(proc):
        return None
    raise refusal(proc, f"git reports no work tree for {ancestor}")


def _same_repo(first: Path, second: Path) -> bool:
    """Do two work trees belong to one repository? A linked worktree shares its common dir."""
    one, two = _git_path(first, "--git-common-dir"), _git_path(second, "--git-common-dir")
    return one is not None and two is not None and _same_file(one, two)


def _gate_target(out_dir: Path) -> tuple[Path | None, Path]:
    """``(work tree or None, folder)`` for ``draft --out``.

    The work tree that git finds around ``out_dir`` decides, whatever repository the scan
    file names. Inside a work tree, ``out_dir`` must be one of its located ADR folders that
    take drafts, and ``folder`` is that folder spelled as the work tree has it. A path with
    no work tree around it is a scratch folder.
    """
    try:
        tree = _enclosing_tree(out_dir)
    except ConfigError as exc:
        raise ConfigError(f"{out_dir} is not an ADR folder that takes drafts: {exc}") from exc
    if tree is None:
        return None, out_dir
    for rel, _source in locate_folders(tree)[0]:
        folder = (tree / rel).resolve()
        if is_draft_target(rel) and _same_file(folder, out_dir):
            return tree, folder
    raise ConfigError(
        f"{out_dir} is inside the repository {tree} and is not an ADR folder that takes drafts"
    )


def _refuse_ignored(tree: Path, target: Path) -> None:
    # ``./`` keeps a name that starts with ``:`` from being read as pathspec magic. git refuses
    # ``--literal-pathspecs`` for check-ignore ("pathspec magic not supported by this command").
    pathspec = "./" + target.relative_to(tree).as_posix()
    proc = git_text(tree, "check-ignore", "-q", "--", pathspec, ok=(0, 1))
    if proc.returncode == 0:
        raise ConfigError(f"{target} is ignored by git; the ADR would not be committed")


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


def _encode(text: str, target: Path) -> bytes:
    """UTF-8 bytes of ``text``. A lone surrogate fails here, before any file or folder exists."""
    try:
        return text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ConfigError(f"text for {target} cannot be written as UTF-8: {exc.reason}") from exc


def _create_new(target: Path, data: bytes) -> None:
    """Create ``target`` with mode ``x``, and its folder if needed. FileExistsError if it exists."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "xb") as handle:
        handle.write(data)


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
    tree, out_dir = _gate_target(Path(out).resolve())
    if out_dir.exists() and not out_dir.is_dir():
        raise ConfigError(f"--out {out_dir} is not a directory")
    style = folder_style(out_dir)
    number = style.highest + 1
    target = out_dir / _file_name(style, number, candidate)
    if tree is not None:
        _refuse_ignored(tree, target)
    data = _encode(render(style, number, candidate, status), target)
    try:
        _create_new(target, data)
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
    data = _read_json(path, "--prs-json")
    if not isinstance(data, list):
        raise ConfigError(f"--prs-json {path} must hold a JSON list")
    return data


def _out_outside_repo(root: Path, out: str) -> Path:
    """Resolve ``--out`` once and refuse a path inside any work tree of the scanned repository,
    a directory, or an existing file."""
    target = Path(out).resolve()
    inside = target == root or root in target.parents
    if not inside:
        try:
            tree = _enclosing_tree(target)
        except ConfigError as exc:
            raise ConfigError(f"--out {target}: {exc}") from exc
        inside = tree is not None and _same_repo(root, tree)
    if inside:
        raise ConfigError(f"--out {target} is inside the repository {root}; write it elsewhere")
    if target.is_dir():
        raise ConfigError(f"--out {target} is a directory")
    if target.exists():
        raise ConfigError(f"--out {target} already exists; it is never overwritten")
    return target


def _cmd_locate(args: argparse.Namespace) -> dict[str, Any]:
    return locate(repo_root(Path(args.repo)))


def _cmd_scan(args: argparse.Namespace) -> dict[str, Any]:
    root = repo_root(Path(args.repo))
    target = _out_outside_repo(root, args.out)
    if args.since is not None and args.since.startswith("-"):
        raise ConfigError(f"--since may not start with '-': {args.since!r}")
    payload = scan(root, args.rev, args.max_commits, args.since, _read_prs(args.prs_json))
    try:
        _create_new(target, _encode(json.dumps(payload, indent=2) + "\n", target))
    except FileExistsError as exc:
        raise ConfigError(f"--out {target} already exists; it is never overwritten") from exc
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
    args = build_parser().parse_args(argv)
    try:
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

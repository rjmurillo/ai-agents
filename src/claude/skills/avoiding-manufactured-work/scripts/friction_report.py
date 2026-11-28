#!/usr/bin/env python3
"""Compute the computable half of a friction report from the session transcript.

The friction report names, per workaround, what the agent hit, what it did
instead, and the permanent fix. A program finds the first two in the session
transcript. The model writes the permanent fix and decides which candidates
are real friction.

Subcommands:

- ``candidates``: failed shell calls that a later call worked around. Prints
  one ``Hit:`` / ``Did instead:`` / ``Permanent fix:`` block per candidate. The
  permanent fix line stays a placeholder for the model to fill.
- ``scripts``: inline programs seen two or more times, and script files written
  under a scratch path by a file tool or a shell redirect. It resolves the
  repository root from the working directory the transcript records and prints
  ``<root>/scripts`` beside each one. With no such directory it prints a
  friction block for the missing location.
- ``check``: validates the final friction block. Reads ``--file`` or stdin.

``candidates`` and ``scripts`` read ``--transcript``. Without it they use the
newest ``*.jsonl`` under ``${CLAUDE_CONFIG_DIR:-~/.claude}/projects/<slug>/``,
where ``<slug>`` is the working directory with ``/`` and ``.`` replaced by
``-``. A candidate is a lead: it can be a false positive, and a real workaround
can be missing when the harness did not mark the call as failed.

EXIT CODES (ADR-035):
    0 - Success, including no candidates found, and a valid friction block.
    1 - Logic failure: ``check`` found problems in the friction block.
    2 - Usage or configuration: bad arguments, missing or unreadable
        transcript or file, no transcript found for the working directory,
        input over the size cap.
    3 - External: an I/O error while reading after the file opened.

Stdlib only, plus this plugin's own ``lib/``.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import sys
from collections.abc import Callable, Iterable, Iterator, Mapping
from pathlib import Path
from typing import IO, NoReturn

# ADR-047 keeps this bootstrap inline because imports need sys.path first.
# The skill directory sits at <plugin root>/skills/avoiding-manufactured-work/
# and this file sits in its scripts/ directory.
# A plugin-root variable can name a foreign plugin, so a root counts only when
# its lib/ holds failure_classifier. Otherwise use this file's own plugin root.
_LIB_DIR = Path(__file__).resolve().parents[3] / "lib"
for _root in (os.environ.get("COPILOT_PLUGIN_ROOT"), os.environ.get("CLAUDE_PLUGIN_ROOT")):
    if _root and (Path(_root) / "lib" / "failure_classifier").is_dir():
        _LIB_DIR = Path(_root) / "lib"
        break
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from failure_classifier import (  # noqa: E402
    KIND_FIX_THEN_RETRY,
    FailureEvent,
    ScriptInventory,
    WorkaroundCandidate,
    events_from_records,
    inline_script_inventory,
    redact_text,
    unmarked_failures,
    validate_friction_block,
    workaround_candidates,
)

EXIT_OK = 0
EXIT_LOGIC = 1
EXIT_USAGE = 2
EXIT_EXTERNAL = 3

MAX_TRANSCRIPT_BYTES = 128 * 1024 * 1024
MAX_LINE_CHARS = 16 * 1024 * 1024
MAX_CHECK_CHARS = 1024 * 1024
PERMANENT_FIX_PLACEHOLDER = "<model writes this>"
_SLUG_UNSAFE = re.compile(r"[/.]")


class UsageError(Exception):
    """A configuration or usage problem: exit 2."""


class ExternalError(Exception):
    """An I/O failure after the input opened: exit 3."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise UsageError(message)


# ---------------------------------------------------------------------------
# Transcript input
# ---------------------------------------------------------------------------


def project_slug(cwd: str) -> str:
    """The directory name Claude Code uses for a working directory."""
    return _SLUG_UNSAFE.sub("-", cwd)


def resolve_transcript(explicit: str | None, cwd: str, env: Mapping[str, str]) -> Path:
    """The transcript to read: ``explicit``, else the newest one for ``cwd``."""
    if explicit:
        return Path(explicit)
    config = Path(env.get("CLAUDE_CONFIG_DIR") or "~/.claude").expanduser()
    directory = config / "projects" / project_slug(cwd)
    try:
        found = list(directory.glob("*.jsonl"))
    except OSError as exc:
        raise UsageError(f"cannot list {directory}: {exc.strerror or exc}") from exc
    if not found:
        raise UsageError(f"no *.jsonl transcript under {directory}; pass --transcript PATH")
    try:
        return max(found, key=lambda path: (path.stat().st_mtime, path.name))
    except OSError as exc:
        raise UsageError(f"cannot stat a transcript in {directory}: {exc.strerror or exc}") from exc


def iter_records(handle: IO[str]) -> Iterator[object]:
    """Decoded JSON records, one per line. Bad and oversize lines are skipped."""
    while True:
        line = handle.readline(MAX_LINE_CHARS + 1)
        if not line:
            return
        if len(line) > MAX_LINE_CHARS:
            while line and not line.endswith("\n"):
                line = handle.readline(MAX_LINE_CHARS)
            continue
        try:
            yield json.loads(line)
        except (ValueError, RecursionError):
            continue


class _CwdTap:
    """Pass records through and keep the first working directory one carries."""

    def __init__(self, records: Iterator[object]) -> None:
        self._records = records
        self.cwd: str | None = None

    def __iter__(self) -> Iterator[object]:
        for record in self._records:
            if self.cwd is None and isinstance(record, dict):
                cwd = record.get("cwd")
                if isinstance(cwd, str) and cwd:
                    self.cwd = cwd
            yield record


def load_session(path: Path) -> tuple[list[FailureEvent], str | None]:
    """``path`` as FailureEvents plus its recorded working directory.

    Exit 2 on open failure, 3 on read failure.
    """
    try:
        size = path.stat().st_size
        handle = path.open("r", encoding="utf-8", errors="replace")
    except FileNotFoundError as exc:
        raise UsageError(f"transcript not found: {path}") from exc
    except OSError as exc:
        raise UsageError(f"cannot read transcript {path}: {exc.strerror or exc}") from exc
    if size > MAX_TRANSCRIPT_BYTES:
        handle.close()
        raise UsageError(f"transcript is {size} bytes, over the {MAX_TRANSCRIPT_BYTES} cap")
    with handle:
        try:
            tap = _CwdTap(iter_records(handle))
            return events_from_records(tap), tap.cwd
        except OSError as exc:
            raise ExternalError(f"read failed for {path}: {exc.strerror or exc}") from exc


def load_events(path: Path) -> list[FailureEvent]:
    """Stream ``path`` into FailureEvents. Exit 2 on open failure, 3 on read failure."""
    return load_session(path)[0]


# ---------------------------------------------------------------------------
# Script location
# ---------------------------------------------------------------------------

LOCATION_FOUND = "found"
LOCATION_MISSING = "missing"
LOCATION_UNKNOWN = "unknown"
SCRIPT_DIR_NAME = "scripts"
_ROOT_SEARCH_DEPTH = 64


@dataclasses.dataclass(frozen=True)
class ScriptLocation:
    """Where the project keeps scripts. ``root`` is None when it is unknown."""

    status: str
    root: str | None = None
    path: str | None = None


def resolve_script_location(cwd: str | None) -> ScriptLocation:
    """``<root>/scripts`` for the repository that holds ``cwd``.

    The root is the nearest directory at or above ``cwd`` with a ``.git`` entry
    (a directory, or a file in a linked worktree). A ``cwd`` that is absent, not
    on this disk, or outside a repository gives ``unknown``: the program then
    claims nothing about the location.
    """
    if not cwd:
        return ScriptLocation(LOCATION_UNKNOWN)
    try:
        start = Path(cwd)
        if not start.is_absolute() or not start.is_dir():
            return ScriptLocation(LOCATION_UNKNOWN)
        for directory in (start, *start.parents)[:_ROOT_SEARCH_DEPTH]:
            if (directory / ".git").exists():
                scripts = directory / SCRIPT_DIR_NAME
                if scripts.is_dir():
                    return ScriptLocation(LOCATION_FOUND, str(directory), str(scripts))
                return ScriptLocation(LOCATION_MISSING, str(directory))
    except (OSError, ValueError):
        return ScriptLocation(LOCATION_UNKNOWN)
    return ScriptLocation(LOCATION_UNKNOWN)


def missing_location_block(location: ScriptLocation, inventory: ScriptInventory) -> str:
    """The friction block for a repository with no scripts directory."""
    count = len(inventory.inline) + len(inventory.scratch)
    return (
        f"Hit: no {SCRIPT_DIR_NAME}/ directory under {redact_text(location.root or '')}\n"
        f"Did instead: left {count} recurring programs inline or under a scratch path\n"
        f"Permanent fix: {PERMANENT_FIX_PLACEHOLDER}"
    )


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def candidate_block(candidate: WorkaroundCandidate) -> str:
    """One friction block. Hit and Did instead come from evidence."""
    hit = f"{candidate.tool} call failed: {candidate.failed}"
    if candidate.error:
        hit += f" | error: {candidate.error}"
    if candidate.count > 1:
        hit += f" (seen {candidate.count} times)"
    if candidate.kind == KIND_FIX_THEN_RETRY:
        did = f"ran {candidate.succeeded}, then the same call worked"
    else:
        did = f"ran {candidate.succeeded}"
    return f"Hit: {hit}\nDid instead: {did}\nPermanent fix: {PERMANENT_FIX_PLACEHOLDER}"


def _failed_count(events: Iterable[FailureEvent]) -> int:
    return sum(1 for event in events if not event.ok)


def render_candidates(
    events: list[FailureEvent], candidates: list[WorkaroundCandidate], fmt: str
) -> str:
    unmarked = unmarked_failures(events)
    if fmt == "json":
        payload = {
            "events": len(events),
            "failed": _failed_count(events),
            "candidates": [dataclasses.asdict(c) for c in candidates],
            "unmarked": [dataclasses.asdict(u) for u in unmarked],
        }
        return json.dumps(payload, indent=2)
    parts = [candidate_block(candidate) for candidate in candidates]
    if not candidates:
        parts.append(
            f"No workaround candidates: {len(events)} tool calls, "
            f"{_failed_count(events)} marked failed."
        )
    if unmarked:
        lines = ["Calls marked as success whose output states a failure (leads, not blocks):"]
        lines.extend(f"- {u.command} | output: {u.line} (seen {u.count} times)" for u in unmarked)
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def render_scripts(
    events: list[FailureEvent],
    inventory: ScriptInventory,
    fmt: str,
    location: ScriptLocation | None = None,
) -> str:
    where = location or ScriptLocation(LOCATION_UNKNOWN)
    path = redact_text(where.path) if where.path else None
    has_programs = bool(inventory.inline or inventory.scratch)
    if fmt == "json":
        payload = {
            "events": len(events),
            "repository_root": redact_text(where.root) if where.root else None,
            "script_location": path,
            "script_location_status": where.status,
            "inline": [dataclasses.asdict(g) | {"script_location": path} for g in inventory.inline],
            "scratch": [
                dataclasses.asdict(s) | {"script_location": path} for s in inventory.scratch
            ],
        }
        return json.dumps(payload, indent=2)
    if not has_programs:
        return f"No recurring inline programs and no scratch scripts in {len(events)} tool calls."
    keep = f" | keep in: {path}" if path else ""
    lines: list[str] = []
    if inventory.inline:
        lines.append("Inline programs seen 2 or more times:")
        lines.extend(
            f"- {g.interpreter} x{g.count} (hash {g.body_hash}, first at tool call "
            f"{g.first_index + 1}): {g.sample}{keep}"
            for g in inventory.inline
        )
    if inventory.scratch:
        lines.append("Scratch scripts written:")
        lines.extend(
            f"- {s.path}: written {s.writes} times, named by {s.references} later commands{keep}"
            for s in inventory.scratch
        )
    if where.status == LOCATION_MISSING:
        lines.extend(("", missing_location_block(where, inventory)))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def _transcript_events(args: argparse.Namespace) -> list[FailureEvent]:
    path = resolve_transcript(args.transcript, os.getcwd(), os.environ)
    return load_events(path)


def run_candidates(args: argparse.Namespace) -> int:
    events = _transcript_events(args)
    candidates = workaround_candidates(events)
    print(render_candidates(events, candidates, args.format))
    return EXIT_OK


def run_scripts(args: argparse.Namespace) -> int:
    events, cwd = load_session(resolve_transcript(args.transcript, os.getcwd(), os.environ))
    location = resolve_script_location(cwd)
    print(render_scripts(events, inline_script_inventory(events), args.format, location))
    return EXIT_OK


def _read_check_text(file: str | None) -> str:
    if file is None:
        if sys.stdin.isatty():
            raise UsageError("no --file given and stdin is a terminal")
        text = sys.stdin.read(MAX_CHECK_CHARS + 1)
    else:
        try:
            with Path(file).open("r", encoding="utf-8", errors="replace") as handle:
                text = handle.read(MAX_CHECK_CHARS + 1)
        except FileNotFoundError as exc:
            raise UsageError(f"file not found: {file}") from exc
        except OSError as exc:
            raise UsageError(f"cannot read {file}: {exc.strerror or exc}") from exc
    if len(text) > MAX_CHECK_CHARS:
        raise UsageError(f"input is over the {MAX_CHECK_CHARS} character cap")
    return text


def run_check(args: argparse.Namespace) -> int:
    problems = validate_friction_block(_read_check_text(args.file))
    if problems:
        print("\n".join(problems))
        return EXIT_LOGIC
    print("friction block valid")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="friction_report.py",
        description="Compute the computable half of a friction report from the session transcript.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name, helptext in (
        ("candidates", "Hit and Did instead blocks for failed calls that were worked around."),
        ("scripts", "Recurring inline programs and scratch script files."),
    ):
        sub = commands.add_parser(name, help=helptext)
        sub.add_argument("--transcript", help="session transcript (.jsonl); default: newest")
        sub.add_argument("--format", choices=("text", "json"), default="text")
    check = commands.add_parser("check", help="Validate a friction block.")
    check.add_argument("--file", help="file holding the block; default: stdin")
    return parser


_HANDLERS: dict[str, Callable[[argparse.Namespace], int]] = {
    "candidates": run_candidates,
    "scripts": run_scripts,
    "check": run_check,
}


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        return _HANDLERS[args.command](args)
    except UsageError as exc:
        print(f"friction_report: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except ExternalError as exc:
        print(f"friction_report: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Resolve which lock files a block of shell text actually opens.

Split out of ``check_push_lock_paths`` so that gate keeps only its Markdown
units, its corpus inventory and its CLI. This module answers one question,
"given these lines, which paths does ``flock`` end up holding", and knows
nothing about fences, paragraphs or tracked files.

The unit is the block, not the line, because three of the four ways a recipe
reaches its lock separate ``flock`` from the path it opens.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Sequence
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.validation.shell_text import split_statements, strip_hash_comments  # noqa: E402

_FLOCK = re.compile(r"\bflock\b")
# A lock path token anywhere in a statement. The character class stops at the
# shell metacharacters that cannot appear inside a path, so `exec 9>/tmp/x.lock`
# yields `/tmp/x.lock` rather than `9>/tmp/x.lock`. The `+` requires at least
# one character before the suffix, so prose that writes the bare extension is
# not mistaken for a path.
_LOCK_PATH = re.compile(r"[A-Za-z0-9_./$~{}@%+-]+\.lock\b")
_CANONICAL_PATH = re.compile(r"^(?:\$HOME|\$\{HOME\})/src/scratch/locks/push-lock-[^/]*\.lock$")
# `exec 9>/path` opens the lock without ever naming it to `flock`.
_EXEC_REDIRECT = re.compile(r"\bexec\s+\d*>+\s*([^\s;|&<>'\"]+)")
# `LOCK=/path` then `flock "$LOCK"`.
_ASSIGNMENT = re.compile(r"\b(\w+)=(\S+)")
# A whole token that is only a variable, so it points at an assignment above.
_BARE_VARIABLE = re.compile(r"^\$\{?(\w+)\}?$")


def is_canonical(path: str) -> bool:
    """Return True when ``path`` matches the one sanctioned lock filename shape."""
    return bool(_CANONICAL_PATH.match(path.strip("\"'")))


def _statements(block: Sequence[str], start: int) -> list[tuple[int, int, str]]:
    """Return (line, column, text) for every shell statement in the block.

    The one list every reader below consumes. Scanning raw lines with a regex
    each, as this module used to, gave each reader a different idea of what the
    line contained: only the first ``flock`` on a line was ever inspected, a
    ``.lock`` literal was collected from a statement the ``flock`` never ran,
    and an argument with the next statement's ``;`` attached to it stopped
    looking like a variable. One statement list fixes all three at the source
    instead of teaching three regexes about separators.
    """
    statements: list[tuple[int, int, str]] = []
    for offset, line in enumerate(block):
        number = start + offset + 1
        statements.extend((number, column, text) for column, text in split_statements(line))
    return statements


def _flock_argument(statement: str) -> tuple[int, str] | None:
    """Return (column, token) that ``flock`` is given, ignoring options and fds.

    Takes one statement, not a line, so the token ends where the statement
    does. The column is relative to the statement and the caller adds the
    statement's own offset, keeping every position comparable within a line.
    """
    match = _FLOCK.search(statement)
    if match is None:
        return None
    for token in re.finditer(r"\S+", statement[match.end() :]):
        text = token.group(0)
        if text.startswith("-") or text.isdigit():
            continue
        return (match.end() + token.start(), text.strip("\"'"))
    return None


def _is_path_like(token: str) -> bool:
    """Return True when a token could name a file rather than a prose word."""
    return "/" in token or token.endswith(".lock")


def _assignments(block: Sequence[str], start: int) -> list[tuple[int, int, str, str]]:
    """Return (line, column, variable, value) for each assignment, in source order.

    Order is kept rather than collapsed into a name-to-value map because a
    block can set the same variable more than once and only the setting that
    precedes a given ``flock`` describes the lock that call actually opens.

    Comments are stripped first, because a commented-out assignment binds
    nothing at runtime and reading it as live is a way to launder a bad recipe
    past this gate:

        LOCK=/tmp/bad.lock
        # LOCK="$HOME/src/scratch/locks/push-lock-$SLUG.lock"
        flock "$LOCK" git push

    The live value is ``/tmp/bad.lock``; taking the comment as the later
    binding made the block read as canonical. The half-finished edit that
    comments out one line and leaves it above the call is the accidental
    version of the same thing.

    Only assignment collection strips comments. ``_candidate_tokens`` keeps
    reading them, so a dead scheme parked in a comment stays visible: that
    direction over-reports, and over-reporting is what the historical marker
    is for.
    """
    found: list[tuple[int, int, str, str]] = []
    for offset, line in enumerate(block):
        number = start + offset + 1
        for column, text in split_statements(strip_hash_comments(line)):
            for match in _ASSIGNMENT.finditer(text):
                name, value = match.group(1), match.group(2)
                found.append((number, column + match.start(), name, value.strip("\"'")))
    return found


def _value_in_effect(
    assignments: Sequence[tuple[int, int, str, str]],
    variable: str,
    use: tuple[int, int],
) -> tuple[int, str] | None:
    """Return the assignment to ``variable`` live at the ``(line, column)`` use.

    Shell rebinds a name in source order, so ``flock "$LOCK"`` opens whatever
    ``LOCK`` was set to *before* it, and a later reassignment cannot reach
    backwards to change that. Taking the block's final value instead read the
    wrong recipe in both directions: a bad path rebound to the canonical one
    afterwards reported clean, and the canonical path rebound to a bad one
    afterwards reported a violation the ``flock`` never opened.

    Position, not line, because a line holds a whole recipe often enough to
    matter: ``LOCK=/tmp/a.lock ; flock "$LOCK"`` must resolve, and its mirror
    ``flock "$LOCK" ; LOCK=/tmp/a.lock`` must not, the same defect one
    granularity down.
    """
    live: tuple[int, str] | None = None
    for number, column, name, value in assignments:
        if name == variable and (number, column) < use:
            live = (number, value)
    return live


def _candidate_tokens(block: Sequence[str], start: int) -> list[tuple[int, int, str]]:
    """Return (line, column, token) for everything that could name a lock file.

    The statement, not the line, decides what counts. A bare ``.lock`` literal
    is read only from a statement that is not purely an assignment, so
    ``LOCK=$CANONICAL ; flock "$LOCK" ; LOCK=/tmp/bad.lock`` no longer reports
    the trailing rebind as a lock the ``flock`` opened. It did not open it: the
    resolver already said so, and the raw literal scan used to contradict the
    resolver from the same line.
    """
    candidates: list[tuple[int, int, str]] = []
    for number, column, text in _statements(block, start):
        assignment_only = _ASSIGNMENT.search(text) is not None and _FLOCK.search(text) is None
        if not assignment_only:
            candidates.extend(
                (number, column + match.start(), match.group(0))
                for match in _LOCK_PATH.finditer(text)
            )
        candidates.extend(
            (number, column + match.start(1), match.group(1))
            for match in _EXEC_REDIRECT.finditer(text)
        )
        argument = _flock_argument(text)
        if argument is not None:
            candidates.append((number, column + argument[0], argument[1]))
    return candidates


def _lock_targets(block: Sequence[str], start: int) -> list[tuple[int, str]]:
    """Return (line number, lock path) for every lock the block actually opens.

    A recipe reaches its lock four ways and only the first keeps ``flock`` and
    the path together:

        flock /tmp/a.lock git push
        LOCK=/tmp/a.lock ; flock "$LOCK" git push
        exec 9>/tmp/a.lock ; flock -n 9
        flock \\ (newline) /tmp/a.lock \\ (newline) git push

    Reading only ``.lock`` tokens misses a lock file written without the
    suffix, so the ``flock`` argument and the ``exec`` redirect target count as
    targets whatever they are named. A bare variable resolves to the assignment
    live at its own position and reports at that assignment, which is where a
    reader fixes it.
    """
    assignments = _assignments(block, start)
    targets: list[tuple[int, str]] = []
    for number, column, token in _candidate_tokens(block, start):
        variable = _BARE_VARIABLE.match(token)
        if variable is not None:
            live = _value_in_effect(assignments, variable.group(1), (number, column))
            number, token = live if live is not None else (number, "")
        if _is_path_like(token) and (number, token) not in targets:
            targets.append((number, token))
    return targets


def _non_canonical(targets: Sequence[tuple[int, str]]) -> list[tuple[int, str]]:
    """Return the subset of resolved lock targets that disagree with the rule."""
    return [(number, path) for number, path in targets if not is_canonical(path)]


def _unresolved_flock_variables(block: Sequence[str], start: int) -> list[tuple[int, str]]:
    """Report each ``flock "$VAR"`` that does not reach a readable path.

    A bare variable handed to ``flock`` is a call site, not discussion: prose
    writes "``flock`` excludes processes that open the same path", never
    "``flock`` $SOMETHING". So one the checker cannot follow to a path is a
    recipe whose lock it cannot read at all, and reading nothing is exactly how
    the three schemes of issue #4366 stayed invisible.

    Two ways it fails to reach one, and both are silent without this:

        flock "$LOCK" git push          # nothing in the block assigns LOCK
        LOCK=$SOME_EXTERNAL_ENV ; flock "$LOCK"   # resolves to another name

    Both units call this, per call site. ``_scan_block``'s no-targets fallback
    does not cover it, because that fallback fires only when the block names
    nothing at all: a fence holding the canonical recipe on one line and
    ``flock "$OTHER"`` on the next has a non-empty target list and used to
    swallow the second call. Unfenced runs suppress the fallback entirely so
    prose about ``flock`` stays quiet, which left the same hole there.

    Reported with an empty path, the same shape a fence uses, because the point
    is that no path could be determined. It reports at the ``flock`` line
    rather than at the assignment, because the call is what cannot be verified.
    Measured over 3518 tracked Markdown files before landing: none of them gain
    a finding.
    """
    assignments = _assignments(block, start)
    unresolved: list[tuple[int, str]] = []
    for number, column, text in _statements(block, start):
        argument = _flock_argument(text)
        if argument is None:
            continue
        argument_column, token = argument
        variable = _BARE_VARIABLE.match(token)
        if variable is None:
            continue
        live = _value_in_effect(assignments, variable.group(1), (number, column + argument_column))
        if live is None or not _is_path_like(live[1]):
            unresolved.append((number, ""))
    return unresolved

#!/usr/bin/env python3
"""Fail when a tracked prescription names a push-lock path that is not canonical.

``flock`` excludes only processes that open the same path, so a second lock name
is not a second lock: it is no lock at all against the first. Three schemes were
live at once on 2026-08-02 and the only way anyone found out was a ``ps`` census
(issue #4366). This checker makes a fourth scheme visible at commit time.

The canonical form is fixed by ``.claude/rules/push-lock.md``:

    flock "$HOME/src/scratch/locks/push-lock-$SLUG.lock" git push origin "$BR"

Scope is prescriptive Markdown only. A retrospective or an audit that records
what an old scheme looked like is evidence, not a recipe, so those trees are
skipped wholesale; a fenced block or a paragraph of prose elsewhere opts out by
carrying the token ``push-lock-historical`` on a line inside it.

A recipe does not stop being a recipe when it loses its fence, so unfenced
prose is scanned in paragraph-sized runs with the same resolver (issue #4635).

EXIT CODES (ADR-035):
  0 - every prescription agrees (prints the examined count)
  1 - at least one non-canonical lock path
  2 - configuration or runtime error
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

CANONICAL_TEMPLATE = '"$HOME/src/scratch/locks/push-lock-<slug>.lock"'
HISTORICAL_MARKER = "push-lock-historical"

# Trees whose whole purpose is recording what already happened.
EXCLUDED_PREFIXES = (
    ".agents/retrospective/",
    ".agents/audits/",
    ".agents/archive/",
)

_FLOCK = re.compile(r"\bflock\b")
# A lock path token anywhere on a line. The character class stops at the shell
# metacharacters that cannot appear inside a path, so `exec 9>/tmp/x.lock`
# yields `/tmp/x.lock` rather than `9>/tmp/x.lock`. The `+` requires at least
# one character before the suffix, so prose that writes the bare extension is
# not mistaken for a path.
_LOCK_PATH = re.compile(r"[A-Za-z0-9_./$~{}@%+-]+\.lock\b")
_CANONICAL_PATH = re.compile(r"^(?:\$HOME|\$\{HOME\})/src/scratch/locks/push-lock-[^/]*\.lock$")
_FENCE = re.compile(r"^\s*(?:```|~~~)")
# `exec 9>/path` opens the lock without ever naming it to `flock`.
_EXEC_REDIRECT = re.compile(r"\bexec\s+\d*>+\s*([^\s;|&<>'\"]+)")
# `LOCK=/path` then `flock "$LOCK"`. Name to (line number, value).
_ASSIGNMENT = re.compile(r"\b(\w+)=(\S+)")
# A whole token that is only a variable, so it points at an assignment above.
_BARE_VARIABLE = re.compile(r"^\$\{?(\w+)\}?$")
NO_PATH_MESSAGE = (
    "flock recipe names no canonical lock path in this block "
    "(expected {template}; see .claude/rules/push-lock.md, issue #4366)"
)


def is_canonical(path: str) -> bool:
    """Return True when ``path`` matches the one sanctioned lock filename shape."""
    return bool(_CANONICAL_PATH.match(path.strip("\"'")))


def _fenced_blocks(lines: Sequence[str]) -> list[tuple[int, int]]:
    """Return (start, end) line indices for each fenced block, end exclusive."""
    blocks: list[tuple[int, int]] = []
    start: int | None = None
    for index, line in enumerate(lines):
        if not _FENCE.match(line):
            continue
        if start is None:
            start = index
        else:
            blocks.append((start, index + 1))
            start = None
    if start is not None:
        blocks.append((start, len(lines)))
    return blocks


def _historical_line_numbers(lines: Sequence[str]) -> set[int]:
    """Return the 1-based line numbers inside blocks marked historical."""
    skipped: set[int] = set()
    for start, end in _fenced_blocks(lines):
        block = lines[start:end]
        if any(HISTORICAL_MARKER in line for line in block):
            skipped.update(range(start + 1, end + 1))
    return skipped


def _flock_argument(line: str) -> tuple[int, str] | None:
    """Return (column, token) that ``flock`` is given, ignoring options and fds.

    The column travels with the token so a use can be ordered against an
    assignment that shares its line.
    """
    match = _FLOCK.search(line)
    if match is None:
        return None
    for token in re.finditer(r"\S+", line[match.end() :]):
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
    """
    found: list[tuple[int, int, str, str]] = []
    for offset, line in enumerate(block):
        for match in _ASSIGNMENT.finditer(line):
            name, value = match.group(1), match.group(2)
            found.append((start + offset + 1, match.start(), name, value.strip("\"'")))
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
    """Return (line, column, token) for everything that could name a lock file."""
    candidates: list[tuple[int, int, str]] = []
    for offset, line in enumerate(block):
        number = start + offset + 1
        assignment_only = _ASSIGNMENT.search(line) is not None and _FLOCK.search(line) is None
        if not assignment_only:
            candidates.extend(
                (number, match.start(), match.group(0)) for match in _LOCK_PATH.finditer(line)
            )
        candidates.extend(
            (number, match.start(1), match.group(1)) for match in _EXEC_REDIRECT.finditer(line)
        )
        argument = _flock_argument(line)
        if argument is not None:
            candidates.append((number, argument[0], argument[1]))
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


def _scan_block(lines: Sequence[str], start: int, end: int) -> list[tuple[int, str]]:
    """Scan one fenced block that mentions ``flock``.

    The block, not the line, is the unit, because three of the four recipe
    forms above separate ``flock`` from its path. Every lock target in the
    block must be canonical; a block whose lock target cannot be identified at
    all is reported for naming no canonical path.

    Every target, not merely the first: a block that contrasts the canonical
    recipe with a dead scheme names two, and stopping at the canonical one hid
    the dead one, which is the exact evidence shape issue #4366 recorded.
    """
    block = lines[start:end]
    targets = _lock_targets(block, start)
    findings = _non_canonical(targets)
    if not targets:
        flock_lines = [
            start + offset + 1 for offset, line in enumerate(block) if _FLOCK.search(line)
        ]
        findings.append((flock_lines[0] if flock_lines else start + 1, ""))
    return findings


def _prose_runs(lines: Sequence[str], skipped: set[int], fenced: set[int]) -> list[tuple[int, int]]:
    """Return (start, end) indices for each run of unfenced prose, end exclusive.

    A run is a maximal group of consecutive lines that are neither fenced nor
    skipped nor blank, so the unit is one Markdown paragraph. The blank line is
    the boundary because it is the boundary Markdown itself uses: it is what
    separates a recipe from the paragraph that discusses it. Taking every
    unfenced line in a file as one unit instead would let a variable assigned
    in one section resolve a ``flock`` in another.
    """
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, line in enumerate(lines):
        number = index + 1
        if number in skipped or number in fenced or not line.strip():
            if start is not None:
                runs.append((start, index))
                start = None
            continue
        if start is None:
            start = index
    if start is not None:
        runs.append((start, len(lines)))
    return runs


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

    A fence already surfaces both through ``_scan_block``'s no-targets
    fallback. Unfenced runs suppress that fallback so prose about ``flock``
    does not fire, and this restores the case the suppression was never meant
    to cover.

    Reported with an empty path, the same shape a fence uses, because the point
    is that no path could be determined. It reports at the ``flock`` line
    rather than at the assignment, because the call is what is unverifiable.
    Measured over 3518 tracked Markdown files before landing: zero gain a
    finding.
    """
    assignments = _assignments(block, start)
    unresolved: list[tuple[int, str]] = []
    for offset, line in enumerate(block):
        argument = _flock_argument(line)
        if argument is None:
            continue
        column, token = argument
        variable = _BARE_VARIABLE.match(token)
        if variable is None:
            continue
        number = start + offset + 1
        live = _value_in_effect(assignments, variable.group(1), (number, column))
        if live is None or not _is_path_like(live[1]):
            unresolved.append((number, ""))
    return unresolved


def _scan_prose_run(lines: Sequence[str], start: int, end: int) -> list[tuple[int, str]]:
    """Scan one run of unfenced prose, resolving locks the way a fence does.

    A recipe does not become canonical by losing its fence. Before this ran,
    ``LOCK=/var/locks/branch.lock`` followed by ``flock "$LOCK" git push`` was
    reported inside a fence and invisible outside one, because the unfenced
    path read each line alone: the assignment line has no ``flock`` and the
    ``flock`` line has no path (issue #4635).

    Unlike ``_scan_block`` this does not report "names no canonical path" for
    the whole run. Prose discusses ``flock`` without prescribing anything, and
    the blanket empty finding over unfenced runs fired on 13 tracked files that
    only mention the tool, including this module's own rule mirror. A run that
    records a dead scheme as evidence opts out with ``push-lock-historical``,
    the same token a fence uses.

    ``_unresolved_flock_variables`` is the narrow exception, because that
    asymmetry was meant for prose *about* ``flock`` and would otherwise swallow
    a real call whose lock cannot be read.
    """
    block = lines[start:end]
    if not any(_FLOCK.search(line) for line in block):
        return []
    if any(HISTORICAL_MARKER in line for line in block):
        return []
    return _non_canonical(_lock_targets(block, start)) + _unresolved_flock_variables(block, start)


def scan_text(text: str) -> list[tuple[int, str]]:
    """Return (line number, offending path) for every non-canonical lock path.

    Two units, one resolver. A fenced block is scanned by ``_scan_block`` and
    each run of unfenced prose by ``_scan_prose_run``; both read their lock
    targets from ``_lock_targets``, so a recipe resolves the same way whether
    or not it carries a fence. Only the fenced unit reports "names no
    canonical path", because only a fence is unambiguously a prescription.

    An empty path means the block invokes ``flock`` without naming the
    canonical path anywhere in it.
    """
    lines = text.splitlines()
    skipped = _historical_line_numbers(lines)
    findings: list[tuple[int, str]] = []
    fenced: set[int] = set()
    for start, end in _fenced_blocks(lines):
        fenced.update(range(start + 1, end + 1))
        if any(number in skipped for number in range(start + 1, end + 1)):
            continue
        if not any(_FLOCK.search(line) for line in lines[start:end]):
            continue
        findings.extend(_scan_block(lines, start, end))
    for start, end in _prose_runs(lines, skipped, fenced):
        findings.extend(_scan_prose_run(lines, start, end))
    return sorted(findings)


def tracked_markdown(repo_root: Path) -> list[str]:
    """Return tracked Markdown paths in scope, read from the index.

    ci-scripts MUST 9 wants a named ref for a claim about what the repository
    *contains*, and exempts a check whose subject is the state about to be
    committed. This is that second kind: it runs from ``pre_pr.py`` before a
    commit or a push, and it reads content from the working tree. Taking the
    inventory from ``HEAD`` instead left a staged new Markdown file invisible
    to the gate, so a fifth lock scheme could be committed through it. The
    index is the inventory that matches the content being read.
    """
    result = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files", "-z", "--cached"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git ls-files failed: {result.stderr.strip()}")
    paths = [entry for entry in result.stdout.split("\0") if entry.endswith(".md")]
    return [path for path in paths if not path.startswith(EXCLUDED_PREFIXES)]


def check_paths(repo_root: Path, paths: Iterable[str]) -> tuple[list[str], int]:
    """Return (violation messages, examined file count)."""
    violations: list[str] = []
    examined = 0
    for relative in paths:
        target = repo_root / relative
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        examined += 1
        for line_number, candidate in scan_text(text):
            if candidate:
                detail = (
                    f"push lock '{candidate}' is not {CANONICAL_TEMPLATE} "
                    "(see .claude/rules/push-lock.md, issue #4366)"
                )
            else:
                detail = NO_PATH_MESSAGE.format(template=CANONICAL_TEMPLATE)
            violations.append(f"{relative}:{line_number}: {detail}")
    return violations, examined


def validate_push_lock_paths(repo_root: Path) -> bool:
    """Return True when every tracked prescription names the canonical lock path.

    Entry point matching the ``validate_*(repo_root) -> bool`` contract used by
    ``pre_pr.py``.
    """
    try:
        paths = tracked_markdown(repo_root)
    except (RuntimeError, OSError) as error:
        print(f"[FAIL] push-lock check could not read the index: {error}", file=sys.stderr)
        return False
    violations, examined = check_paths(repo_root, paths)
    if not violations:
        print(f"[PASS] push-lock: 0 violation(s) in {examined} tracked Markdown file(s)")
        return True
    print(
        f"[FAIL] {len(violations)} push-lock path(s) in {examined} tracked Markdown "
        "file(s) disagree with the canonical form:",
        file=sys.stderr,
    )
    for violation in violations:
        print(f"  {violation}", file=sys.stderr)
    return False


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    try:
        paths = tracked_markdown(repo_root)
    except (RuntimeError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    violations, examined = check_paths(repo_root, paths)
    for violation in violations:
        print(violation, file=sys.stderr)
    print(f"push-lock: {len(violations)} violation(s) in {examined} tracked Markdown file(s)")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())

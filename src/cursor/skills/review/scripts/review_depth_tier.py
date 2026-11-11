#!/usr/bin/env python3
"""Compute the review depth tier from a unified diff.

The technical-review contract scales its caller-trace floor with the size and
spread of a change.  This script derives that tier from the diff alone so the
reviewer does not re-derive it by judgment.  It is a pure function of the diff
text and the exclusion globs: the same input always yields the same tier.

Signals (all counted over human-authored files, after ``--exclude`` globs):

* ``lines``: added plus removed lines.
* ``files``: distinct changed paths.
* ``dirs``: distinct parent directories of the changed paths.
* ``public_symbols``: added or removed lines that declare a public symbol
  (see ``PUBLIC_SYMBOL_PATTERNS``) in a source file.

The tier is the highest tier any one signal reaches.  ``standard`` is the
current protocol: one real caller per changed contract.

This is separate from the analyst's Tier 1-5 complexity assessment in the
``review`` skill.  That one is judged by a model.  This one is computed.

Usage:
    git diff "origin/$BASE...HEAD" | review_depth_tier.py [--exclude GLOB ...]

EXIT CODES (ADR-035):
    0 - A tier was emitted on stdout as JSON.
    2 - Config error: stdin was empty or held no diff headers.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import PurePosixPath

TIERS: tuple[str, ...] = ("standard", "elevated", "high")

# (elevated_at, high_at): a signal at or above a bound reaches that tier.
# These are judgment calls, not measured values; edit them here and the
# boundary tests in tests/skills/review/test_review_depth_tier.py together.
THRESHOLDS: dict[str, tuple[int, int]] = {
    "lines": (201, 1001),
    "files": (11, 31),
    "dirs": (4, 9),
    "public_symbols": (3, 10),
}

# Caller-trace floor per tier: callers to read per changed public symbol (or all
# of them when fewer exist) and distinct caller files to cover when that many
# exist.  Callers past the count are out of scope.  The count is the whole
# requirement, so meeting it never leaves an unverified caller.
CALLER_TRACE_FLOOR: dict[str, dict[str, int]] = {
    "standard": {"callers": 1, "files": 1},
    "elevated": {"callers": 3, "files": 2},
    "high": {"callers": 10, "files": 3},
}

# Lockfiles never count: no reviewer reads them as authored code, and a bulk
# dependency bump would otherwise lift a small change to ``high``.  Generated
# trees are repository-specific, so the caller passes those with ``--exclude``.
DEFAULT_EXCLUDES: tuple[str, ...] = (
    "*.lock",
    "*.lockb",
    "*package-lock.json",
    "*packages.lock.json",
    "*pnpm-lock.yaml",
    "*go.sum",
)

SOURCE_SUFFIXES = frozenset(
    {
        ".py", ".ps1", ".psm1", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
        ".cs", ".java", ".kt", ".go", ".rs", ".rb", ".php", ".swift", ".c",
        ".cc", ".cpp", ".h", ".hpp",
    }
)  # fmt: skip

# A declaration of a public symbol on a changed line.  A leading underscore
# marks a private name in Python; ``export`` and ``public`` mark the others.
PUBLIC_SYMBOL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*(?:async\s+)?def\s+(?!_)\w+\s*\("),
    re.compile(r"^\s*class\s+(?!_)\w+"),
    re.compile(r"^\s*export\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|let|interface|type|enum)\b"),
    re.compile(r"^\s*public\s+(?!static\s+void\s+Main\b)[\w<>\[\],.?\s]+\("),
    re.compile(r"^\s*function\s+\w+-\w+"),
    re.compile(r"^\s*func\s+[A-Z]\w*\s*\("),
    re.compile(r"^\s*pub\s+(?:async\s+)?(?:fn|struct|enum|trait)\b"),
)  # fmt: skip

# Git quotes a path holding non-ASCII bytes, quotes, backslashes, or control
# characters: ``diff --git "a/caf\303\251.py" "b/caf\303\251.py"``.  Either
# side may be quoted on its own.
_DIFF_HEADER = re.compile(r'^diff --git (?:"a/(?:.*?)"|a/(?:.*?)) (?:"b/(.*)"|b/(.*))$')
_ESCAPE = re.compile(r"(?:\\[0-7]{3})+|\\.")
_SIMPLE_ESCAPES = {"t": "\t", "n": "\n", '"': '"', "\\": "\\"}


@dataclass
class Signals:
    lines: int = 0
    files: int = 0
    dirs: int = 0
    public_symbols: int = 0
    paths: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, int]:
        return {
            "lines": self.lines,
            "files": self.files,
            "dirs": self.dirs,
            "public_symbols": self.public_symbols,
        }


def _is_excluded(path: str, excludes: Sequence[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in excludes)


def _is_source(path: str) -> bool:
    return PurePosixPath(path).suffix.lower() in SOURCE_SUFFIXES


def _is_public_declaration(line: str) -> bool:
    return any(pattern.match(line) for pattern in PUBLIC_SYMBOL_PATTERNS)


def _unescape(match: re.Match[str]) -> str:
    text = match.group()
    if len(text) > 2:  # a run of octal escapes is UTF-8 bytes
        octets = (int(text[i + 1 : i + 4], 8) for i in range(0, len(text), 4))
        return bytes(octets).decode("utf-8", errors="replace")
    return _SIMPLE_ESCAPES.get(text[1], text[1])


def _new_path(match: re.Match[str]) -> str:
    """Return the post-image path from a header match, unquoting a quoted one."""
    quoted, plain = match.group(1), match.group(2)
    if plain is not None:
        return plain
    return _ESCAPE.sub(_unescape, quoted)


def parse_diff(diff_text: str, excludes: Sequence[str] = ()) -> Signals:
    """Count the tier signals in a unified diff.

    A rename with no content hunks still counts as one changed file.  Binary
    files count as a file but add no lines.  A quoted header path is unquoted
    before it is matched against ``--exclude`` globs.
    """
    signals = Signals()
    current: str | None = None
    counting = False
    in_hunk = False
    seen: list[str] = []
    for raw in diff_text.splitlines():
        header = _DIFF_HEADER.match(raw)
        if header:
            current = _new_path(header)
            counting = not _is_excluded(current, excludes)
            in_hunk = False
            if counting and current not in seen:
                seen.append(current)
            continue
        if not counting or current is None:
            continue
        if raw.startswith("@@"):
            in_hunk = True
            continue
        # Before the first hunk, ``---`` and ``+++`` are file headers.  Inside a
        # hunk they are content: a removed YAML ``---`` or C ``--i;`` line.
        if in_hunk and raw.startswith(("+", "-")):
            signals.lines += 1
            if _is_source(current) and _is_public_declaration(raw[1:]):
                signals.public_symbols += 1
    signals.paths = seen
    signals.files = len(seen)
    signals.dirs = len({str(PurePosixPath(p).parent) for p in seen})
    return signals


def tier_for(signals: Signals) -> tuple[str, list[str]]:
    """Return the highest tier any signal reaches and the signals that set it."""
    values = signals.as_dict()
    level = 0
    reasons: list[str] = []
    for name, (elevated_at, high_at) in THRESHOLDS.items():
        value = values[name]
        reached = 2 if value >= high_at else 1 if value >= elevated_at else 0
        if reached > level:
            level = reached
            reasons = [name]
        elif reached == level and reached > 0:
            reasons.append(name)
    return TIERS[level], reasons


def compute(diff_text: str, excludes: Sequence[str] = ()) -> dict[str, object]:
    excludes = (*DEFAULT_EXCLUDES, *excludes)
    signals = parse_diff(diff_text, excludes)
    tier, reasons = tier_for(signals)
    header = (
        f"REVIEW_DEPTH: {tier} lines={signals.lines} files={signals.files} "
        f"dirs={signals.dirs} public_symbols={signals.public_symbols}"
    )
    return {
        "header": header,
        "tier": tier,
        "signals": signals.as_dict(),
        "selected_by": reasons,
        "thresholds": {k: {"elevated": v[0], "high": v[1]} for k, v in THRESHOLDS.items()},
        "caller_trace_floor": CALLER_TRACE_FLOOR[tier],
        "excluded_globs": list(excludes),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        epilog="exit codes:\n  0  tier emitted as JSON\n  2  stdin held no diff headers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="GLOB",
        help=(
            "fnmatch glob of a path to leave out (generated file, lockfile, "
            "fixture). Repeatable. Use the same exclusions as the scope accounting."
        ),
    )
    return parser


def main(argv: Iterable[str] | None = None, stdin: str | None = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    diff_text = sys.stdin.read() if stdin is None else stdin
    if not any(_DIFF_HEADER.match(line) for line in diff_text.splitlines()):
        print("review_depth_tier: no 'diff --git' headers on stdin", file=sys.stderr)
        return 2
    print(json.dumps(compute(diff_text, args.exclude), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

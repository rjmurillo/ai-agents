"""CODEOWNERS pattern matching and coverage for the closure manifest.

ADR-101's exit condition for the computed protected set says CODEOWNERS covers
the manifest's file set exactly, "with any deliberate exclusion named in the
manifest". This module answers the first half: which files of a set does no
CODEOWNERS entry own.

Pattern semantics follow gitignore, which CODEOWNERS documents as its dialect
(GitHub Docs, "About code owners"). The subset implemented is the one this
repository's `.github/CODEOWNERS` uses and the one a hand-written protected
path list would use:

  * a pattern with a leading `/` is anchored at the repository root;
  * a pattern with no `/` except a trailing one matches at any depth;
  * a trailing `/` matches everything under that directory;
  * `*` matches within one path segment, `**` across segments, `?` one
    character;
  * the last matching entry wins, so a later entry can only narrow or move
    ownership, and an entry that names no owner releases the file.

Not implemented, and refused rather than guessed: negation (`!pattern`), bracket
character classes and backslash escapes. A pattern using one is reported as
unsupported, and the coverage answer for the file set is then not trustworthy,
so `coverage` raises instead of returning a partial result.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_UNSUPPORTED = re.compile(r"[\[\]\\]|^!")


class UnsupportedPatternError(ValueError):
    """A CODEOWNERS pattern uses syntax this matcher does not implement."""


@dataclass(frozen=True, slots=True)
class Rule:
    """One CODEOWNERS entry: a pattern and the owners it names."""

    pattern: str
    owners: tuple[str, ...]
    line: int


def parse(text: str) -> list[Rule]:
    """Parse CODEOWNERS text into rules, in file order."""
    rules: list[Rule] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", maxsplit=1)[0].strip()
        if not line:
            continue
        pattern, *owners = line.split()
        if _UNSUPPORTED.search(pattern):
            raise UnsupportedPatternError(f"line {number}: unsupported pattern {pattern!r}")
        rules.append(Rule(pattern, tuple(owners), number))
    return rules


def _segment_regex(segment: str) -> str:
    out: list[str] = []
    for char in segment:
        out.append("[^/]*" if char == "*" else "[^/]" if char == "?" else re.escape(char))
    return "".join(out)


@lru_cache(maxsize=512)
def compile_pattern(pattern: str) -> re.Pattern[str]:
    """Compile one CODEOWNERS pattern to an anchored regular expression.

    A slash at the start or in the middle anchors the pattern at the repository
    root; a pattern with no such slash matches at any depth. `**` as a whole
    segment spans directories, and a trailing `**` spans everything below. Every
    pattern also matches what lies beneath a directory it names, as gitignore does.
    """
    body = pattern.strip("/")
    if not body:
        return re.compile(r"(?s).*")
    anchored = pattern.startswith("/") or "/" in body
    segments = body.split("/")
    parts: list[str] = []
    for index, segment in enumerate(segments):
        last = index == len(segments) - 1
        if segment == "**":
            parts.append(".*" if last else "(?:.*/)?")
        else:
            parts.append(_segment_regex(segment) + ("" if last else "/"))
    prefix = "" if anchored else "(?:.*/)?"
    return re.compile(rf"(?s){prefix}{''.join(parts)}(?:/.*)?")


def owners_of(path: str, rules: Iterable[Rule]) -> tuple[str, ...]:
    """Owners of ``path`` under the last matching rule; () when none matches."""
    owners: tuple[str, ...] = ()
    for rule in rules:
        if compile_pattern(rule.pattern).fullmatch(path):
            owners = rule.owners
    return owners


def coverage(
    paths: Iterable[str],
    rules: list[Rule],
    exclusions: Mapping[str, str],
) -> tuple[list[str], list[str]]:
    """Split ``paths`` into ``(uncovered, excluded)``.

    ``exclusions`` maps a path to the reason it is deliberately left unowned. A
    path is excluded only when it is named there exactly; a reason is required,
    so an empty string does not exclude.
    """
    uncovered: list[str] = []
    excluded: list[str] = []
    for path in sorted(set(paths)):
        if owners_of(path, rules):
            continue
        if exclusions.get(path):
            excluded.append(path)
        else:
            uncovered.append(path)
    return uncovered, excluded


def load(codeowners: Path) -> list[Rule]:
    """Read and parse a CODEOWNERS file."""
    return parse(codeowners.read_text(encoding="utf-8"))

#!/usr/bin/env python3
"""Resolve numbered ADR aliases for the citation-freshness gates."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from check_adr_links import ADR_BASENAME, adr_number
from stale_script_refs import HISTORICAL_ROOTS

# Colon form: ADR number, colon, line number, and no space after the colon.
# "ADR-035: 0 ok" stays an exit code because a space follows the colon.
# Prose form: ADR number, up to six words, then lines and a line range.
_ADR_CITE = re.compile(
    r"\bADR-(?P<number>\d+)(?::|\s+(?:[A-Za-z]+\s+){0,6}lines?\s+)"
    r"(?P<start>\d+)(?:-(?P<end>\d+))?\b",
    re.IGNORECASE,
)


def _historical(path: str) -> bool:
    """Return whether path sits under a historical root the gates already exempt."""
    return path.startswith(HISTORICAL_ROOTS)


_ADR_PARENTS = frozenset({"architecture", "adr", "adrs"})


def _adr_candidates(tracked: set[str]) -> dict[str, set[str]]:
    """Map a zero-padded ADR number to the files that use it."""
    candidates: dict[str, set[str]] = {}
    for path in tracked:
        if _historical(path):
            continue
        pure = PurePosixPath(path)
        if pure.parent.name not in _ADR_PARENTS:
            continue
        if not ADR_BASENAME.match(pure.name):
            continue
        number = adr_number(pure.name)
        if number is None:
            continue
        candidates.setdefault(f"{number:03d}", set()).add(path)
    return candidates


def _unique_adr(paths: set[str]) -> str | None:
    """Return the only path in a number's set, or None when it is empty or split."""
    if len(paths) != 1:
        return None
    return next(iter(paths))


def _citation_aliases(tracked: set[str]) -> dict[str, str]:
    """Map a zero-padded ADR number to its file when that number is unique.

    The number parse is ``adr_number`` from the ADR link checker. Serena
    memories and other historical roots are not ADR records, so they do not
    compete. A number that still names two files is left unresolved.
    """
    return {
        name: path
        for name, paths in _adr_candidates(tracked).items()
        if (path := _unique_adr(paths)) is not None
    }


def _citation_aliases_across(base_tracked: set[str], head_tracked: set[str]) -> dict[str, str]:
    """Resolve ADR numbers from the merge base and from HEAD.

    A number that names two files on either side stays unresolved. A number
    that exists only at the merge base keeps that path, so a deletion still
    fails at HEAD. Different unique paths are a rename, and the alias then
    names the HEAD file.
    """
    base = _adr_candidates(base_tracked)
    head = _adr_candidates(head_tracked)
    aliases: dict[str, str] = {}
    for number in set(base) | set(head):
        if len(base.get(number, set())) > 1 or len(head.get(number, set())) > 1:
            continue
        head_path = _unique_adr(head.get(number, set()))
        if head_path is not None:
            aliases[number] = head_path
            continue
        base_path = _unique_adr(base.get(number, set()))
        if base_path is not None:
            aliases[number] = base_path
    return aliases


def _adr_base_path(head_path: str, base_tracked: set[str]) -> str | None:
    """Return the one merge-base ADR file that shares ``head_path``'s number."""
    number = adr_number(PurePosixPath(head_path).name)
    if number is None:
        return None
    return _unique_adr(_adr_candidates(base_tracked).get(f"{number:03d}", set()))


def _expand_adr_citations(text: str, aliases: dict[str, str]) -> str:
    """Rewrite ADR-NNN line cites as path:line cites the matcher already checks."""

    def adr(match: re.Match[str]) -> str:
        path = aliases.get(f"{int(match.group('number')):03d}")
        if path is None:
            return match.group(0)
        end = f"-{match.group('end')}" if match.group("end") else ""
        return f"{path}:{match.group('start')}{end}"

    return _ADR_CITE.sub(adr, text)

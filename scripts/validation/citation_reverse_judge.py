#!/usr/bin/env python3
"""Per-citation judgment for the citation reverse pass.

Extracted from citation_reverse_pass.py at the file-size ceiling.
The pass imports this module by its bare sibling name.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Protocol, cast

from check_citation_freshness import Finding, _citation_anchors
from citation_adr_aliases import _adr_base_path, _expand_adr_citations
from citation_anchors import _CITATION
from citation_head_state import _ChangeSet, _HeadFileCache, _reworded_line_pairs


class _CiteView(Protocol):
    """Citation fields the judge reads. The cite is frozen, so each field is read-only."""

    @property
    def citing_file(self) -> str: ...

    @property
    def line_number(self) -> int: ...

    @property
    def spelling(self) -> str: ...

    @property
    def start(self) -> int: ...

    @property
    def end(self) -> int: ...

    @property
    def target(self) -> str: ...

    @property
    def label(self) -> str: ...


class _TreesView(Protocol):
    """Tracked paths and file reads at the merge base and at HEAD."""

    @property
    def base_tracked(self) -> set[str]: ...

    @property
    def head_tracked(self) -> set[str]: ...

    @property
    def base_files(self) -> _HeadFileCache: ...

    @property
    def head_files(self) -> _HeadFileCache: ...


class _TallyView(Protocol):
    """Counters the judge increments."""

    examined: int
    stale_at_base: int


class _ReversePass(Protocol):
    """Pass functions this module calls, without a static import.

    The pass imports this file by the bare name citation_reverse_judge.
    Importing the pass back would put one file under two mypy names.
    """

    _judge: Callable[
        [_CiteView, str, list[str], set[str], _HeadFileCache, str],
        tuple[Finding | None, list[str] | None],
    ]
    _new_finding: Callable[
        [_CiteView, list[str], _ChangeSet, _TreesView, list[str], str],
        Finding | None,
    ]


def _gate() -> _ReversePass:
    """Load the pass by its bare sibling name.

    importlib keeps mypy from following the import.
    """
    module = importlib.import_module("citation_reverse_pass")
    return cast(_ReversePass, module)


def _judge_one(
    cite: _CiteView,
    segment: str,
    expanded: str,
    citing_lines: list[str],
    line_number: int,
    markdown: bool,
    added: set[int],
    aliases: dict[str, str],
    retained: dict[str, dict[int, str]],
    trees: _TreesView,
    tally: _TallyView,
    findings: list[Finding],
    changes: _ChangeSet,
) -> None:
    """Judge one reverse-pass citation and record a finding or base debt."""
    gate = _gate()
    tally.examined += 1
    anchors = _citation_anchors(cite.label, expanded, segment, citing_lines, line_number, markdown)
    touched = line_number in added
    citing_file = cite.citing_file
    if citing_file not in retained:
        old = trees.base_files.lines(citing_file) if citing_file in trees.base_tracked else []
        retained[citing_file] = _reworded_line_pairs(old, citing_lines)
    old_text = _expand_adr_citations(retained[citing_file].get(line_number, ""), aliases)
    kept = any(match.group(0) == cite.spelling for match in _CITATION.finditer(old_text))
    # A new token is written against HEAD. A token the edit kept still
    # belongs to the author, so base debt does not excuse it.
    if touched and not kept:
        finding, _lines = gate._judge(
            cite,
            cite.target,
            anchors,
            trees.head_tracked,
            trees.head_files,
            segment,
        )
        if finding is not None:
            findings.append(finding)
        return
    base_path = cite.target
    if cite.target not in trees.base_tracked:
        paired = _adr_base_path(cite.target, trees.base_tracked)
        if paired is not None:
            base_path = paired
    base_finding, base_lines = gate._judge(
        cite, base_path, anchors, trees.base_tracked, trees.base_files, segment
    )
    base_ok = base_finding is None and base_lines is not None
    if not base_ok and not touched:
        # Debt this branch did not write. Moving lines under it, even the
        # quoted line or a block of cited lines, does not make it the
        # branch's citation (PR #7482). Count it; never block on it.
        tally.stale_at_base += 1
        return
    if base_ok:
        finding = gate._new_finding(cite, anchors, changes, trees, base_lines or [], segment)
    else:
        finding, _lines = gate._judge(
            cite,
            cite.target,
            anchors,
            trees.head_tracked,
            trees.head_files,
            segment,
        )
    if finding is not None:
        findings.append(finding)

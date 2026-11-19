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
from citation_anchors import (
    _CITATION,
    _adr_base_path,
    _anchor_matches,
    _expand_adr_citations,
    _moved_cluster,
)
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
        [_CiteView, str, list[str], set[str], _HeadFileCache],
        tuple[Finding | None, list[str] | None],
    ]
    _new_finding: Callable[
        [_CiteView, list[str], _ChangeSet, _TreesView, list[str]],
        Finding | None,
    ]


def _gate() -> _ReversePass:
    """Load the pass by its bare sibling name.

    importlib keeps mypy from following the import.
    """
    module = importlib.import_module("citation_reverse_pass")
    return cast(_ReversePass, module)


def _cluster_finding(
    cite: _CiteView, base_lines: list[str] | None, trees: _TreesView
) -> Finding | None:
    """Return a move finding when four or more cited lines relocated together."""
    if base_lines is None or cite.target not in trees.head_tracked:
        return None
    cluster = _moved_cluster(cite.start, cite.end, base_lines, trees.head_files.lines(cite.target))
    if cluster is None:
        return None
    new_start, new_end = cluster
    span = f"{new_start}-{new_end}" if new_end != new_start else str(new_start)
    reason = (
        f"the text at lines {cite.start}-{cite.end} at the merge base moved at HEAD; "
        f"suggested citation {cite.target}:{span}"
    )
    return Finding(cite.citing_file, cite.line_number, cite.label, reason)


def _quote_moved_outside(
    anchors: list[str],
    base_lines: list[str] | None,
    head_lines: list[str] | None,
    start: int,
    end: int,
) -> bool:
    """Return whether a quoted anchor's only line changed and left the range.

    A bare name is not enough. Debt stays quiet when that quoted line
    keeps its number. A quote that occurs once, on a new line, is a finding.
    """
    if not base_lines or not head_lines:
        return False
    for anchor in anchors:
        if " " not in anchor or len(anchor) < 12:
            continue
        base_hits = [
            number for number, text in enumerate(base_lines, 1) if _anchor_matches(anchor, text)
        ]
        head_hits = [
            number for number, text in enumerate(head_lines, 1) if _anchor_matches(anchor, text)
        ]
        moved = len(base_hits) == 1 and len(head_hits) == 1 and base_hits[0] != head_hits[0]
        if moved and not start <= head_hits[0] <= end:
            return True
    return False


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
            cite, cite.target, anchors, trees.head_tracked, trees.head_files
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
        cite, base_path, anchors, trees.base_tracked, trees.base_files
    )
    base_ok = base_finding is None and base_lines is not None
    if not base_ok and not touched:
        finding = _cluster_finding(cite, base_lines, trees)
        if finding is not None:
            findings.append(finding)
            return
        head_finding, head_lines = gate._judge(
            cite, cite.target, anchors, trees.head_tracked, trees.head_files
        )
        if head_finding is not None and _quote_moved_outside(
            anchors, base_lines, head_lines, cite.start, cite.end
        ):
            findings.append(head_finding)
            return
        tally.stale_at_base += 1
        return
    if base_ok:
        finding = gate._new_finding(cite, anchors, changes, trees, base_lines or [])
    else:
        finding, _lines = gate._judge(
            cite, cite.target, anchors, trees.head_tracked, trees.head_files
        )
    if finding is not None:
        findings.append(finding)

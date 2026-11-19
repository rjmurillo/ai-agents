#!/usr/bin/env python3
"""Per-citation judgment for the citation reverse pass.

Extracted from citation_reverse_pass.py at the file-size ceiling.
The scan loads this module inside the grep loop.
"""

from __future__ import annotations

import citation_reverse_pass as gate
from check_citation_freshness import Finding, _citation_anchors
from citation_anchors import _CITATION, _adr_base_path, _expand_adr_citations, _moved_cluster
from citation_head_state import _reworded_line_pairs


def _cluster_finding(
    cite: gate._Cite, base_lines: list[str] | None, trees: gate._Trees
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


def _judge_one(
    cite: gate._Cite,
    segment: str,
    expanded: str,
    citing_lines: list[str],
    line_number: int,
    markdown: bool,
    added: set[int],
    aliases: dict[str, str],
    retained: dict[str, dict[int, str]],
    trees: gate._Trees,
    tally: gate._Tally,
    findings: list[Finding],
    changes: gate._ChangeSet,
) -> None:
    """Judge one reverse-pass citation and record a finding or base debt."""
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
        if finding is None:
            tally.stale_at_base += 1
        else:
            findings.append(finding)
        return
    if base_ok:
        finding = gate._new_finding(cite, anchors, changes, trees, base_lines or [])
    else:
        finding, _lines = gate._judge(
            cite, cite.target, anchors, trees.head_tracked, trees.head_files
        )
    if finding is not None:
        findings.append(finding)

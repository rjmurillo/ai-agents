#!/usr/bin/env python3
"""Reverse pass of the citation-freshness gate: inbound citations to changed files.

The forward gate (``check_citation_freshness.py``, issue #5337) checks
citations on lines ADDED since the base ref. A branch that edits, renames,
or deletes a file can also break citations elsewhere that point INTO it,
on lines the branch never touched (PR #6689 and PR #6584 were caught only
by a post-PR reviewer). This pass finds them: for every file modified,
retyped, renamed, or deleted in ``base...HEAD``, it greps HEAD for
citations that target the file and judges each one twice, once against
the cited file at the merge base and once at HEAD, with the forward
gate's own existence, range, and anchor checks.

Base-derived blocking, the model ``.claude/rules/ci-scripts.md`` MUST 14
describes for the taste and ruff ratchets: a citation blocks only when it
held at the merge base and fails at HEAD, so a branch is red only for
drift it caused. A citation already stale at the base is counted and
printed, never blocking, and no baseline file exists. An anchorless
citation is also judged by its content: when the base text of the cited
range is distinctive, unique at the merge base, and sits verbatim at one
other place at HEAD, the content moved and the citation is stale. Text edited in place is not
flagged, because the citation may still be right. A finding names the
corrected citation when it can compute one, keeping the anchor's offset
inside the cited range.

A slashless name (``name.py:3``) counts here when exactly one file
tracked at the merge base has that basename and that file changed; the
forward gate reads slashless names only for repository-root files. That
covers the PR #5812 shape behind PR #6584, a bare name added in the same
change that rewrote the cited file. A line the branch added was written
against HEAD, so it is judged at HEAD only, with no merge-base comparison. Citations the forward gate already
checks (an added line whose path it resolves) are skipped, so nothing is
reported twice. Exemptions and the reasoned ignore marker are the forward
gate's own, imported, not copied.

Not caught: a citation with no ``path:N`` shape (prose such as "ADR-101
lines 278-284", the PR #6689 miss), a citing file in an exempt historical
tree, and an anchorless citation whose cited lines were edited in place.

EXIT CODES (ADR-035): 0 = no new stale citations (prints examined counts
so an idle run is distinguishable from a clean one) or no base ref
resolved (prints ``[SKIP]``); 1 = findings; 2 = git failed."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from check_citation_freshness import (  # noqa: E402
    Finding,
    _anchor_finding,
    _citation_anchors,
    _has_ignore_marker,
    _is_exempt_citing_file,
    _report_findings,
    _resolve_cited_range,
)
from checks_common import _resolve_default_base_ref  # noqa: E402
from citation_anchors import (  # noqa: E402
    _CITATION,
    _EXTENSIONS,
    _URL,
    _anchor_matches,
    _same_line_segment,
)
from citation_head_state import (  # noqa: E402
    HeadReadError,
    _added_lines_since_base,
    _git,
    _head_tracked_paths,
    _HeadFileCache,
)
from citation_scope import string_literal_lines  # noqa: E402

_PREFIX = "[citation-reverse-pass]"

# A cheap superset of _CITATION for git grep: any known extension followed
# by ``:digit``. One pattern keeps the grep near 0.4s on this tree; one
# fixed-string needle per changed file timed out at 60s on a wide base.
_GREP_PREFILTER = rf"\.({_EXTENSIONS}):[0-9]"


@dataclass(frozen=True, slots=True)
class _ChangeSet:
    """Base-side paths whose content or name changed, and where renames went."""

    changed: frozenset[str]
    renamed_to: dict[str, str]


@dataclass(frozen=True, slots=True)
class _Trees:
    """Tracked paths and lazy file reads at the merge base and at HEAD."""

    base_tracked: set[str]
    head_tracked: set[str]
    base_files: _HeadFileCache
    head_files: _HeadFileCache


@dataclass(frozen=True, slots=True)
class _Cite:
    """One citation occurrence on one citing line."""

    citing_file: str
    line_number: int
    text: str
    target: str
    start: int
    end: int
    ranged: bool

    @property
    def label(self) -> str:
        suffix = f"-{self.end}" if self.ranged else ""
        return f"{self.target}:{self.start}{suffix}"


def _merge_base(repo_root: Path, base_ref: str) -> str | None:
    exit_code, stdout, _stderr = _git(repo_root, ["merge-base", base_ref, "HEAD"])
    sha = stdout.strip()
    return sha if exit_code == 0 and sha else None


def _change_set(repo_root: Path, base_ref: str) -> _ChangeSet | None:
    """Read ``--name-status`` for base...HEAD; added files cite nothing old."""
    exit_code, stdout, _stderr = _git(
        repo_root,
        [
            "-c",
            "core.quotePath=false",
            "diff",
            "--no-color",
            "--no-ext-diff",
            "--no-relative",
            "--name-status",
            "-z",
            "--find-renames",
            f"{base_ref}...HEAD",
        ],
    )
    if exit_code != 0:
        return None
    tokens = stdout.split("\0")
    changed: set[str] = set()
    renamed_to: dict[str, str] = {}
    index = 0
    while index < len(tokens):
        status = tokens[index]
        if not status:
            index += 1
            continue
        if status[0] in "RC":
            old, new = tokens[index + 1], tokens[index + 2]
            index += 3
            if status[0] == "R":
                changed.add(old)
                renamed_to[old] = new
            continue
        if status[0] in "MTD":
            changed.add(tokens[index + 1])
        index += 2
    return _ChangeSet(frozenset(changed), renamed_to)


def _grep_head(repo_root: Path) -> list[tuple[str, int, str]] | None:
    """Return (path, line number, text) for HEAD lines shaped like a citation."""
    args = ["-c", "core.quotePath=false", "grep", "--no-color", "-I", "-n", "-z", "-E"]
    args += ["-e", _GREP_PREFILTER, "HEAD"]
    exit_code, stdout, _stderr = _git(repo_root, args)
    if exit_code == 1:
        return []
    if exit_code != 0:
        return None
    hits: list[tuple[str, int, str]] = []
    for record in stdout.split("\n"):
        parts = record.split("\0", 2)
        if len(parts) == 3 and parts[1].isdigit():
            hits.append((parts[0].removeprefix("HEAD:"), int(parts[1]), parts[2]))
    return hits


def _resolve_target(
    cited: str, changes: _ChangeSet, base_tracked: set[str], by_name: dict[str, list[str]]
) -> str | None:
    """Map a cited path to the changed base-side file it names, if any."""
    if "/" in cited or cited in base_tracked:
        return cited if cited in changes.changed else None
    candidates = by_name.get(cited, [])
    if len(candidates) == 1 and candidates[0] in changes.changed:
        return candidates[0]
    return None


def _judge(
    cite: _Cite, path: str, anchors: list[str], tracked: set[str], files: _HeadFileCache
) -> tuple[Finding | None, list[str] | None]:
    """Run the forward gate's existence, range, and anchor checks on one tree."""
    cited_lines, finding = _resolve_cited_range(
        cite.citing_file,
        cite.line_number,
        cite.label,
        path,
        cite.start,
        cite.end,
        tracked,
        files,
    )
    if finding is None and cited_lines is not None:
        finding = _anchor_finding(
            cite.citing_file,
            cite.line_number,
            cite.label,
            anchors,
            cited_lines,
            cite.start,
            cite.end,
        )
    return finding, cited_lines


def _first_anchor_line(anchors: list[str], lines: list[str], lo: int, hi: int) -> tuple[str, int]:
    """Return the first (anchor, 1-based line) in lines[lo..hi] an anchor matches."""
    for anchor in anchors:
        for number in range(lo, min(hi, len(lines)) + 1):
            if _anchor_matches(anchor, lines[number - 1]):
                return anchor, number
    return "", 0


def _nearest(positions: list[int], target: int) -> int | None:
    return min(positions, key=lambda p: (abs(p - target), p)) if positions else None


def _block_positions(block: list[str], lines: list[str]) -> list[int]:
    """Return every 1-based start where block sits verbatim in lines."""
    width = len(block)
    return [i + 1 for i in range(len(lines) - width + 1) if lines[i : i + width] == block]


def _unique_move(block: list[str], start: int, base: list[str], head: list[str]) -> int | None:
    """Return the block's single HEAD position, or None when the move is unproven.

    A cited block counts as moved only when it is distinctive (at least
    eight non-space characters), occurs exactly once at the merge base and
    exactly once at HEAD, and the HEAD copy is not at the cited start. A
    common line such as ``---`` or ``sys.executable,`` proves nothing.
    """
    if len("".join(text.strip() for text in block)) < 8:
        return None
    at_head = _block_positions(block, head)
    if len(_block_positions(block, base)) != 1 or len(at_head) != 1:
        return None
    return None if at_head[0] == start else at_head[0]


def _moved_start(cite: _Cite, anchors: list[str], base: list[str], head: list[str]) -> int | None:
    """Return the cited range's new start at HEAD, or None when unknown."""
    if anchors:
        anchor, at_base = _first_anchor_line(anchors, base, cite.start, cite.end)
        if not anchor:
            return None
        hits = [n for n, text in enumerate(head, 1) if _anchor_matches(anchor, text)]
        at_head = _nearest(hits, at_base)
        return None if at_head is None else cite.start + at_head - at_base
    return _unique_move(base[cite.start - 1 : cite.end], cite.start, base, head)


def _suggestion(cite: _Cite, head_path: str, start: int) -> str:
    end = f"-{start + cite.end - cite.start}" if cite.ranged else ""
    return f"; suggested citation {head_path}:{start}{end}"


def _content_moved(cite: _Cite, base: list[str], head: list[str]) -> bool:
    """Anchorless check: the cited base text now sits, uniquely, elsewhere."""
    block = base[cite.start - 1 : cite.end]
    return _unique_move(block, cite.start, base, head) is not None


def _new_finding(
    cite: _Cite, anchors: list[str], changes: _ChangeSet, trees: _Trees, base_lines: list[str]
) -> Finding | None:
    """Judge one base-valid citation at HEAD; return the finding or None."""
    finding, head_lines = _judge(cite, cite.target, anchors, trees.head_tracked, trees.head_files)
    head_path = changes.renamed_to.get(cite.target, cite.target)
    moved_lines = head_lines
    if head_path != cite.target and head_path in trees.head_tracked:
        moved_lines = trees.head_files.lines(head_path)
    if finding is None:
        if anchors or head_lines is None or not _content_moved(cite, base_lines, head_lines):
            return None
        reason = f"the text at lines {cite.start}-{cite.end} at the merge base moved at HEAD"
        finding = Finding(cite.citing_file, cite.line_number, cite.label, reason)
    reason = finding.reason
    if head_path != cite.target:
        reason += f"; renamed to {head_path}"
    if moved_lines is not None:
        start = _moved_start(cite, anchors, base_lines, moved_lines)
        if start is not None and start >= 1:
            reason += _suggestion(cite, head_path, start)
    return Finding(cite.citing_file, cite.line_number, cite.label, reason)


def _line_cites(
    citing_file: str,
    line_number: int,
    text: str,
    added: set[int],
    resolve: dict[str, str | None],
    head_tracked: set[str],
) -> list[tuple[_Cite, str]]:
    """Return (cite, same-line segment) for each reverse-pass citation on a line."""
    scannable = _URL.sub(" ", text)
    matches = list(_CITATION.finditer(scannable))
    cites: list[tuple[_Cite, str]] = []
    for index, match in enumerate(matches):
        cited = match.group("path").removeprefix("./")
        forward_reads = "/" in cited or cited in head_tracked
        if line_number in added and forward_reads:
            continue
        target = resolve.get(cited)
        if target is None:
            continue
        start = int(match.group("start"))
        end_group = match.group("end")
        cite = _Cite(
            citing_file,
            line_number,
            text,
            target,
            start,
            int(end_group) if end_group else start,
            end_group is not None,
        )
        cites.append((cite, _same_line_segment(scannable, matches, index)))
    return cites


@dataclass
class _Tally:
    examined: int = 0
    stale_at_base: int = 0


def _scan(
    repo_root: Path,
    base_ref: str,
    changes: _ChangeSet,
    trees: _Trees,
    tally: _Tally,
) -> list[Finding] | None:
    """Grep HEAD for inbound citations and judge each; may raise HeadReadError."""
    by_name: dict[str, list[str]] = {}
    for path in trees.base_tracked:
        by_name.setdefault(path.rsplit("/", 1)[-1], []).append(path)
    hits = _grep_head(repo_root)
    added_map = _added_lines_since_base(repo_root, base_ref)
    if hits is None or added_map is None:
        return None
    resolve_cache: dict[str, str | None] = {}
    findings: list[Finding] = []
    for citing_file, line_number, text in hits:
        if _is_exempt_citing_file(citing_file) or not _CITATION.search(text):
            continue
        for match in _CITATION.finditer(_URL.sub(" ", text)):
            cited = match.group("path").removeprefix("./")
            if cited not in resolve_cache:
                resolve_cache[cited] = _resolve_target(cited, changes, trees.base_tracked, by_name)
        added = {number for number, _text in added_map.get(citing_file, [])}
        cites = _line_cites(
            citing_file, line_number, text, added, resolve_cache, trees.head_tracked
        )
        if not cites:
            continue
        citing_lines = trees.head_files.lines(citing_file)
        if line_number in string_literal_lines(citing_file, citing_lines):
            continue
        markdown = citing_file.endswith(".md")
        if _has_ignore_marker(citing_lines, line_number, text, markdown):
            continue
        for cite, segment in cites:
            tally.examined += 1
            anchors = _citation_anchors(
                cite.label, text, segment, citing_lines, line_number, markdown
            )
            if line_number in added:
                # Written against HEAD, so HEAD alone is the reference.
                finding, _lines = _judge(
                    cite, cite.target, anchors, trees.head_tracked, trees.head_files
                )
                findings.extend([finding] if finding is not None else [])
                continue
            base_finding, base_lines = _judge(
                cite, cite.target, anchors, trees.base_tracked, trees.base_files
            )
            if base_finding is not None or base_lines is None:
                tally.stale_at_base += 1
                continue
            finding = _new_finding(cite, anchors, changes, trees, base_lines)
            if finding is not None:
                findings.append(finding)
    return findings


def find_reverse_stale_citations(repo_root: Path, base_ref: str) -> list[Finding] | None:
    """Return citations that held at the merge base and fail at HEAD, or None on git failure."""
    merge_base = _merge_base(repo_root, base_ref)
    if merge_base is None:
        print(f"{_PREFIX} git could not find a merge base for {base_ref}", file=sys.stderr)
        return None
    changes = _change_set(repo_root, base_ref)
    base_tracked = _head_tracked_paths(repo_root, merge_base)
    head_tracked = _head_tracked_paths(repo_root)
    if changes is None or base_tracked is None or head_tracked is None:
        return None
    trees = _Trees(
        base_tracked,
        head_tracked,
        _HeadFileCache(repo_root, merge_base),
        _HeadFileCache(repo_root),
    )
    tally = _Tally()
    findings: list[Finding] | None = []
    if changes.changed:
        try:
            findings = _scan(repo_root, base_ref, changes, trees, tally)
        except HeadReadError as error:
            print(f"{_PREFIX} git could not read {error}", file=sys.stderr)
            return None
    if findings is None:
        return None
    print(
        f"{_PREFIX} examined {tally.examined} inbound citation(s) to "
        f"{len(changes.changed)} changed file(s) vs {base_ref}; "
        f"{tally.stale_at_base} already stale at the merge base (not blocking)"
    )
    return findings


def validate_citation_reverse_pass(repo_root: Path) -> bool:
    """Gate entry point: print findings, return True when clean."""
    base_ref = _resolve_default_base_ref(repo_root)
    if base_ref is None:
        print("[SKIP] citation-reverse-pass: no base ref resolved; nothing to diff against")
        return True
    findings = find_reverse_stale_citations(repo_root, base_ref)
    if findings is None:
        print(f"{_PREFIX} git failed while reading repository state", file=sys.stderr)
        return False
    _report_findings(findings)
    return not findings


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        description="Verify path:line citations that point into files changed since the base."
    )
    parser.add_argument("--repo-root", default=".", help="Repository root path.")
    parser.add_argument(
        "--base",
        default=None,
        help="Base ref to diff against (default: resolved like pre_pr's other gates).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the reverse citation pass as a CLI."""
    args = build_parser().parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    if not (repo_root / ".git").exists():
        print(f"{_PREFIX} not a git repository: {repo_root}", file=sys.stderr)
        return 2
    base_ref = args.base or _resolve_default_base_ref(repo_root)
    if base_ref is None:
        print("[SKIP] citation-reverse-pass: no base ref resolved; nothing to diff against")
        return 0
    findings = find_reverse_stale_citations(repo_root, base_ref)
    if findings is None:
        print(f"{_PREFIX} git failed while reading repository state", file=sys.stderr)
        return 2
    _report_findings(findings)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())

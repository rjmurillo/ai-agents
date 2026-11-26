"""Deterministic ADR checks for adr_drift.py: numbering, links, supersession, cited paths.

Stdlib only. Every check reads the working tree and never writes.

Conventions: filenames are `ADR-NNN-slug.md` or `NNNN-slug.md` with one to six
digits, as `adr_corpus.parse_name` reads them, and every ADR folder found is
scanned, not only the first. Two folders may reuse a number, so a bare number or
`ADR-N` resolves in the citing record's own folder first.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from itertools import count, islice
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from adr_corpus import (
    AdrDir,
    AdrDoc,
    AdrFile,
    Finding,
    cited_paths,
    find_h1,
    is_non_record_name,
    make_finding,
    next_number,
    parse_name,
    path_exists,
)
from adr_text import (
    ADR_NUMBER,
    LINKS,
    NUMBERING,
    STATUS_HEADING,
    display_rel,
    h1_number,
    prose_lines,
    rel_join,
    status_word,
)

ACTIVE_STATUSES = frozenset({"", "accepted", "proposed", "draft", "approved"})
GAP_EVIDENCE_CAP = 50
KIND_PROFILE = {
    "adr-duplicate-number": (NUMBERING, "high"),
    "adr-title-number-mismatch": (NUMBERING, "medium"),
    "adr-unparseable-name": (NUMBERING, "low"),
    "adr-number-gap": (NUMBERING, "low"),
    "adr-broken-link": (LINKS, "medium"),
    "adr-supersedes-missing-target": (LINKS, "medium"),
    "adr-supersession-not-reciprocal": (LINKS, "medium"),
    "adr-cited-path-missing": (LINKS, "low"),
}

# Link text and target never span a `[`, and a title is at most 300 characters, so each
# match attempt stops near the next `[`. That keeps a long line of brackets linear.
INLINE_LINK = re.compile(r"\[[^\[\]\n]*\]\(\s*<?([^()\[\]\s<>]+)>?(?:\s+\"[^\"\n]{0,300}\")?\s*\)")
REF_LINK = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*<?(\S+?)>?(?:\s|$)")
CODE_SPAN = re.compile(r"`[^`\n]*`")
EDGE_LINE = re.compile(
    r"^\s*(?:[-*>]\s+)*\**(supersedes|superseded[ -]by|status)\**\s*[:|-]\s*(.*)$", re.IGNORECASE
)
LINKED_EDGE = re.compile(
    r"^\s*(?:[-*>]\s+)*\**(supersedes|superseded[ -]by)\**\s+(?=\[)(.*)$", re.IGNORECASE
)
SUPERSEDED_BY_TEXT = re.compile(r"supersed\w{0,20}\s+by\s+(.*)", re.IGNORECASE)
PATH_RUN = re.compile(r"[\w./-]+")
# Bounded like ADR_NUMBER, so a hostile frontmatter value cannot overflow int().
BARE_NUMBER = re.compile(r"^\d{1,6}$")
EDGE_KEYS = (
    ("supersedes", "supersedes"),
    ("superseded-by", "superseded_by"),
    ("superseded_by", "superseded_by"),
)
ADR_REF = re.compile(rf"\b{ADR_NUMBER}")


@dataclass(frozen=True)
class Edge:
    kind: str
    number: int
    line: int | None


def pad(number: int, folder: AdrDir) -> str:
    width = folder.files[-1].digits if folder.files else 3
    return f"{number:0{width}d}"


def _found(kind: str, evidence: dict[str, Any], suggested_fix: str, key: Sequence[str]) -> Finding:
    """A finding from a check that reads only files, so its confidence is deterministic."""
    group, severity = KIND_PROFILE[kind]
    return make_finding(kind, group, severity, "deterministic", evidence, suggested_fix, key)


def check_numbering(dirs: Sequence[AdrDir], docs: Sequence[AdrDoc]) -> list[Finding]:
    findings: list[Finding] = []
    # One counter for the whole repository, so no two suggested renames share a number.
    free = count(next_number(dirs))
    for folder in dirs:
        findings.extend(_duplicates(folder, free))
        findings.extend(_unparseable(folder))
        findings.extend(_gaps(folder))
    for doc in docs:
        mismatch = _title_mismatch(doc)
        if mismatch:
            findings.append(mismatch)
    return findings


def _duplicates(folder: AdrDir, free: Iterator[int]) -> list[Finding]:
    by_number: dict[int, list[AdrFile]] = defaultdict(list)
    for file in folder.files:
        by_number[file.number].append(file)
    findings = []
    for number, files in sorted(by_number.items()):
        if len(files) < 2:
            continue
        keep, *later = sorted(files, key=lambda f: f.path.name)
        renames = [(f.rel, pad(next(free), folder)) for f in later]
        steps = "; ".join(f"rename {rel} to number {new}" for rel, new in renames)
        fix = (
            f"Keep {keep.rel} as is; {steps} (next free in this repository)."
            " Update each renamed file's H1 and references."
        )
        evidence = {
            "path": later[0].rel,
            "paths": [f.rel for f in files],
            "number": number,
            "renames": [{"path": rel, "number": new} for rel, new in renames],
        }
        findings.append(
            _found(
                "adr-duplicate-number",
                evidence,
                fix,
                (folder.rel, str(number)),
            )
        )
    return findings


def _unparseable(folder: AdrDir) -> list[Finding]:
    findings = []
    for name in folder.other_md:
        if is_non_record_name(name) or not re.match(r"(?i)^(adr|\d)", name):
            continue
        if parse_name(name) is not None:
            continue
        rel = rel_join(folder.rel, name)
        fix = f"Rename {rel} to the folder convention, for example ADR-NNN-short-title.md."
        findings.append(
            _found(
                "adr-unparseable-name",
                {"path": rel},
                fix,
                (rel,),
            )
        )
    return findings


def _gaps(folder: AdrDir) -> list[Finding]:
    numbers = sorted({f.number for f in folder.files})
    if len(numbers) < 2:
        return []
    missing_count = numbers[-1] - numbers[0] + 1 - len(numbers)
    if missing_count == 0:
        return []
    present = set(numbers)
    # Walk only far enough to fill the evidence cap: the span can be large.
    shown = list(
        islice((n for n in range(numbers[0], numbers[-1]) if n not in present), GAP_EVIDENCE_CAP)
    )
    evidence = {
        "path": display_rel(folder.rel),
        "missing_count": missing_count,
        "missing": shown,
        "truncated": missing_count > GAP_EVIDENCE_CAP,
    }
    fix = "None needed. Report only: gaps are usually withdrawn or renumbered records."
    return [_found("adr-number-gap", evidence, fix, (folder.rel,))]


def _title_mismatch(doc: AdrDoc) -> Finding | None:
    h1 = find_h1(doc)
    if h1 is None:
        return None
    line, text = h1
    found = h1_number(text)
    if found is None or found == doc.file.number:
        return None
    evidence = {
        "path": doc.file.rel,
        "line": line,
        "h1_number": found,
        "filename_number": doc.file.number,
    }
    fix = (
        f"Make the H1 on line {line} of {doc.file.rel} name {doc.file.number}, "
        "the number in the filename, or rename the file to match the H1."
    )
    return _found(
        "adr-title-number-mismatch",
        evidence,
        fix,
        (doc.file.rel, str(found)),
    )


def _targets(line: str) -> list[str]:
    stripped = CODE_SPAN.sub("", line)
    found = INLINE_LINK.findall(stripped)
    ref = REF_LINK.match(stripped)
    if ref:
        found.append(ref.group(1))
    return found


def _adr_link_target(raw: str) -> tuple[str, int] | None:
    target = unquote(re.split(r"[#?]", raw, maxsplit=1)[0])
    if not target or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target) or target.startswith("/"):
        return None
    parsed = parse_name(os.path.basename(target))
    if parsed is None:
        return None
    return target, parsed[1]


def check_links(docs: Sequence[AdrDoc], dirs: Sequence[AdrDir]) -> list[Finding]:
    by_number: dict[int, list[AdrFile]] = defaultdict(list)
    for folder in dirs:
        for file in folder.files:
            by_number[file.number].append(file)
    findings: list[Finding] = []
    seen: set[tuple[str, int, str]] = set()
    adr_folders = {os.path.normpath(folder.path) for folder in dirs}
    for doc in docs:
        for number, text in prose_lines(doc.lines, doc.body_start):
            for raw in _targets(text):
                parsed = _adr_link_target(raw)
                if parsed is None:
                    continue
                target, adr_number = parsed
                resolved = Path(os.path.normpath(doc.file.path.parent / target))
                key = (doc.file.rel, number, target)
                if os.path.dirname(resolved) not in adr_folders:
                    continue
                if path_exists(resolved) or key in seen:
                    continue
                seen.add(key)
                findings.append(_broken_link(doc, number, target, adr_number, by_number))
    return findings


def _broken_link(
    doc: AdrDoc, line: int, target: str, number: int, by_number: dict[int, list[AdrFile]]
) -> Finding:
    existing = by_number.get(number)
    if existing:
        fix = f"Point the link at {existing[0].rel}, the file that holds ADR-{number}."
    else:
        fix = f"No file holds ADR-{number}. Remove the link or restore that record."
    evidence = {"path": doc.file.rel, "line": line, "target": target, "number": number}
    return _found(
        "adr-broken-link",
        evidence,
        fix,
        (doc.file.rel, str(line), target),
    )


def _md_paths(text: str) -> list[str]:
    """Each path-like run cut after its last `.md`: what `[\\w./-]+\\.md` finds, in linear time."""
    found = []
    for run in PATH_RUN.findall(text):
        end = run.rfind(".md")
        if end >= 1:
            found.append(run[: end + 3])
    return found


def _refs(text: str, include_paths: bool) -> list[int]:
    """ADR numbers named by `ADR-N`, by link targets, and (when asked) by bare .md paths."""
    numbers = {int(n) for n in ADR_REF.findall(text)}
    targets = _targets(text) + (_md_paths(text) if include_paths else [])
    for raw in targets:
        parsed = _adr_link_target(raw)
        if parsed is not None:
            numbers.add(parsed[1])
    return sorted(numbers)


def _frontmatter_numbers(item: str) -> list[int]:
    """Numbers in one frontmatter value: ADR refs, link or path targets, or a whole bare integer."""
    found = _refs(item, include_paths=True)
    if not found and BARE_NUMBER.match(item.strip()):
        return [int(item.strip())]
    return found


def _frontmatter_edges(doc: AdrDoc) -> list[Edge]:
    found: list[Edge] = []
    for key, kind in EDGE_KEYS:
        raw = doc.frontmatter.get(key)
        items = raw if isinstance(raw, list) else [raw]
        line = doc.frontmatter_lines.get(key)
        for item in items:
            if isinstance(item, str):
                found.extend(Edge(kind, n, line) for n in _frontmatter_numbers(item))
    status = doc.frontmatter.get("status")
    by = SUPERSEDED_BY_TEXT.search(status) if isinstance(status, str) else None
    if by:
        line = doc.frontmatter_lines.get("status")
        found.extend(Edge("superseded_by", n, line) for n in _refs(by.group(1), False))
    return found


def edges(doc: AdrDoc) -> list[Edge]:
    """Supersession edges from frontmatter and Status-style prose, one per (kind, number).

    Frontmatter wins: when it declares an edge kind, prose edges of that kind are dropped,
    because prose often tells a longer chain ("superseded by ADR-91, later by ADR-92").
    """
    declared = _frontmatter_edges(doc)
    declared_kinds = {edge.kind for edge in declared}
    found = list(declared)
    in_status = False
    for number, line in prose_lines(doc.lines, doc.body_start):
        if STATUS_HEADING.match(line):
            in_status = True
            continue
        if line.startswith("#"):
            in_status = False
        found.extend(
            e for e in _prose_edges(line, number, in_status) if e.kind not in declared_kinds
        )
    unique: dict[tuple[str, int], Edge] = {}
    for edge in found:
        unique.setdefault((edge.kind, edge.number), edge)
    return list(unique.values())


def _edges_of(kind: str, text: str, line: int) -> list[Edge]:
    return [Edge(kind, n, line) for n in _refs(text, include_paths=False)]


def _prose_edges(line: str, number: int, in_status: bool) -> list[Edge]:
    match = EDGE_LINE.match(line) or LINKED_EDGE.match(line)
    if match:
        word, value = match.group(1).lower(), match.group(2)
        if word == "supersedes":
            return _edges_of("supersedes", value, number)
        if word.startswith("superseded"):
            return _edges_of("superseded_by", value, number)
        line = value
    elif not in_status:
        return []
    by = SUPERSEDED_BY_TEXT.search(line)
    return _edges_of("superseded_by", by.group(1), number) if by else []


def resolve_number(doc: AdrDoc, number: int, docs: Sequence[AdrDoc]) -> AdrDoc | None:
    """The record `number` names from `doc`: its own folder first, else the only other match."""
    same = [
        d for d in docs if d.file.number == number and d.file.path.parent == doc.file.path.parent
    ]
    if same:
        return same[0]
    others = [d for d in docs if d.file.number == number]
    return others[0] if len(others) == 1 else None


def check_supersession(docs: Sequence[AdrDoc]) -> list[Finding]:
    graph = {doc.file.rel: edges(doc) for doc in docs}
    findings: list[Finding] = []
    seen: set[tuple[str, ...]] = set()
    for doc in docs:
        for edge in graph[doc.file.rel]:
            if edge.number == doc.file.number:
                continue
            target = resolve_number(doc, edge.number, docs)
            if target is None and any(d.file.number == edge.number for d in docs):
                continue  # several other folders hold this number: no single target to check
            finding = (
                _missing_target(doc, edge)
                if target is None
                else _reciprocity(doc, edge, target, graph[target.file.rel], docs)
            )
            if finding is not None and finding["id"] not in seen:
                seen.add(finding["id"])
                findings.append(finding)
    return findings


def _missing_target(doc: AdrDoc, edge: Edge) -> Finding:
    evidence = {
        "path": doc.file.rel,
        "line": edge.line,
        "edge": edge.kind,
        "number": edge.number,
    }
    fix = f"Fix the number: no file holds ADR-{edge.number}. Drop the {edge.kind} edge if it is stale."
    return _found(
        "adr-supersedes-missing-target",
        evidence,
        fix,
        (doc.file.rel, edge.kind, str(edge.number)),
    )


def _reciprocity(
    doc: AdrDoc, edge: Edge, target: AdrDoc, target_edges: list[Edge], docs: Sequence[AdrDoc]
) -> Finding | None:
    """A missing back-edge. A back-edge counts only when it resolves, from the target, to `doc`.

    When `doc`'s number names another record from the target's folder, no edge in the
    target can name `doc` by number, so no fix exists and the edge is not checked.
    """
    if resolve_number(target, doc.file.number, docs) is not doc:
        return None
    wanted = "superseded_by" if edge.kind == "supersedes" else "supersedes"
    if any(e.kind == wanted and e.number == doc.file.number for e in target_edges):
        return None
    label = "superseded-by" if wanted == "superseded_by" else "supersedes"
    evidence = {
        "path": target.file.rel,
        "from": doc.file.rel,
        "edge": edge.kind,
        "missing_edge": wanted,
    }
    fix = (
        f"Add `{label}: ADR-{doc.file.number}` to {target.file.rel} "
        f"(or a matching status line), because {doc.file.rel} declares the {edge.kind} edge."
    )
    return _found(
        "adr-supersession-not-reciprocal",
        evidence,
        fix,
        (target.file.rel, doc.file.rel, wanted),
    )


def check_cited_paths(repo: Path, docs: Sequence[AdrDoc]) -> list[Finding]:
    findings: list[Finding] = []
    for doc in docs:
        if status_word(doc.status) not in ACTIVE_STATUSES:
            continue
        for line, path in cited_paths(doc):
            first = path.split("/", 1)[0]
            if not path_exists(repo / first) or path_exists(repo / path):
                continue
            if path_exists(doc.file.path.parent / path):
                continue
            evidence = {"path": doc.file.rel, "line": line, "cited": path}
            fix = (
                f"Update {doc.file.rel} line {line}: `{path}` no longer exists. "
                "Name the file's current path, or drop the citation. Supersede the record only if"
                " the decision itself changed."
            )
            findings.append(
                _found(
                    "adr-cited-path-missing",
                    evidence,
                    fix,
                    (doc.file.rel, path),
                )
            )
    return findings

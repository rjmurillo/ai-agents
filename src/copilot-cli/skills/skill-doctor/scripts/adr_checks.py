"""Deterministic ADR checks for adr_drift.py: numbering, links, supersession, cited paths.

Stdlib only. Every check reads the working tree and never writes.

Mirrors `scripts/validation/check_adr_uniqueness.py` for duplicate numbers
(same rule, same "next free" arithmetic). It is looser on filenames (any digit
run, two conventions) and scans every ADR folder, not one.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

from adr_corpus import (
    AdrDir,
    AdrDoc,
    AdrFile,
    Finding,
    find_h1,
    h1_number,
    is_template_name,
    make_finding,
    parse_name,
    prose_lines,
    status_word,
)

NUMBERING = "Numbering"
LINKS = "Links"
ACTIVE_STATUSES = frozenset({"", "accepted", "proposed", "draft", "approved"})
GAP_EVIDENCE_CAP = 50

INLINE_LINK = re.compile(r"\[[^\]\n]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
REF_LINK = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*<?(\S+?)>?(?:\s|$)")
CODE_SPAN = re.compile(r"`[^`\n]*`")
BACKTICK = re.compile(r"`([^`\n]+)`")
EDGE_LINE = re.compile(
    r"^\s*(?:[-*>]\s+)*\**(supersedes|superseded[ -]by|status)\**\s*[:|-]\s*(.*)$", re.IGNORECASE
)
SUPERSEDED_BY_TEXT = re.compile(r"supersed\w*\s+by\s+(.*)", re.IGNORECASE)
ADR_REF = re.compile(r"\bADR-0*(\d+)\b")
PATHLIKE = re.compile(r"^[A-Za-z0-9_.@+-][A-Za-z0-9_.@+/-]*$")
PLACEHOLDER = re.compile(r"YYYY|MM-DD|NNN|XXX|path/to", re.IGNORECASE)
FILE_EXTENSION = re.compile(r"\.[A-Za-z0-9]{1,8}$")


@dataclass(frozen=True)
class Edge:
    kind: str
    number: int
    line: int | None


def pad(number: int, folder: AdrDir) -> str:
    width = folder.files[-1].digits if folder.files else 3
    return f"{number:0{width}d}"


def next_number(dirs: Sequence[AdrDir]) -> int:
    numbers = [f.number for folder in dirs for f in folder.files]
    return (max(numbers) + 1) if numbers else 1


def check_numbering(dirs: Sequence[AdrDir], docs: Sequence[AdrDoc]) -> list[Finding]:
    findings: list[Finding] = []
    upcoming = next_number(dirs)
    for folder in dirs:
        findings.extend(_duplicates(folder, upcoming))
        findings.extend(_unparseable(folder))
        findings.extend(_gaps(folder))
    for doc in docs:
        mismatch = _title_mismatch(doc)
        if mismatch:
            findings.append(mismatch)
    return findings


def _duplicates(folder: AdrDir, upcoming: int) -> list[Finding]:
    by_number: dict[int, list[AdrFile]] = defaultdict(list)
    for file in folder.files:
        by_number[file.number].append(file)
    findings = []
    for number, files in sorted(by_number.items()):
        if len(files) < 2:
            continue
        later = sorted(files, key=lambda f: f.path.name)[-1]
        fix = (
            f"Rename {later.rel} to number {pad(upcoming, folder)} (next free in this repository)"
            " and update its H1 and references. Keep the earlier file as is."
        )
        evidence = {"path": later.rel, "paths": [f.rel for f in files], "number": number}
        findings.append(
            make_finding(
                "adr-duplicate-number",
                NUMBERING,
                "high",
                "deterministic",
                evidence,
                fix,
                (folder.rel, str(number)),
            )
        )
    return findings


def _unparseable(folder: AdrDir) -> list[Finding]:
    findings = []
    for name in folder.other_md:
        if is_template_name(name) or not re.match(r"(?i)^(adr|\d)", name):
            continue
        if parse_name(name) is not None:
            continue
        rel = f"{folder.rel}/{name}"
        fix = f"Rename {rel} to the folder convention, for example ADR-NNN-short-title.md."
        findings.append(
            make_finding(
                "adr-unparseable-name",
                NUMBERING,
                "low",
                "deterministic",
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
    present = set(numbers)
    missing = [n for n in range(numbers[0], numbers[-1] + 1) if n not in present]
    if not missing:
        return []
    evidence = {
        "path": folder.rel,
        "missing_count": len(missing),
        "missing": missing[:GAP_EVIDENCE_CAP],
        "truncated": len(missing) > GAP_EVIDENCE_CAP,
    }
    fix = "None needed. Report only: gaps are usually withdrawn or renumbered records."
    return [
        make_finding(
            "adr-number-gap", NUMBERING, "low", "deterministic", evidence, fix, (folder.rel,)
        )
    ]


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
    return make_finding(
        "adr-title-number-mismatch",
        NUMBERING,
        "medium",
        "deterministic",
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
                if resolved.exists() or key in seen:
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
    return make_finding(
        "adr-broken-link",
        LINKS,
        "medium",
        "deterministic",
        evidence,
        fix,
        (doc.file.rel, str(line), target),
    )


def _numbers(value: str) -> list[int]:
    return [int(n) for n in re.findall(r"\d+", value)]


def edges(doc: AdrDoc) -> list[Edge]:
    """Supersession edges from frontmatter and from Status-style prose lines."""
    found: list[Edge] = []
    for key, kind in (
        ("supersedes", "supersedes"),
        ("superseded-by", "superseded_by"),
        ("superseded_by", "superseded_by"),
    ):
        raw = doc.frontmatter.get(key)
        text = " ".join(raw) if isinstance(raw, list) else str(raw or "")
        found.extend(Edge(kind, n, None) for n in _numbers(text))
    in_status = False
    for number, line in prose_lines(doc.lines, doc.body_start):
        if re.match(r"^#{2,3}\s+status\b", line, re.IGNORECASE):
            in_status = True
            continue
        if line.startswith("#"):
            in_status = False
        found.extend(_prose_edges(line, number, in_status))
    return found


def _prose_edges(line: str, number: int, in_status: bool) -> list[Edge]:
    match = EDGE_LINE.match(line)
    if match:
        word, value = match.group(1).lower(), match.group(2)
        if word == "supersedes":
            return [Edge("supersedes", int(n), number) for n in ADR_REF.findall(value)]
        if word.startswith("superseded"):
            return [Edge("superseded_by", int(n), number) for n in ADR_REF.findall(value)]
        line = value
    elif not in_status:
        return []
    by = SUPERSEDED_BY_TEXT.search(line)
    return (
        [Edge("superseded_by", int(n), number) for n in ADR_REF.findall(by.group(1))] if by else []
    )


def check_supersession(docs: Sequence[AdrDoc]) -> list[Finding]:
    by_number: dict[int, AdrDoc] = {}
    for doc in docs:
        by_number.setdefault(doc.file.number, doc)
    graph = {doc.file.rel: edges(doc) for doc in docs}
    findings: list[Finding] = []
    seen: set[tuple[str, ...]] = set()
    for doc in docs:
        for edge in graph[doc.file.rel]:
            if edge.number == doc.file.number:
                continue
            target = by_number.get(edge.number)
            if target is None:
                findings.append(_missing_target(doc, edge))
                continue
            finding = _reciprocity(doc, edge, target, graph[target.file.rel])
            marker = (finding or {}).get("id", "")
            if finding is not None and marker not in seen:
                seen.add(marker)
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
    return make_finding(
        "adr-supersedes-missing-target",
        LINKS,
        "medium",
        "deterministic",
        evidence,
        fix,
        (doc.file.rel, edge.kind, str(edge.number)),
    )


def _reciprocity(
    doc: AdrDoc, edge: Edge, target: AdrDoc, target_edges: list[Edge]
) -> Finding | None:
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
    return make_finding(
        "adr-supersession-not-reciprocal",
        LINKS,
        "medium",
        "deterministic",
        evidence,
        fix,
        (target.file.rel, doc.file.rel, wanted),
    )


def _clean_path(token: str) -> str | None:
    value = re.sub(r":\d+(?:-\d+)?$", "", token.strip())
    if not PATHLIKE.match(value) or "/" not in value or PLACEHOLDER.search(value):
        return None
    if value.startswith(("/", "~", "./", "..")) or ".." in value or "//" in value:
        return None
    last = value.rstrip("/").rsplit("/", 1)[-1]
    if not (value.endswith("/") or FILE_EXTENSION.search(last)):
        return None
    return value


def cited_paths(doc: AdrDoc) -> list[tuple[int, str]]:
    """Backticked repo-relative paths in prose, as (line, path), first sighting only."""
    seen: set[str] = set()
    found: list[tuple[int, str]] = []
    for number, line in prose_lines(doc.lines, doc.body_start):
        for token in BACKTICK.findall(line):
            path = _clean_path(token)
            if path is not None and path not in seen:
                seen.add(path)
                found.append((number, path))
    return found


def check_cited_paths(repo: Path, docs: Sequence[AdrDoc]) -> list[Finding]:
    findings: list[Finding] = []
    for doc in docs:
        if status_word(doc.status) not in ACTIVE_STATUSES:
            continue
        for line, path in cited_paths(doc):
            first = path.split("/", 1)[0]
            if not (repo / first).exists() or (repo / path).exists():
                continue
            if (doc.file.path.parent / path).exists():
                continue
            evidence = {"path": doc.file.rel, "line": line, "cited": path}
            fix = (
                f"Update {doc.file.rel} line {line}: `{path}` no longer exists. "
                "Name its replacement or mark the record superseded."
            )
            findings.append(
                make_finding(
                    "adr-cited-path-missing",
                    LINKS,
                    "low",
                    "deterministic",
                    evidence,
                    fix,
                    (doc.file.rel, path),
                )
            )
    return findings

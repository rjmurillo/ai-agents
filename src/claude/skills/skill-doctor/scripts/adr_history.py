"""Git-history ADR checks for adr_drift.py: superseded-by-commit and contradiction candidates.

Stdlib only, local git only, no network.

Every finding here is heuristic. It names a candidate and cites the commit.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from adr_checks import cited_paths
from adr_corpus import AdrDoc, Finding, make_finding, run_git, status_word

HISTORY = "History"
MAX_CITED_EVIDENCE = 10
SUPERSEDE_VERB = r"(?:supersed\w*|replac\w*|revert\w*|deprecat\w*|drop\w*)"
VERB_THEN_ADR = re.compile(rf"{SUPERSEDE_VERB}[^.\n]{{0,60}}?\bADR-0*(\d+)\b", re.IGNORECASE)
ADR_THEN_VERB = re.compile(rf"\bADR-0*(\d+)\b[^.\n]{{0,60}}?{SUPERSEDE_VERB}", re.IGNORECASE)
RECORD_SEP, FIELD_SEP, HEADER_END = "\x1e", "\x1f", "\x1d"


@dataclass(frozen=True)
class Commit:
    sha: str
    date: str
    subject: str
    body: str
    paths: tuple[tuple[str, str], ...]

    @property
    def text(self) -> str:
        return f"{self.subject}\n{self.body}"


def read_commits(repo: Path, max_commits: int, since: str | None) -> tuple[list[Commit], bool]:
    """Walk HEAD. Returns (commits, truncated). Asks for one extra to detect truncation."""
    args = [
        "log",
        "--no-show-signature",
        "-M",
        "--name-status",
        "--no-color",
        f"--max-count={max_commits + 1}",
        f"--format={RECORD_SEP}%H{FIELD_SEP}%aI{FIELD_SEP}%s{FIELD_SEP}%b{HEADER_END}",
    ]
    if since:
        args.append(f"--since={since}")
    commits = [_parse_commit(chunk) for chunk in run_git(repo, args).split(RECORD_SEP)[1:]]
    return commits[:max_commits], len(commits) > max_commits


def _parse_commit(chunk: str) -> Commit:
    header, _, rest = chunk.partition(HEADER_END)
    sha, date, subject, body = (header.split(FIELD_SEP) + ["", "", "", ""])[:4]
    paths: list[tuple[str, str]] = []
    for line in rest.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        letter = parts[0][:1]
        if letter in "RC" and len(parts) >= 3:
            paths.append(("D" if letter == "R" else "M", parts[1]))
            paths.append(("A", parts[2]))
        else:
            paths.append((letter, parts[1]))
    return Commit(sha.strip(), date.strip(), subject.strip(), body.strip(), tuple(paths))


def _commit_evidence(commit: Commit) -> dict[str, Any]:
    return {"sha": commit.sha, "date": commit.date, "subject": commit.subject}


def superseded_by_commits(commits: Sequence[Commit], docs: Sequence[AdrDoc]) -> list[Finding]:
    by_number = {d.file.number: d for d in docs if status_word(d.status) == "accepted"}
    findings: list[Finding] = []
    for commit in commits:
        numbers = {int(n) for rx in (VERB_THEN_ADR, ADR_THEN_VERB) for n in rx.findall(commit.text)}
        for number in sorted(numbers & by_number.keys()):
            doc = by_number[number]
            if any(path == doc.file.rel for _, path in commit.paths):
                continue
            evidence = {**_commit_evidence(commit), "adr": doc.file.rel, "number": number}
            fix = (
                f"Candidate: commit {commit.sha[:10]} may supersede ADR-{number}, which is still "
                "accepted. Update its status, or write the successor ADR."
            )
            findings.append(
                make_finding(
                    "adr-superseded-by-commit",
                    HISTORY,
                    "medium",
                    "heuristic",
                    evidence,
                    fix,
                    (commit.sha, doc.file.rel),
                )
            )
    return findings


def _index_citations(
    docs: Sequence[AdrDoc],
) -> tuple[dict[str, list[tuple[AdrDoc, int]]], list[tuple[str, AdrDoc, int]]]:
    """Cited paths of accepted ADRs: exact files by path, and cited folders as prefixes."""
    exact: dict[str, list[tuple[AdrDoc, int]]] = {}
    folders: list[tuple[str, AdrDoc, int]] = []
    for doc in docs:
        if status_word(doc.status) != "accepted":
            continue
        for line, path in cited_paths(doc):
            if path.endswith("/"):
                folders.append((path, doc, line))
            else:
                exact.setdefault(path, []).append((doc, line))
    return exact, folders


def contradiction_candidates(commits: Sequence[Commit], docs: Sequence[AdrDoc]) -> list[Finding]:
    """One finding per (commit, accepted ADR), listing the cited paths the commit removed."""
    exact, folders = _index_citations(docs)
    findings: list[Finding] = []
    for commit in commits:
        hits: dict[str, tuple[AdrDoc, list[tuple[int, str]]]] = {}
        for letter, path in commit.paths:
            if letter != "D":
                continue
            matches = list(exact.get(path, []))
            matches += [(d, ln) for prefix, d, ln in folders if path.startswith(prefix)]
            for doc, line in matches:
                hits.setdefault(doc.file.rel, (doc, []))[1].append((line, path))
        findings += [
            _contradiction(commit, doc, cited)
            for doc, cited in hits.values()
            if not (_before_adr(commit, doc) or _touches_doc(commit, doc))
        ]
    return findings


def _before_adr(commit: Commit, doc: AdrDoc) -> bool:
    adr_date = str(doc.frontmatter.get("date") or "")[:10]
    return bool(re.match(r"\d{4}-\d{2}-\d{2}$", adr_date)) and commit.date[:10] < adr_date


def _touches_doc(commit: Commit, doc: AdrDoc) -> bool:
    return any(path == doc.file.rel for _, path in commit.paths)


def _contradiction(commit: Commit, doc: AdrDoc, cited: list[tuple[int, str]]) -> Finding:
    paths = sorted({path for _, path in cited})
    evidence = {
        **_commit_evidence(commit),
        "adr": doc.file.rel,
        "line": min(line for line, _ in cited),
        "cited": paths[:MAX_CITED_EVIDENCE],
        "cited_count": len(paths),
    }
    fix = (
        f"Candidate: commit {commit.sha[:10]} removed or renamed {len(paths)} path(s) that accepted "
        f"{doc.file.rel} cites, for example `{paths[0]}`. Review the ADR against the commit."
    )
    return make_finding(
        "adr-contradiction-candidate",
        HISTORY,
        "medium",
        "heuristic",
        evidence,
        fix,
        (commit.sha, doc.file.rel),
    )


def history_findings(commits: Sequence[Commit], docs: Sequence[AdrDoc]) -> list[Finding]:
    """All History findings for the commits read."""
    return superseded_by_commits(commits, docs) + contradiction_candidates(commits, docs)


__all__ = ["Commit", "history_findings", "read_commits"]

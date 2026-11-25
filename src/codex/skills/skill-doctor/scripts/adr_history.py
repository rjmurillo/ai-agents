"""Git-history ADR checks for adr_drift.py: superseded-by-commit and contradiction candidates.

Stdlib only, local git only, no network.

Every finding here is heuristic and low severity. It names a candidate and cites
the commit. Hand checks on one repository found no real reversal among them.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from adr_corpus import AdrDoc, Finding, cited_paths, make_finding
from adr_git import GitError, run_git
from adr_text import ADR_NUMBER, HISTORY, status_word

MAX_CITED_EVIDENCE = 10
# Word suffixes are bounded so a long run of verbs cannot make each match attempt rescan it.
SUPERSEDE_VERB = r"(?:supersed|replac|revert|deprecat|drop)\w{0,20}"
VERB_THEN_ADR = re.compile(rf"{SUPERSEDE_VERB}([^.\n]{{0,60}}?)\b{ADR_NUMBER}", re.IGNORECASE)
# A "by" or "in favor of" between the verb and ADR-N, as in "superseded by the new
# ADR-N" or "deprecated in favor of ADR-N", names ADR-N as the successor.
BY_SUCCESSOR = re.compile(r"\b(?:by|in\s+favou?r\s+of)\b", re.IGNORECASE)
# In "ADR-M supersedes ADR-N" or "ADR-M replaced ADR-N", ADR-M is the successor: another
# ADR follows the verb with no "by" or "in favor of" between. The passive "ADR-N is
# superseded by ADR-M" keeps ADR-N.
THEN_ADR = re.compile(rf"([^.\n]{{0,60}}?)\b{ADR_NUMBER}", re.IGNORECASE)
ADR_THEN_VERB = re.compile(rf"\b{ADR_NUMBER}[^.\n]{{0,60}}?{SUPERSEDE_VERB}", re.IGNORECASE)
SHA_TOKEN = re.compile(r"^[0-9a-f]{40,64}$")
STATUS_TOKEN = re.compile(r"^[A-Z]\d*$")
LOG_ARGS = (
    "log",
    "-z",
    "--no-show-signature",
    "--no-ext-diff",
    "--no-textconv",
    "--no-color",
    "--diff-merges=first-parent",
    # No rename detection: a rename lists as a delete plus an add, which is how the
    # checks read it anyway, and git never reads a blob (a partial clone lacks them).
    "--no-renames",
    "--name-status",
)
LOG_FORMAT = "--format=%H%x00%aI%x00%s%x00%b"


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


def head_commit(repo: Path) -> str | None:
    """The commit HEAD names, or None for an unborn branch. Any other failure raises GitError."""
    try:
        return run_git(repo, ["rev-parse", "--verify", "--quiet", "HEAD^{commit}"]).strip()
    except GitError as exc:
        if exc.returncode != 1:
            raise
    try:
        ref = run_git(repo, ["symbolic-ref", "-q", "HEAD"]).strip()
    except GitError as exc:
        raise GitError("HEAD is detached and names no commit", exc.returncode) from exc
    try:
        run_git(repo, ["show-ref", "--verify", "--quiet", ref])
    except GitError as exc:
        if exc.returncode == 1:
            return None
        raise
    raise GitError(f"{ref} exists but is not a commit")


def read_commits(repo: Path, max_commits: int, since: str | None) -> tuple[list[Commit], bool]:
    """Walk HEAD. Returns (commits, truncated). Asks for one extra to detect truncation."""
    args = [*LOG_ARGS, f"--max-count={max_commits + 1}", LOG_FORMAT]
    if since:
        args.append(f"--since={since}")
    commits = _parse_log(run_git(repo, args))
    return commits[:max_commits], len(commits) > max_commits


def _parse_log(output: str) -> list[Commit]:
    """Parse `git log -z` output. NUL cannot occur in a message, so a body cannot forge a record."""
    tokens = output.split("\0")
    commits: list[Commit] = []
    index = 0
    while index < len(tokens):
        if index == len(tokens) - 1 and not tokens[index].strip():
            break
        sha = tokens[index].strip()
        if not SHA_TOKEN.match(sha) or index + 4 > len(tokens):
            raise GitError(f"unexpected git log output at token {index}")
        date, subject, body = tokens[index + 1 : index + 4]
        paths, index = _parse_paths(tokens, index + 4)
        commits.append(Commit(sha, date.strip(), subject.strip(), body.strip(), paths))
    return commits


def _parse_paths(tokens: list[str], index: int) -> tuple[tuple[tuple[str, str], ...], int]:
    paths: list[tuple[str, str]] = []
    while index < len(tokens):
        status = tokens[index].strip()
        if not STATUS_TOKEN.match(status):
            break
        width = 2 if status[0] in "RC" else 1
        names = tokens[index + 1 : index + 1 + width]
        if len(names) < width:
            raise GitError(f"unexpected git log output at token {index}")
        if width == 2:
            paths.append(("D" if status[0] == "R" else "M", names[0]))
            paths.append(("A", names[1]))
        else:
            paths.append((status[0], names[0]))
        index += 1 + width
    return tuple(paths), index


def _commit_evidence(commit: Commit) -> dict[str, Any]:
    return {"sha": commit.sha, "date": commit.date, "subject": commit.subject}


def _names_successor(match: re.Match[str], text: str) -> bool:
    """True for ADR-M in "ADR-M supersedes ADR-N": another ADR follows the verb, and no
    "by" or "in favor of" stands anywhere between them."""
    after = THEN_ADR.match(text, match.end())
    return after is not None and not BY_SUCCESSOR.search(after.group(1))


def superseded_numbers(text: str) -> set[int]:
    """ADR numbers a commit text says were superseded, replaced, reverted, or dropped."""
    numbers = {
        int(m.group(1)) for m in ADR_THEN_VERB.finditer(text) if not _names_successor(m, text)
    }
    for match in VERB_THEN_ADR.finditer(text):
        if not BY_SUCCESSOR.search(match.group(1)):
            numbers.add(int(match.group(2)))
    return numbers


def superseded_by_commits(commits: Sequence[Commit], docs: Sequence[AdrDoc]) -> list[Finding]:
    """One candidate per (commit, accepted ADR). Every folder that holds the number is a candidate."""
    by_number: dict[int, list[AdrDoc]] = {}
    for doc in docs:
        if status_word(doc.status) == "accepted":
            by_number.setdefault(doc.file.number, []).append(doc)
    findings: list[Finding] = []
    for commit in commits:
        numbers = superseded_numbers(commit.text)
        for number, doc in [
            (n, d) for n in sorted(numbers & by_number.keys()) for d in by_number[n]
        ]:
            if _touches_doc(commit, doc):
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
                    "low",
                    "heuristic",
                    evidence,
                    fix,
                    (commit.sha, doc.file.rel),
                )
            )
    return findings


def _index_citations(docs: Sequence[AdrDoc]) -> dict[str, list[tuple[AdrDoc, int]]]:
    """Cited files of accepted ADRs, by path.

    A cited folder is not indexed: deleting one file under a cited folder rarely
    reverses a decision, and folder matches were 218 of 225 candidates on one repo.
    """
    exact: dict[str, list[tuple[AdrDoc, int]]] = {}
    for doc in docs:
        if status_word(doc.status) != "accepted":
            continue
        for line, path in cited_paths(doc):
            if not path.endswith("/"):
                exact.setdefault(path, []).append((doc, line))
    return exact


def contradiction_candidates(commits: Sequence[Commit], docs: Sequence[AdrDoc]) -> list[Finding]:
    """One finding per (commit, accepted ADR), listing the cited paths the commit removed."""
    exact = _index_citations(docs)
    findings: list[Finding] = []
    for commit in commits:
        hits: dict[str, tuple[AdrDoc, list[tuple[int, str]]]] = {}
        for letter, path in commit.paths:
            if letter != "D":
                continue
            for doc, line in exact.get(path, []):
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
        f"{doc.file.rel} cites, for example `{paths[0]}`. Update the cited paths; if the decision "
        "itself changed, supersede the record."
    )
    return make_finding(
        "adr-contradiction-candidate",
        HISTORY,
        "low",
        "heuristic",
        evidence,
        fix,
        (commit.sha, doc.file.rel),
    )


def history_findings(commits: Sequence[Commit], docs: Sequence[AdrDoc]) -> list[Finding]:
    """All History findings for the commits read."""
    return superseded_by_commits(commits, docs) + contradiction_candidates(commits, docs)


__all__ = ["Commit", "head_commit", "history_findings", "read_commits"]

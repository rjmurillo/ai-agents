"""Git-history ADR checks for adr_drift.py: undocumented decisions and stale ADRs.

Stdlib only, local git only, no network. A PR export arrives as a file the
caller wrote (`--prs-json`), in the list shape `bootstrap_mine.py --prs-json`
reads: a JSON list of objects that each carry an integer `number`. This module
also reads `title`, `body`, and `url` (or `html_url`) from each item.

Every finding here is heuristic. It names a candidate and cites the commit.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from adr_checks import cited_paths
from adr_corpus import AdrDir, AdrDoc, Finding, GitError, make_finding, run_git, status_word

HISTORY = "History"
BODY_CAP = 1500
MAX_DEPENDENCY_SIGNALS = 10
MAX_CITED_EVIDENCE = 10
MANIFEST_PATHSPECS = (
    ":(glob)**/pyproject.toml",
    ":(glob)**/package.json",
    ":(glob)**/go.mod",
    ":(glob)**/Cargo.toml",
    ":(glob)**/*.csproj",
)
VERB_SIGNALS = (
    ("switch to", r"\bswitch(?:es|ed|ing)?\s+to\b"),
    ("replace X with Y", r"\breplac(?:e|es|ed|ing)\s+[^\n]{1,80}?\s+with\b"),
    ("migrate", r"\bmigrat(?:e|es|ed|ing|ion)\b"),
    ("adopt", r"\badopt(?:s|ed|ing|ion)?\b"),
    ("drop support", r"\bdrop(?:s|ped|ping)?\s+support\b"),
    ("deprecate", r"\bdeprecat(?:e|es|ed|ing)\b"),
    ("instead of", r"\binstead\s+of\b"),
    ("decide", r"\bdecid(?:e|es|ed|ing)\b"),
    ("standardize on", r"\bstandardi[sz](?:e|es|ed|ing)\s+on\b"),
)
VERB_REGEXES = tuple((label, re.compile(rx, re.IGNORECASE)) for label, rx in VERB_SIGNALS)
BREAKING_SUBJECT = re.compile(r"^\w+(?:\([^)]*\))?!:")
BREAKING_FOOTER = re.compile(r"^BREAKING[ -]CHANGE\b", re.MULTILINE)
SQUASH_PR = re.compile(r"\(#(\d+)\)\s*$")
MERGE_PR = re.compile(r"^Merge pull request #(\d+)\b")
SUPERSEDE_VERB = r"(?:supersed\w*|replac\w*|revert\w*|deprecat\w*|drop\w*)"
VERB_THEN_ADR = re.compile(rf"{SUPERSEDE_VERB}[^.\n]{{0,60}}?\bADR-0*(\d+)\b", re.IGNORECASE)
ADR_THEN_VERB = re.compile(rf"\bADR-0*(\d+)\b[^.\n]{{0,60}}?{SUPERSEDE_VERB}", re.IGNORECASE)
HEX_TOKEN = re.compile(r"\b[0-9a-f]{7,40}\b")
PR_NUMBER_TOKEN = re.compile(r"(?<![\w&])#(\d+)\b|/pull/(\d+)\b")
NON_DEPENDENCY_KEYS = frozenset(
    {
        "name",
        "version",
        "description",
        "main",
        "license",
        "type",
        "module",
        "types",
        "author",
        "homepage",
        "edition",
        "requires-python",
        "python",
        "build-backend",
        "readme",
        "authors",
        "repository",
        "private",
        "packagemanager",
    }
)
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


def read_prs(path: str) -> dict[int, dict[str, Any]]:
    """Read a `--prs-json` export. Raises ValueError with a message on bad input."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read --prs-json {path}: {exc}") from exc
    if not isinstance(data, list):
        raise ValueError(f"--prs-json {path} must hold a JSON list")
    prs: dict[int, dict[str, Any]] = {}
    for index, item in enumerate(data):
        number = item.get("number") if isinstance(item, dict) else None
        if not isinstance(number, int) or isinstance(number, bool) or number < 0:
            raise ValueError(f"--prs-json {path} item {index} needs an integer `number`")
        prs[number] = item
    return prs


def pr_number_of(commit: Commit) -> int | None:
    match = SQUASH_PR.search(commit.subject) or MERGE_PR.match(commit.subject)
    return int(match.group(1)) if match else None


def _dependency_name(manifest: str, text: str) -> str | None:
    patterns = {
        "package.json": r'^"([@A-Za-z0-9._/-]+)"\s*:\s*"[\^~><*=0-9a-z:.@/-]+",?$',
        "pyproject.toml": (
            r'^"([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?\s*(?:[<>=!~;@][^"]*)?",?$'
            r'|^([A-Za-z0-9][A-Za-z0-9._-]*)\s*=\s*(?:"[\^~><=*0-9]|\{)'
        ),
        "go.mod": r"^(?:require\s+)?([A-Za-z0-9._~-]+\.[A-Za-z0-9._~-]+/\S+)\s+v[\w.+-]+",
        "Cargo.toml": r'^([A-Za-z0-9_-]+)\s*=\s*(?:"[\^~><=*0-9]|\{)',
        "csproj": r'^<PackageReference\s+Include="([^"]+)"',
    }
    match = re.match(patterns[manifest], text.strip())
    if not match:
        return None
    name = next((g for g in match.groups() if g), None)
    if name is None or name.lower() in NON_DEPENDENCY_KEYS:
        return None
    return name


def _manifest_kind(path: str) -> str | None:
    base = path.rsplit("/", 1)[-1]
    if base in {"package.json", "pyproject.toml", "go.mod", "Cargo.toml"}:
        return base
    return "csproj" if base.endswith(".csproj") else None


def dependency_changes(repo: Path, shas: Sequence[str]) -> dict[str, tuple[set[str], set[str]]]:
    """Per commit, (added, removed) dependency names net of version bumps."""
    if not shas:
        return {}
    args = [
        "log",
        "--no-walk=unsorted",
        "--no-show-signature",
        "-p",
        "-U0",
        "-M",
        "--no-color",
        f"--format={RECORD_SEP}%H",
        *shas,
        "--",
        *MANIFEST_PATHSPECS,
    ]
    result: dict[str, tuple[set[str], set[str]]] = {}
    for chunk in run_git(repo, args).split(RECORD_SEP)[1:]:
        sha, _, diff = chunk.partition("\n")
        added, removed = _scan_diff(diff)
        net = (added - removed, removed - added)
        if net[0] or net[1]:
            result[sha.strip()] = net
    return result


def _scan_diff(diff: str) -> tuple[set[str], set[str]]:
    added: set[str] = set()
    removed: set[str] = set()
    manifest: str | None = None
    in_hunk = False
    for line in diff.splitlines():
        if line.startswith("diff --git"):
            manifest, in_hunk = _manifest_kind(line.rsplit(" b/", 1)[-1]), False
        elif line.startswith("@@"):
            in_hunk = True
        elif in_hunk and manifest and line[:1] in "+-":
            name = _dependency_name(manifest, line[1:])
            if name:
                (added if line[0] == "+" else removed).add(name)
    return added, removed


@dataclass
class AdrText:
    text: str
    hex_tokens: set[str]
    pr_numbers: set[int]

    @classmethod
    def build(cls, docs: Sequence[AdrDoc]) -> AdrText:
        text = "\n".join("\n".join(d.lines) for d in docs)
        lowered = text.lower()
        prs = {int(a or b) for a, b in PR_NUMBER_TOKEN.findall(text)}
        return cls(text, set(HEX_TOKEN.findall(lowered)), prs)

    def names_commit(self, sha: str, pr_number: int | None, pr_url: str | None) -> bool:
        if sha in self.text or any(sha[:n] in self.hex_tokens for n in range(7, 41)):
            return True
        if pr_number is not None and pr_number in self.pr_numbers:
            return True
        return bool(pr_url and pr_url in self.text)

    def names_dependency(self, name: str) -> bool:
        return bool(
            re.search(rf"(?<![\w.-]){re.escape(name)}(?![\w-]|\.\w)", self.text, re.IGNORECASE)
        )


def _signals(
    commit: Commit, pr: dict[str, Any] | None, deps: tuple[set[str], set[str]] | None
) -> tuple[list[str], list[str]]:
    """Return (commit-level signals, dependency signals).

    A decision verb in the subject or PR title is a signal. A verb found only in a
    body is recorded as `body-verb` context and never makes a finding by itself:
    squash merges carry whole PR descriptions, and body verbs alone flagged over a
    third of ordinary commits when measured on this skill's home repository.
    """
    headline = commit.subject
    body = commit.body
    if pr:
        headline += f"\n{pr.get('title') or ''}"
        body += f"\n{pr.get('body') or ''}"
    found = []
    if BREAKING_SUBJECT.match(commit.subject) or BREAKING_FOOTER.search(commit.body):
        found.append("breaking-change")
    for label, rx in VERB_REGEXES:
        if rx.search(headline):
            found.append(f"verb: {label}")
        elif rx.search(body):
            found.append(f"body-verb: {label}")
    dep_signals: list[str] = []
    if deps:
        dep_signals += [f"dependency-added: {n}" for n in sorted(deps[0])]
        dep_signals += [f"dependency-removed: {n}" for n in sorted(deps[1])]
    return found, dep_signals


def _decisive(signals: Sequence[str]) -> bool:
    """True when a signal other than body-only verb context is present."""
    return any(not s.startswith("body-verb") for s in signals)


def _touches_adr(commit: Commit, dirs: Sequence[AdrDir]) -> bool:
    prefixes = tuple(f"{d.rel}/" for d in dirs)
    return bool(prefixes) and any(p.startswith(prefixes) for _, p in commit.paths)


def _undocumented(
    commit: Commit, pr: dict[str, Any] | None, signals: list[str], pr_number: int | None
) -> Finding:
    pr_url = (pr or {}).get("url") or (pr or {}).get("html_url")
    evidence: dict[str, Any] = {
        "sha": commit.sha,
        "date": commit.date,
        "subject": commit.subject,
        "signals": signals,
        "body": commit.body[:BODY_CAP],
    }
    if pr_number is not None:
        evidence["pr_number"] = pr_number
    if pr_url:
        evidence["pr_url"] = pr_url
    if pr:
        evidence["pr_title"] = str(pr.get("title") or "")[:300]
        evidence["pr_body"] = str(pr.get("body") or "")[:BODY_CAP]
    strong = any(s.startswith(("breaking", "dependency")) for s in signals)
    finding = make_finding(
        "undocumented-decision",
        HISTORY,
        "medium" if strong else "low",
        "heuristic",
        evidence,
        f"Candidate: commit {commit.sha[:10]} may record a decision no ADR names. "
        "Review it, then draft an ADR from it or dismiss it.",
        (commit.sha,),
    )
    finding["fix"] = ["draft", "--scan", "<SCAN_JSON>", "--id", finding["id"], "--out", "<ADR_DIR>"]
    return finding


def undocumented_decisions(
    commits: Sequence[Commit],
    dirs: Sequence[AdrDir],
    docs: Sequence[AdrDoc],
    prs: dict[int, dict[str, Any]],
    deps: dict[str, tuple[set[str], set[str]]],
) -> tuple[list[Finding], int]:
    """Return (findings, suppressed commit count)."""
    corpus = AdrText.build(docs)
    findings: list[Finding] = []
    suppressed = 0
    for commit in commits:
        if _touches_adr(commit, dirs):
            continue
        number = pr_number_of(commit)
        pr = prs.get(number) if number is not None else None
        url = (pr or {}).get("url") or (pr or {}).get("html_url")
        signals, dep_signals = _signals(commit, pr, deps.get(commit.sha))
        if not (_decisive(signals) or dep_signals):
            continue
        if corpus.names_commit(commit.sha, number, url):
            suppressed += 1
            continue
        dep_signals = [s for s in dep_signals if not corpus.names_dependency(s.split(": ", 1)[1])]
        if not (_decisive(signals) or dep_signals):
            suppressed += 1
            continue
        findings.append(
            _undocumented(commit, pr, signals + dep_signals[:MAX_DEPENDENCY_SIGNALS], number)
        )
    return findings, suppressed


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


def history_findings(
    repo: Path,
    dirs: Sequence[AdrDir],
    docs: Sequence[AdrDoc],
    commits: Sequence[Commit],
    prs: dict[int, dict[str, Any]],
) -> tuple[list[Finding], int]:
    """All History findings plus the suppressed-commit count. Raises GitError."""
    deps = dependency_changes(repo, [c.sha for c in commits])
    undocumented, suppressed = undocumented_decisions(commits, dirs, docs, prs, deps)
    findings = (
        undocumented
        + superseded_by_commits(commits, docs)
        + contradiction_candidates(commits, docs)
    )
    return findings, suppressed


__all__ = ["Commit", "GitError", "history_findings", "read_commits", "read_prs", "pr_number_of"]

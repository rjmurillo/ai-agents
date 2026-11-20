# Port of aligndottech/align-cli at commit 8d758e9899677b61442b08ffda74b74887bfc42a
# Ported upstream files:
#   src/lib/adr-writer.ts              (adrCandidates and linkedFromAdrs, lines 86-120)
#   src/commands/adr.ts                (runAdr, the list step, lines 25-35)
#   src/lib/first-run-pr-import.ts     (through adr_prs.py)
#   src/lib/fetchers/docs-decision-log.ts (through adr_log.py)
# Extensions E1 (decision-log candidates) and E3 (breaking-change signal) have no upstream source.
# Sibling ports: adr_text.py, adr_locate.py, adr_prs.py, adr_draft.py, adr_log.py.
# MIT, Copyright (c) 2026 Align Tech Ltd, see LICENSE-align
"""List the decisions in a repository that have no ADR yet. Read-only, no network.

Pipeline: commits from ``adr_git.read_commits``, then P6 merge promotion, P1 and P4 (the
commit filters in ``adr_shape.py``), P8 (the decision-shaped title filter), P5 (the reason),
P9 and P10 (pull requests and commit/PR dedup in ``adr_prs.py``), E1 (decision-log entries),
and last the suppression of every decision an existing ADR already names.

Departures from the upstream source, each pinned by a test:

- Upstream suppressed only on an exact URL. A decision is also hidden when an existing ADR
  holds its full SHA, a 7 or more character prefix of it as a whole word, its pull request
  URL, or ``#N`` for its pull request number. A URL matches whole, so ``issues/123`` does not
  hide ``issues/12``.
- ADR files are read in ``.md``, ``.mdx`` and ``.adoc`` in every located folder.
- E3: a commit with a ``type!:`` subject or a ``BREAKING CHANGE:`` footer is kept without a
  stated rationale and without a decision-shaped title. It still has to pass P1, so a
  ``chore!:`` subject or a release stays out. Its ``signals`` hold ``breaking-change``.
- E1: a decision-log entry that has an id and is not named by any ADR is a candidate.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from adr_commits import CommitRecord, breaking_change, is_decision_shaped_title
from adr_git import origin_web_base, read_commits, resolve_rev
from adr_locate import locate_folders, read_adr_texts
from adr_log import entry_date, read_log_entries
from adr_prs import PrRow, covering_numbers, is_covered, select_prs, trailing_pr_number
from adr_reason import extract_reason
from adr_shape import has_stated_rationale, is_decision_commit, resolve_commit_shape
from adr_text import hash_tokens, iso_day, issue_numbers, sanitize, urls_in, word_present

__all__ = ["DROP_KEYS", "EXCERPT_CHARS", "ExistingAdrs", "scan"]

EXCERPT_CHARS = 1200
DROP_KEYS = (
    "housekeeping",
    "no_rationale",
    "not_decision_shaped",
    "covered_by_pr",
    "already_documented",
    "pr_incomplete",
    "pr_bot",
    "pr_housekeeping",
    "pr_no_reason",
    "pr_not_decision_shaped",
    "log_no_id",
)
_MIN_SHA_PREFIX = 7

Candidate = dict[str, Any]


class ExistingAdrs:
    """What the existing ADRs name: hashes, URLs, ``#N`` numbers, and plain words."""

    def __init__(self, texts: list[tuple[str, str]]) -> None:
        self.texts = [text for _path, text in texts]
        self.hashes: set[str] = set()
        self.urls: set[str] = set()
        self.numbers: set[int] = set()
        for text in self.texts:
            self.hashes |= hash_tokens(text)
            self.urls |= urls_in(text)
            self.numbers |= issue_numbers(text)

    def _names_sha(self, sha: str) -> bool:
        full = sha.lower()
        return any(full[:size] in self.hashes for size in range(_MIN_SHA_PREFIX, len(full) + 1))

    def names(self, shas: tuple[str, ...], urls: tuple[str, ...], number: int | None) -> bool:
        """Does an ADR hold one of these SHAs (or a 7+ character prefix), one of these URLs, or ``#N``?"""
        if any(self._names_sha(sha) for sha in shas):
            return True
        if any(url.rstrip("/") in self.urls for url in urls):
            return True
        return number is not None and number in self.numbers

    def names_id(self, ident: str) -> bool:
        """Does an ADR name this decision-log id as a whole word?"""
        return any(word_present(ident, text) for text in self.texts)


@dataclass
class _Pending:
    candidate: Candidate
    shas: tuple[str, ...]
    urls: tuple[str, ...]
    number: int | None


def _excerpt(title: str, body: str) -> str:
    return sanitize(f"{title}\n\n{body}".strip(), EXCERPT_CHARS)


def _urls(
    web: tuple[str, str] | None, sha: str, number: int | None
) -> tuple[str | None, str | None]:
    """``(commit URL, pull request URL)`` on a GitHub or GitLab origin, else ``(None, None)``."""
    if web is None:
        return None, None
    kind, base = web
    commit = f"{base}/-/commit/{sha}" if kind == "gitlab" else f"{base}/commit/{sha}"
    pull = f"{base}/pull/{number}" if kind == "github" and number is not None else None
    return commit, pull


def _commit_pr_number(record: CommitRecord, promoted: str) -> int | None:
    from_squash = trailing_pr_number(promoted) or trailing_pr_number(record.subject)
    if from_squash is not None:
        return from_squash
    merge = record.subject.startswith("Merge pull request #")
    digits = record.subject[len("Merge pull request #") :].split(" ", 1)[0]
    return int(digits) if merge and digits.isdigit() else None


def _commit_pending(
    record: CommitRecord, web: tuple[str, str] | None, breaking: bool, subject: str, body: str
) -> _Pending:
    number = _commit_pr_number(record, subject)
    commit_url, pull_url = _urls(web, record.sha, number)
    candidate: Candidate = {
        "id": f"c-{record.sha[:7]}",
        "kind": "commit",
        "title": sanitize(subject).strip(),
        "reason": extract_reason(subject, body),
        "excerpt": _excerpt(subject, body),
        "date": iso_day(record.date),
        "source": {"sha": record.sha, "url": commit_url, "pr_number": number, "pr_url": pull_url},
        "signals": ["breaking-change"] if breaking else [],
    }
    urls = tuple(url for url in (commit_url, pull_url) if url)
    return _Pending(candidate, (record.sha,), urls, number)


def _commit_candidates(
    records: list[CommitRecord],
    covering: tuple[set[str], set[int]],
    web: tuple[str, str] | None,
    dropped: dict[str, int],
) -> list[_Pending]:
    pending: list[_Pending] = []
    for record in records:
        shape = resolve_commit_shape(record.subject, record.body)
        breaking = breaking_change(shape.subject, shape.body)
        if not is_decision_commit(shape.subject):
            dropped["housekeeping"] += 1
        elif not breaking and not has_stated_rationale(shape.subject, shape.body):
            dropped["no_rationale"] += 1
        elif not breaking and not is_decision_shaped_title(shape.subject):
            dropped["not_decision_shaped"] += 1
        elif is_covered(record.sha, (record.subject, shape.subject), *covering):
            dropped["covered_by_pr"] += 1
        else:
            pending.append(_commit_pending(record, web, breaking, shape.subject, shape.body))
    return pending


def _pr_pending(rows: list[PrRow], dropped: dict[str, int]) -> list[_Pending]:
    pending: list[_Pending] = []
    for row in rows:
        if not is_decision_shaped_title(row.title):
            dropped["pr_not_decision_shaped"] += 1
            continue
        candidate: Candidate = {
            "id": f"pr-{row.number}",
            "kind": "pr",
            "title": sanitize(row.title).strip(),
            "reason": row.reason,
            "excerpt": _excerpt(row.title, row.body),
            "date": row.merged_day,
            "source": {"number": row.number, "url": row.url, "sha": row.merge_sha},
            "signals": [],
        }
        shas = (row.merge_sha,) if row.merge_sha else ()
        pending.append(_Pending(candidate, shas, (row.url,), row.number))
    return pending


def _suppress(
    pending: list[_Pending], existing: ExistingAdrs, dropped: dict[str, int]
) -> list[Candidate]:
    kept: list[Candidate] = []
    for item in pending:
        if existing.names(item.shas, item.urls, item.number):
            dropped["already_documented"] += 1
        else:
            kept.append(item.candidate)
    return kept


def _log_candidates(root: Path, existing: ExistingAdrs, dropped: dict[str, int]) -> list[Candidate]:
    found: list[Candidate] = []
    taken: set[str] = set()
    for rel, entry in read_log_entries(root):
        if entry.id is None:
            dropped["log_no_id"] += 1
        elif existing.names_id(entry.id):
            dropped["already_documented"] += 1
        else:
            ident = f"log-{entry.id}"
            suffix = 1
            while ident in taken:
                suffix += 1
                ident = f"log-{entry.id}.{suffix}"
            taken.add(ident)
            rest = entry.text.split("\n", 1)[1] if "\n" in entry.text else ""
            found.append(
                {
                    "id": ident,
                    "kind": "decision-log",
                    "title": sanitize(entry.title).strip(),
                    "reason": extract_reason(entry.title, rest),
                    "excerpt": sanitize(entry.text, EXCERPT_CHARS),
                    "date": entry_date(entry.text),
                    "source": {"file": rel, "entry_id": entry.id},
                    "signals": [],
                }
            )
    return found


def _unique_ids(candidates: list[Candidate]) -> None:
    """Keep ids unique. A commit whose 7-character id is taken gets a 12-character one."""
    seen: set[str] = set()
    for candidate in candidates:
        if candidate["id"] in seen and candidate["kind"] == "commit":
            candidate["id"] = f"c-{candidate['source']['sha'][:12]}"
        seen.add(candidate["id"])


def scan(
    root: Path, rev: str, max_commits: int, since: str | None, prs: list[Any] | None
) -> dict[str, Any]:
    """The ``scan`` payload for the repository at ``root``. Reads git and the working tree only."""
    head = resolve_rev(root, rev)
    records, truncated = read_commits(root, head, max_commits, since)
    dropped = dict.fromkeys(DROP_KEYS, 0)
    pr_rows = select_prs(prs or [], dropped)
    web = origin_web_base(root)
    texts, skipped = read_adr_texts(root)
    existing = ExistingAdrs(texts)
    pending = _pr_pending(pr_rows, dropped)
    pending += _commit_candidates(records, covering_numbers(pr_rows), web, dropped)
    candidates = _suppress(pending, existing, dropped)
    candidates.sort(key=lambda item: item["date"] or "", reverse=True)
    candidates += _log_candidates(root, existing, dropped)
    _unique_ids(candidates)
    return {
        "repo": str(root),
        "rev": rev,
        "head": head,
        "max_commits": max_commits,
        "since": since,
        "truncated": truncated,
        "examined": {
            "commits": len(records),
            "prs": len(prs or []),
            "adr_files": len(texts),
            "adr_files_skipped": skipped,
        },
        "adr_folders": [path for path, _source in locate_folders(root)],
        "dropped": dropped,
        "candidates": candidates,
    }

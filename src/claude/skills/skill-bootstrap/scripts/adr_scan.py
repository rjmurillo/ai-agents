# Port of aligndottech/align-cli at commit 8d758e9899677b61442b08ffda74b74887bfc42a
# Ported upstream files:
#   src/lib/adr-writer.ts              (adrCandidates and linkedFromAdrs, lines 86-120)
#   src/commands/adr.ts                (runAdr, the list step, lines 25-35)
#   src/lib/first-run-pr-import.ts     (through adr_commits.py)
#   src/lib/fetchers/docs-decision-log.ts (through adr_docs.py)
#   src/lib/git.ts                     (replaced here by the raw-object commit reader)
# Extensions E1 (decision-log candidates) and E3 (breaking-change signal) have no upstream source.
# Sibling ports: adr_commits.py, adr_docs.py, adr_locate.py, bootstrap_adr.py.
# MIT, Copyright (c) 2026 Align Tech Ltd, see LICENSE-align
"""List the decisions in a repository that have no ADR yet. Read-only, no network.

Pipeline: commits from ``adr_scan.read_commits``, then P6 merge promotion, P1 and P4 (the
commit filters in ``adr_shape.py``), P8 (the decision-shaped title filter), P5 (the reason),
P9 and P10 (pull requests and commit/PR dedup in ``adr_commits.py``), E1 (decision-log entries),
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

Git access:

Run git with a timeout and read commits without trusting message text.

Commits are read in two steps. ``git rev-list`` gives the SHAs in history order. Those
SHAs go to ``git cat-file --batch``, whose reply is size-prefixed
(``<sha> commit <size>`` then exactly ``size`` bytes), so a commit message cannot add
or hide a record. Every reply must name the SHA that was asked for, in order, with the
type ``commit``. Anything else raises ``GitError``; the reader never resynchronizes.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from adr_commits import (
    EXCERPT_CHARS,
    CommitRecord,
    PrRow,
    breaking_change,
    covering_numbers,
    is_covered,
    is_decision_shaped_title,
    iso_day,
    parse_commit_object,
    sanitize,
    select_prs,
    trailing_pr_number,
)
from adr_docs import ExistingAdrs, log_candidates
from adr_locate import locate_folders, read_adr_texts
from adr_reason import extract_reason
from adr_shape import has_stated_rationale, is_decision_commit, resolve_commit_shape

__all__ = [
    "DROP_KEYS",
    "EXCERPT_CHARS",
    "GIT_TIMEOUT_S",
    "ConfigError",
    "ExistingAdrs",
    "GitError",
    "git_bytes",
    "git_text",
    "origin_web_base",
    "read_commits",
    "repo_root",
    "resolve_rev",
    "rev_list",
    "scan",
    "web_base",
]

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

Candidate = dict[str, Any]


@dataclass
class _Pending:
    candidate: Candidate
    shas: tuple[str, ...]
    urls: tuple[str, ...]
    number: int | None


_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_TASK_LINE = re.compile(r"^[ \t]*[-*][ \t]+\[[ xX]\][^\n]*\n?", re.MULTILINE)
_BLANK_RUN = re.compile(r"\n{3,}")


def _excerpt(title: str, body: str) -> str:
    """The quoted source text: template comments and checklist lines are form, not content.

    The body is cut before any pattern runs. ``<!--.*?-->`` is quadratic on a body of many
    unclosed ``<!--``, and only ``EXCERPT_CHARS`` of the result are kept.
    """
    body = body[: EXCERPT_CHARS * 4]
    body = _BLANK_RUN.sub("\n\n", _TASK_LINE.sub("", _HTML_COMMENT.sub("", body)))
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
    folders = locate_folders(root)
    texts, skipped = read_adr_texts(root, folders)
    existing = ExistingAdrs(texts)
    pending = _pr_pending(pr_rows, dropped)
    pending += _commit_candidates(records, covering_numbers(pr_rows), web, dropped)
    candidates = _suppress(pending, existing, dropped)
    candidates.sort(key=lambda item: item["date"] or "", reverse=True)
    candidates += log_candidates(root, existing, dropped)
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
        "adr_folders": [path for path, _source in folders],
        "dropped": dropped,
        "candidates": candidates,
    }


# ---------------------------------------------------------------------------
# Git access: run git with a timeout and read commits (no upstream source)
# ---------------------------------------------------------------------------

GIT_TIMEOUT_S = 30
BATCH_SHAS = 500
_SHA = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}", re.ASCII)
_BATCH_HEADER = re.compile(rb"([0-9a-f]{40}|[0-9a-f]{64}) ([a-z]+) ([0-9]+)\n", re.ASCII)


class ConfigError(Exception):
    """Bad input: exit 2."""


class GitError(Exception):
    """git is missing, failed, or timed out: exit 3."""


def git_bytes(
    repo: Path, *args: str, stdin: bytes | None = None
) -> subprocess.CompletedProcess[bytes]:
    """Run ``git -C repo args`` and return the raw result. Never decodes."""
    try:
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            input=stdin,
            capture_output=True,
            check=False,
            timeout=GIT_TIMEOUT_S,
        )
    except FileNotFoundError as exc:
        raise GitError("git is not installed or not on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"git {' '.join(args)} timed out after {GIT_TIMEOUT_S} s") from exc


def git_text(
    repo: Path, *args: str, ok: tuple[int, ...] = (0,)
) -> subprocess.CompletedProcess[str]:
    """Run git and decode stdout and stderr as UTF-8 with replacement."""
    proc = git_bytes(repo, *args)
    if proc.returncode not in ok:
        message = proc.stderr.decode("utf-8", "replace").strip()
        raise GitError(f"git {' '.join(args)} failed: {message}")
    return subprocess.CompletedProcess(
        proc.args,
        proc.returncode,
        proc.stdout.decode("utf-8", "replace"),
        proc.stderr.decode("utf-8", "replace"),
    )


def repo_root(path: Path) -> Path:
    """Return the work-tree root that contains ``path``, or raise ConfigError."""
    if not path.is_dir():
        raise ConfigError(f"repository path is not a directory: {path}")
    proc = git_bytes(path, "rev-parse", "--show-toplevel")
    if proc.returncode != 0:
        raise ConfigError(f"not a git repository: {path}")
    return Path(proc.stdout.decode("utf-8", "replace").strip()).resolve()


def resolve_rev(root: Path, rev: str) -> str:
    """Return the full commit SHA for ``rev``, or raise ConfigError."""
    if rev.startswith("-"):
        raise ConfigError(f"rev may not start with '-': {rev!r}")
    proc = git_bytes(root, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")
    if proc.returncode != 0:
        raise ConfigError(f"rev does not name a commit: {rev!r}")
    return proc.stdout.decode("ascii", "replace").strip()


def rev_list(root: Path, sha: str, max_count: int, since: str | None) -> list[str]:
    """Up to ``max_count`` commit SHAs reachable from ``sha``, newest first."""
    args = ["rev-list", f"--max-count={max_count}"]
    if since:
        args.append(f"--since={since}")
    out = git_text(root, *args, sha, "--").stdout
    shas = out.split()
    if any(not _SHA.fullmatch(item) for item in shas):
        raise GitError("git rev-list printed something that is not a SHA")
    return shas


def _read_batch(root: Path, shas: list[str]) -> list[CommitRecord]:
    proc = git_bytes(root, "cat-file", "--batch", stdin=("\n".join(shas) + "\n").encode("ascii"))
    if proc.returncode != 0:
        message = proc.stderr.decode("utf-8", "replace").strip()
        raise GitError(f"git cat-file --batch failed: {message}")
    data, pos, records = proc.stdout, 0, []
    for expected in shas:
        header = _BATCH_HEADER.match(data, pos)
        if header is None or header[1].decode("ascii") != expected or header[2] != b"commit":
            raise GitError(f"git cat-file --batch did not return commit {expected}")
        start = header.end()
        end = start + int(header[3])
        if data[end : end + 1] != b"\n":
            raise GitError(f"git cat-file --batch returned a short object for {expected}")
        records.append(parse_commit_object(expected, data[start:end]))
        pos = end + 1
    if pos != len(data):
        raise GitError("git cat-file --batch returned more data than was asked for")
    return records


_URL_REMOTE = re.compile(
    r"(?:https?|ssh|git)://(?:[^@/]*@)?(?P<host>[A-Za-z0-9.-]+)(?::[0-9]+)?/(?P<path>.+)\Z",
    re.ASCII,
)
_SCP_REMOTE = re.compile(r"(?:[^@/:]+@)?(?P<host>[A-Za-z0-9.-]+):(?P<path>[^/].*)\Z", re.ASCII)
_REPO_PATH = re.compile(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+\Z", re.ASCII)
_HOSTED = re.compile(r"(?:github|gitlab)\.[a-z0-9.-]+\Z", re.ASCII)


def web_base(remote: str) -> tuple[str, str] | None:
    """``(kind, https base)`` for an https or ssh GitHub or GitLab remote, else None.

    Only the host and the repository path are kept, so a ``user:token@`` in the remote
    never reaches the result. ``kind`` is ``github`` or ``gitlab``.
    """
    text = remote.strip()
    match = _URL_REMOTE.fullmatch(text) or _SCP_REMOTE.fullmatch(text)
    if match is None:
        return None
    host = match["host"].lower()
    path = match["path"].strip("/").removesuffix(".git").strip("/")
    if not _HOSTED.fullmatch(host) or not _REPO_PATH.fullmatch(path):
        return None
    return ("github" if host.startswith("github.") else "gitlab"), f"https://{host}/{path}"


def origin_web_base(root: Path) -> tuple[str, str] | None:
    """``web_base`` of the ``origin`` remote. A repository with no origin gives None."""
    proc = git_text(root, "config", "--get", "remote.origin.url", ok=(0, 1))
    return web_base(proc.stdout) if proc.returncode == 0 else None


def read_commits(
    root: Path, sha: str, max_commits: int, since: str | None = None
) -> tuple[list[CommitRecord], bool]:
    """Read up to ``max_commits`` commits from ``sha``. The flag is True when more exist."""
    shas = rev_list(root, sha, max_commits + 1, since)
    truncated = len(shas) > max_commits
    shas = shas[:max_commits]
    records: list[CommitRecord] = []
    for start in range(0, len(shas), BATCH_SHAS):
        records.extend(_read_batch(root, shas[start : start + BATCH_SHAS]))
    return records, truncated

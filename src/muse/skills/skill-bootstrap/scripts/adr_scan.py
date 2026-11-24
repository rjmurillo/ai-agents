# Port of aligndottech/align-cli at commit 8d758e9899677b61442b08ffda74b74887bfc42a
# Ported upstream files:
#   src/lib/adr-writer.ts              (adrCandidates and linkedFromAdrs, lines 86-120)
#   src/commands/adr.ts                (runAdr, the list step, lines 25-35)
#   src/lib/first-run-pr-import.ts     (through adr_commits.py)
#   src/lib/fetchers/docs-decision-log.ts (through adr_docs.py)
#   src/lib/git.ts                     (replaced here by the raw-object commit reader)
# Extensions E1 (decision-log candidates) and E3 (breaking-change signal) have no upstream source.
# Sibling ports: adr_shape.py, adr_reason.py, adr_commits.py, adr_docs.py, adr_locate.py,
# adr_scan.py, bootstrap_adr.py.
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

Git runs with a timeout, a clean environment, and no trust in message text. Commits are
read in two steps. ``git rev-list`` gives the SHAs in history order. Those
SHAs go to ``git cat-file --batch``, whose reply is size-prefixed
(``<sha> commit <size>`` then exactly ``size`` bytes), so a commit message cannot add
or hide a record. Every reply must name the SHA that was asked for, in order, with the
type ``commit``. Anything else raises ``GitError``; the reader never resynchronizes.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from adr_commits import (
    CommitRecord,
    PrRow,
    breaking_change,
    commit_pr_number,
    commit_urls,
    covering_numbers,
    covering_pr,
    excerpt,
    iso_day,
    parse_commit_object,
    sanitize,
    select_prs,
    web_base,
    without_merge_lines,
)
from adr_docs import DROP_KEYS, ExistingAdrs, log_candidates
from adr_locate import AdrTally, locate_folders, read_adr_texts
from adr_reason import extract_reason
from adr_shape import (
    CommitShape,
    has_stated_rationale,
    is_decision_commit,
    is_decision_shaped_title,
    is_one_off_change_title,
    resolve_commit_shape,
)

__all__ = [
    "DROP_KEYS",
    "GIT_TIMEOUT_S",
    "MAX_BATCH_BYTES",
    "MAX_COMMITS",
    "MAX_COMMIT_BYTES",
    "ConfigError",
    "ExistingAdrs",
    "GitError",
    "git_bytes",
    "git_env",
    "git_text",
    "is_shallow",
    "origin_web_base",
    "read_commits",
    "refusal",
    "repo_root",
    "resolve_rev",
    "rev_list",
    "scan",
    "stderr_text",
    "web_base",
]

MAX_COMMITS = 100_000
Candidate = dict[str, Any]


@dataclass
class _Pending:
    candidate: Candidate
    shas: tuple[str, ...]
    urls: tuple[str, ...]
    number: int | None


def _commit_pending(
    record: CommitRecord, web: tuple[str, str] | None, breaking: bool, shape: CommitShape
) -> _Pending:
    number = commit_pr_number(record, shape.subject)
    commit_url, pull_url = commit_urls(web, record.sha, number)
    candidate: Candidate = {
        "id": f"c-{record.sha[:7]}",
        "kind": "commit",
        "title": sanitize(shape.subject).strip(),
        "reason": extract_reason(shape.subject, shape.body),
        "excerpt": excerpt(shape.subject, shape.body),
        "date": iso_day(record.date),
        "source": {"sha": record.sha, "url": commit_url, "pr_number": number, "pr_url": pull_url},
        "signals": ["breaking-change"] if breaking else [],
    }
    urls = tuple(url for url in (commit_url, pull_url) if url)
    return _Pending(candidate, (record.sha,), urls, number)


def _states_reason(record: CommitRecord, shape: CommitShape) -> bool:
    """The rationale gate. A promoted merge is read without its ``Merge pull request`` line, and
    it also passes when its title is not a one-off change note: a title names a change, not why."""
    if shape.subject == record.subject:
        return has_stated_rationale(shape.subject, shape.body)
    body = without_merge_lines(shape.body)
    return has_stated_rationale(shape.subject, body) or not is_one_off_change_title(shape.subject)


def _commit_candidates(
    records: list[CommitRecord],
    covering: tuple[dict[str, int], set[int]],
    web: tuple[str, str] | None,
    dropped: dict[str, int],
) -> tuple[list[_Pending], set[int]]:
    """The commit candidates, and the numbers of the kept pull requests that cover a breaking
    commit (E3): such a pull request carries the signal, because the commit is dropped."""
    pending: list[_Pending] = []
    carried: set[int] = set()
    for record in records:
        shape = resolve_commit_shape(record.subject, record.body)
        breaking = breaking_change(shape.subject, shape.body)
        covered = covering_pr(record, shape.subject, *covering)
        if not is_decision_commit(shape.subject):
            dropped["housekeeping"] += 1
        elif not breaking and not _states_reason(record, shape):
            dropped["no_rationale"] += 1
        elif not breaking and not is_decision_shaped_title(shape.subject):
            dropped["not_decision_shaped"] += 1
        elif covered is not None:
            dropped["covered_by_pr"] += 1
            if breaking:
                carried.add(covered)
        else:
            pending.append(_commit_pending(record, web, breaking, shape))
    return pending, carried


def _pr_pending(rows: list[PrRow], dropped: dict[str, int]) -> tuple[list[_Pending], list[PrRow]]:
    """The pull request candidates, and the rows that survived every filter.

    A breaking change (E3) keeps a pull request whose title is not decision-shaped, as it keeps
    a commit, once the commit floor has passed it (``chore!:`` stays out). Only the surviving
    rows may cover a commit.
    """
    pending: list[_Pending] = []
    kept: list[PrRow] = []
    for row in rows:
        breaking = breaking_change(row.title, row.body)
        if not is_decision_shaped_title(row.title) and not (
            breaking and is_decision_commit(row.title)
        ):
            dropped["pr_not_decision_shaped"] += 1
            continue
        candidate: Candidate = {
            "id": f"pr-{row.number}",
            "kind": "pr",
            "title": sanitize(row.title).strip(),
            "reason": row.reason,
            "excerpt": excerpt(row.title, row.body),
            "date": row.merged_day,
            "source": {"number": row.number, "url": row.url, "sha": row.merge_sha},
            "signals": ["breaking-change"] if breaking else [],
        }
        shas = (row.merge_sha,) if row.merge_sha else ()
        pending.append(_Pending(candidate, shas, (row.url,), row.number))
        kept.append(row)
    return pending, kept


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
    if not 1 <= max_commits <= MAX_COMMITS:
        raise ConfigError(f"max commits must be from 1 to {MAX_COMMITS}, not {max_commits}")
    head = resolve_rev(root, rev)
    dropped = dict.fromkeys(DROP_KEYS, 0)
    records, truncated = read_commits(root, head, max_commits, since, dropped)
    web = origin_web_base(root)
    pr_rows = select_prs(prs or [], dropped, web[1] if web else None)
    folders, walk_truncated = locate_folders(root)
    tally = AdrTally()
    existing = ExistingAdrs(read_adr_texts(root, folders, tally))
    pending, kept_prs = _pr_pending(pr_rows, dropped)
    commits, carried = _commit_candidates(records, covering_numbers(kept_prs), web, dropped)
    for item in pending:
        if item.number in carried and not item.candidate["signals"]:
            item.candidate["signals"].append("breaking-change")
    pending += commits
    candidates = _suppress(pending, existing, dropped)
    candidates.sort(key=lambda item: item["date"] or "", reverse=True)
    log_found, log_files, log_skipped = log_candidates(root, existing, dropped)
    candidates += log_found
    _unique_ids(candidates)
    return {
        "repo": str(root),
        "rev": rev,
        "head": head,
        "max_commits": max_commits,
        "since": since,
        "truncated": truncated,
        "shallow": is_shallow(root),
        "walk_truncated": walk_truncated,
        "adr_corpus_truncated": tally.cut,
        "examined": {
            "commits": len(records),
            "prs": len(prs or []),
            "adr_files": tally.read,
            "adr_files_skipped": tally.skipped,
            "log_files": log_files,
            "log_files_skipped": log_skipped,
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
MAX_COMMIT_BYTES = 1024 * 1024
MAX_BATCH_BYTES = 16 * 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}", re.ASCII)
_CHECK_ROW = re.compile(rb"([0-9a-f]{40}|[0-9a-f]{64}) commit ([0-9]+)\n", re.ASCII)
_CHECK_REPLY = re.compile(rb"(?:(?:[0-9a-f]{40}|[0-9a-f]{64}) commit [0-9]+\n)*", re.ASCII)
_BATCH_HEADER = re.compile(rb"([0-9a-f]{40}|[0-9a-f]{64}) ([a-z]+) ([0-9]+)\n", re.ASCII)


class ConfigError(Exception):
    """Bad input: exit 2."""


class GitError(Exception):
    """git is missing, failed, or timed out: exit 3."""


# What ``git rev-parse --local-env-vars`` lists, plus GIT_NAMESPACE and the two discovery limits.
# Hard-coded so no extra git call is spent. Any of them in the parent environment would point the
# child at another repository, or hide the work tree around a folder, whatever ``-C`` says.
_LOCAL_GIT_ENV = frozenset(
    "GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_CEILING_DIRECTORIES GIT_COMMON_DIR GIT_CONFIG "
    "GIT_CONFIG_COUNT GIT_CONFIG_PARAMETERS GIT_DIR GIT_DISCOVERY_ACROSS_FILESYSTEM "
    "GIT_GRAFT_FILE GIT_IMPLICIT_WORK_TREE GIT_INDEX_FILE GIT_NAMESPACE GIT_NO_REPLACE_OBJECTS "
    "GIT_OBJECT_DIRECTORY GIT_PREFIX GIT_REPLACE_REF_BASE GIT_SHALLOW_FILE GIT_WORK_TREE".split()
)


def git_env() -> dict[str, str]:
    """The environment for a git child: no repository redirection, no prompt, English messages.

    ``LC_ALL=C`` keeps the stderr texts this module matches (``not a git repository``,
    ``dubious ownership``) the same on every locale.
    """
    env = {key: value for key, value in os.environ.items() if key not in _LOCAL_GIT_ENV}
    env.update(GIT_TERMINAL_PROMPT="0", GIT_NO_LAZY_FETCH="1", LC_ALL="C")
    return env


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
            env=git_env(),
        )
    except FileNotFoundError as exc:
        raise GitError("git is not installed or not on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"git {' '.join(args)} timed out after {GIT_TIMEOUT_S} s") from exc
    except OSError as exc:
        raise GitError(f"cannot run git: {exc}") from exc


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


def stderr_text(proc: subprocess.CompletedProcess[bytes]) -> str:
    """git's stderr, decoded and trimmed."""
    return proc.stderr.decode("utf-8", "replace").strip()


def refusal(proc: subprocess.CompletedProcess[bytes], what: str) -> Exception:
    """The error for a failed git call: a dubious-ownership refusal is git's, the rest is input.

    ``what`` says what the caller asked. git's own words are always kept.
    """
    message = stderr_text(proc)
    if "dubious ownership" in message:
        return GitError(f"git refused to work in {what}: {message}")
    return ConfigError(f"{what} ({message})" if message else what)


def repo_root(path: Path) -> Path:
    """Return the work-tree root that contains ``path``, or raise ConfigError."""
    if not path.is_dir():
        raise ConfigError(f"repository path is not a directory: {path}")
    proc = git_bytes(path, "rev-parse", "--show-toplevel")
    if proc.returncode != 0:
        raise refusal(proc, f"not a git repository: {path}")
    return Path(proc.stdout.decode("utf-8", "replace").strip()).resolve()


def resolve_rev(root: Path, rev: str) -> str:
    """Return the full commit SHA for ``rev``, or raise ConfigError."""
    if rev.startswith("-"):
        raise ConfigError(f"rev may not start with '-': {rev!r}")
    proc = git_bytes(root, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")
    if proc.returncode != 0:
        raise refusal(proc, f"rev does not name a commit: {rev!r}")
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


def _sizes(root: Path, shas: list[str]) -> list[int]:
    """The object size of each SHA from ``git cat-file --batch-check``.

    The reply gets the same strict check as the batch read: one ``<sha> commit <size>`` line per
    SHA, in order, and nothing else.
    """
    if not shas:
        return []
    stdin = ("\n".join(shas) + "\n").encode("ascii")
    proc = git_bytes(root, "cat-file", "--batch-check", stdin=stdin)
    if proc.returncode != 0:
        raise GitError(f"git cat-file --batch-check failed: {stderr_text(proc)}")
    rows = _CHECK_ROW.findall(proc.stdout)
    if not _CHECK_REPLY.fullmatch(proc.stdout) or [row[0].decode("ascii") for row in rows] != shas:
        raise GitError("git cat-file --batch-check did not return the requested commits")
    return [int(row[1]) for row in rows]


def _batches(shas: list[str], sizes: list[int], dropped: dict[str, int]) -> list[list[str]]:
    """The SHAs to read, in order, grouped into batches.

    A batch holds at most ``BATCH_SHAS`` SHAs and ``MAX_BATCH_BYTES`` of objects, but one object
    always forms a batch of its own. A commit over ``MAX_COMMIT_BYTES`` is counted under
    ``commit_too_large`` and left out.
    """
    batches: list[list[str]] = []
    total = 0
    for sha, size in zip(shas, sizes, strict=True):
        if size > MAX_COMMIT_BYTES:
            dropped["commit_too_large"] = dropped.get("commit_too_large", 0) + 1
        elif batches and len(batches[-1]) < BATCH_SHAS and total + size <= MAX_BATCH_BYTES:
            batches[-1].append(sha)
            total += size
        else:
            batches.append([sha])
            total = size
    return batches


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


def origin_web_base(root: Path) -> tuple[str, str] | None:
    """``web_base`` of the ``origin`` remote. A repository with no origin gives None."""
    proc = git_text(root, "config", "--get", "remote.origin.url", ok=(0, 1))
    return web_base(proc.stdout) if proc.returncode == 0 else None


def is_shallow(root: Path) -> bool:
    """True for a shallow clone: history older than its boundary was never fetched."""
    return git_text(root, "rev-parse", "--is-shallow-repository").stdout.strip() == "true"


def read_commits(
    root: Path,
    sha: str,
    max_commits: int,
    since: str | None = None,
    dropped: dict[str, int] | None = None,
) -> tuple[list[CommitRecord], bool]:
    """Read up to ``max_commits`` commits from ``sha``. The flag is True when more exist.

    Object sizes are read first, so no batch holds more than ``MAX_BATCH_BYTES``. A commit over
    ``MAX_COMMIT_BYTES`` is counted in ``dropped`` and not read.
    """
    shas = rev_list(root, sha, max_commits + 1, since)
    truncated = len(shas) > max_commits
    shas = shas[:max_commits]
    records: list[CommitRecord] = []
    for batch in _batches(shas, _sizes(root, shas), {} if dropped is None else dropped):
        records.extend(_read_batch(root, batch))
    return records, truncated

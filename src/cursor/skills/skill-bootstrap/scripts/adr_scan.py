# Port of aligndottech/align-cli at commit 8d758e9899677b61442b08ffda74b74887bfc42a
# Ported upstream files:
#   src/lib/adr-writer.ts              (adrCandidates and linkedFromAdrs, lines 86-120)
#   src/commands/adr.ts                (runAdr, the list step, lines 25-35)
#   src/lib/first-run-pr-import.ts     (through adr_commits.py)
#   src/lib/fetchers/docs-decision-log.ts (through adr_docs.py)
#   src/lib/git.ts                     (replaced here by the raw-object commit reader)
# Extensions E1 (decision-log candidates) and E3 (breaking-change signal) have no upstream source.
# Sibling ports: adr_shape.py, adr_reason.py, adr_commits.py, adr_docs.py, adr_locate.py,
# adr_log.py, adr_scan.py, bootstrap_adr.py.
# MIT, Copyright (c) 2026 Align Tech Ltd, see LICENSE-align
"""List the decisions in a repository that have no ADR yet. Read-only, no network.

Pipeline: commits in batches, P6 merge promotion, P1 and P4 (``adr_shape.py``), P8 (title), P5
(reason), P9 and P10 (PRs, commit/PR dedup: ``adr_commits.py``), E1 (decision logs), then the
suppression of every decision an existing ADR names. Departures, each pinned by a test:

- An ADR hides a decision by the full SHA, a 7+ character prefix as a whole word, the whole PR
  URL, or ``#N`` (upstream: an exact URL only), read from ``.md``, ``.mdx`` and ``.adoc`` files
  in every located folder.
- E3: a ``type!:`` subject or ``BREAKING CHANGE:`` footer keeps a commit with no stated
  rationale or decision-shaped title past ``passes_floor``; ``signals`` holds ``breaking-change``.
- E1: a decision-log entry that has an id and is not named by any ADR is a candidate.

Git runs with a timeout, a clean environment, no replacement objects and no trust in message
text: ``cat-file --batch`` reads ``rev-list`` SHAs size-prefixed, and each reply must name the
SHA asked for, in order, as a ``commit``, else ``GitError``; the reader never resyncs.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

from adr_commits import (
    CommitRecord,
    PrRow,
    commit_pr_number,
    commit_urls,
    covering_numbers,
    covering_pr,
    excerpt,
    iso_day,
    parse_commit_object,
    passes_floor,
    sanitize,
    select_prs,
    web_base,
    without_merge_lines,
)
from adr_docs import DROP_KEYS, ExistingAdrs
from adr_locate import AdrTally, locate_folders, read_adr_texts
from adr_log import log_candidates
from adr_reason import breaking_change, extract_reason
from adr_shape import (
    CommitShape,
    has_stated_rationale,
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

MAX_COMMITS = 10_000
Candidate = dict[str, Any]
Web = tuple[str, str] | None  # ``web_base`` of the origin
Drops = dict[str, int]  # drop counts by filter


@dataclass
class _Pending:
    candidate: Candidate
    shas: tuple[str, ...]
    urls: tuple[str, ...]
    number: int | None


def _commit_pending(record: CommitRecord, web: Web, breaking: bool, shape: CommitShape) -> _Pending:
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
    batches: Iterable[list[CommitRecord]], rows: list[PrRow], web: Web, dropped: Drops
) -> tuple[list[_Pending], dict[int, list[_Pending]], int]:
    """Commit candidates, covered commits per kept PR, and the count read. Each batch is classified
    as read: only candidate data outlives it. A filtered commit hands its PR only SHA and URLs."""
    pending: list[_Pending] = []
    carried: dict[int, list[_Pending]] = {}
    examined, covering = 0, covering_numbers(rows)
    for record in (record for batch in batches for record in batch):
        examined += 1
        shape = resolve_commit_shape(record.subject, record.body)
        breaking = record.breaking or breaking_change(shape.subject, "")  # promoted ``type!:``
        covered = covering_pr(record, shape.subject, *covering)
        if not passes_floor(shape.subject, breaking):
            dropped["housekeeping"] += 1
        elif not breaking and not _states_reason(record, shape):
            dropped["no_rationale"] += 1
        elif not breaking and not is_decision_shaped_title(shape.subject):
            dropped["not_decision_shaped"] += 1
        elif covered is None:
            pending.append(_commit_pending(record, web, breaking, shape))
        else:
            dropped["covered_by_pr"] += 1
            carried.setdefault(covered, []).append(_commit_pending(record, web, breaking, shape))
            continue
        if covered is not None:  # filtered out, yet its SHA and URLs still name the PR
            names = _commit_pending(record, web, False, shape)
            names.candidate["reason"] = None
            carried.setdefault(covered, []).append(names)
    return pending, carried, examined


def _pr_pending(rows: list[PrRow]) -> list[_Pending]:
    """The candidates of the rows ``select_prs`` kept, title filter included."""
    pending: list[_Pending] = []
    for row in rows:
        candidate: Candidate = {
            "id": f"pr-{row.number}",
            "kind": "pr",
            "title": sanitize(row.title).strip(),
            "reason": row.reason,
            "excerpt": excerpt(row.title, row.body),
            "date": row.merged_day,
            "source": {"number": row.number, "url": row.url, "sha": row.merge_sha},
            "signals": ["breaking-change"] if row.breaking else [],
        }
        shas = (row.merge_sha,) if row.merge_sha else ()
        pending.append(_Pending(candidate, shas, (row.url,), row.number))
    return pending


def _absorb(pr: _Pending, commit: _Pending) -> None:
    """A pull request takes from a covered commit its E3 signal, its SHA and its commit URL (not a
    PR URL its subject names), so an ADR citing the commit hides the PR. A reason the PR lacks is
    taken too, and ``source.reason_sha`` and ``reason_url`` name the commit that stated it."""
    if commit.candidate["signals"] and not pr.candidate["signals"]:
        pr.candidate["signals"].append("breaking-change")
    if not pr.candidate["reason"] and commit.candidate["reason"]:
        pr.candidate["reason"] = commit.candidate["reason"]
        cited = commit.candidate["source"]
        pr.candidate["source"].update(reason_sha=cited["sha"], reason_url=cited["url"])
    pr.shas += commit.shas
    pr.urls += tuple(url for url in (commit.candidate["source"]["url"],) if url)


def _suppress(items: list[_Pending], adrs: ExistingAdrs, dropped: Drops) -> list[Candidate]:
    kept = [item.candidate for item in items if not adrs.names(item.shas, item.urls, item.number)]
    dropped["already_documented"] += len(items) - len(kept)
    return kept


def _unique_ids(candidates: list[Candidate]) -> None:
    """Keep ids unique. A commit whose 7-character id is taken gets a 12-character one, and any
    id still taken gets ``.2``, ``.3`` and so on, so ``draft --id`` always names one candidate."""
    seen: set[str] = set()
    for candidate in candidates:
        if candidate["id"] in seen and candidate["kind"] == "commit":
            candidate["id"] = f"c-{candidate['source']['sha'][:12]}"
        base, count = candidate["id"], 1
        while candidate["id"] in seen:
            count += 1
            candidate["id"] = f"{base}.{count}"
        seen.add(candidate["id"])


def scan(
    root: Path, rev: str, max_commits: int, since: str | None, prs: list[Any] | None
) -> dict[str, Any]:
    """The ``scan`` payload for ``root``, from git and the work tree; refuses a fetching clone first."""
    if not 1 <= max_commits <= MAX_COMMITS:
        raise ConfigError(f"max commits must be from 1 to {MAX_COMMITS}, not {max_commits}")
    refuse_lazy_fetch(root)
    head = resolve_rev(root, rev)
    dropped = dict.fromkeys(DROP_KEYS, 0)
    batches, truncated = _record_batches(root, head, max_commits, since, dropped)
    web, base = origin_web_base(root)
    pr_rows = select_prs(prs or [], dropped, base)
    folders, walk_truncated = locate_folders(root)
    tally = AdrTally()
    existing = ExistingAdrs(read_adr_texts(root, folders, tally))
    pending = _pr_pending(pr_rows)
    commits, carried, read = _commit_candidates(batches, pr_rows, web, dropped)
    for item in pending:
        for covered in carried.get(item.number or -1, []):
            _absorb(item, covered)
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
            "commits": read,
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


# --- Git access: run git with a timeout and read commits (no upstream source) ---

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


# ``git rev-parse --local-env-vars``, GIT_NAMESPACE and the discovery ceiling, hard-coded to
# spare a git call. Inherited, any would point the child at another repository or hide the work
# tree around a folder, whatever ``-C`` says. GIT_DISCOVERY_ACROSS_FILESYSTEM is forced on.
_LOCAL_GIT_ENV = frozenset(
    "GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_CEILING_DIRECTORIES GIT_COMMON_DIR GIT_CONFIG "
    "GIT_CONFIG_COUNT GIT_CONFIG_PARAMETERS GIT_DIR "
    "GIT_GRAFT_FILE GIT_IMPLICIT_WORK_TREE GIT_INDEX_FILE GIT_NAMESPACE GIT_NO_REPLACE_OBJECTS "
    "GIT_OBJECT_DIRECTORY GIT_PREFIX GIT_REPLACE_REF_BASE GIT_SHALLOW_FILE GIT_WORK_TREE".split()
)


def git_env() -> dict[str, str]:
    """A git child's environment: no repository redirection, prompt, or replacement objects (a
    replaced commit is never read under the original's SHA). ``LC_ALL=C`` fixes the stderr texts
    matched here; discovery crosses a mount, so the draft gate sees a mounted work tree folder."""
    env = {key: value for key, value in os.environ.items() if key not in _LOCAL_GIT_ENV}
    env.update(GIT_TERMINAL_PROMPT="0", GIT_NO_LAZY_FETCH="1", GIT_NO_REPLACE_OBJECTS="1")
    env.update(GIT_DISCOVERY_ACROSS_FILESYSTEM="1", LC_ALL="C")
    return env


def git_bytes(repo: Path, *args: str, stdin: bytes | None = None) -> CompletedProcess[bytes]:
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


def git_text(repo: Path, *args: str, ok: tuple[int, ...] = (0,)) -> CompletedProcess[str]:
    """Run git and decode stdout and stderr as UTF-8 with replacement."""
    proc = git_bytes(repo, *args)
    if proc.returncode not in ok:
        raise GitError(f"git {' '.join(args)} failed: {stderr_text(proc)}")
    out, err = (part.decode("utf-8", "replace") for part in (proc.stdout, proc.stderr))
    return CompletedProcess(proc.args, proc.returncode, out, err)


def stderr_text(proc: CompletedProcess[bytes]) -> str:
    """git's stderr, decoded and trimmed."""
    return proc.stderr.decode("utf-8", "replace").strip()


def refusal(proc: CompletedProcess[bytes], what: str) -> Exception:
    """The error for a failed git call on ``what``, git's words kept: dubious ownership or input."""
    message = stderr_text(proc)
    if "dubious ownership" in message:
        return GitError(f"git refused to work in {what}: {message}")
    return ConfigError(f"{what} ({message})" if message else what)


def repo_root(path: Path) -> Path:
    """Return the work-tree root that contains ``path``, or raise ConfigError. git honors a
    ``core.worktree`` that names another folder, so the root must hold ``path``."""
    if not path.is_dir():
        raise ConfigError(f"repository path is not a directory: {path}")
    proc = git_bytes(path, "rev-parse", "--show-toplevel")
    if proc.returncode != 0:
        raise refusal(proc, f"not a git repository: {path}")
    top = Path(os.fsdecode(proc.stdout.removesuffix(b"\n"))).resolve()  # the bytes, unchanged
    here = path.resolve()
    try:  # samefile, so a link or a case variant of the root still counts
        inside = any(os.path.samefile(top, item) for item in (here, *here.parents))
    except OSError:  # the root git named does not exist
        inside = False
    if not inside:
        raise ConfigError(f"git names the work tree {top}, which does not contain {path}")
    return top


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
        args.append(f"--since-as-filter={since}")  # --since stops at an older child; git 2.37
    out = git_text(root, *args, sha, "--").stdout
    shas = out.split()
    if any(not _SHA.fullmatch(item) for item in shas):
        raise GitError("git rev-list printed something that is not a SHA")
    return shas


def _sizes(root: Path, shas: list[str]) -> list[int]:
    """Each SHA's size from ``git cat-file --batch-check``: one ``<sha> commit <size>`` line per
    SHA, in order, and nothing else."""
    if not shas:
        return []
    proc = git_bytes(root, "cat-file", "--batch-check", stdin=("\n".join(shas) + "\n").encode())
    if proc.returncode != 0:
        raise GitError(f"git cat-file --batch-check failed: {stderr_text(proc)}")
    rows = _CHECK_ROW.findall(proc.stdout)
    if not _CHECK_REPLY.fullmatch(proc.stdout) or [row[0].decode("ascii") for row in rows] != shas:
        raise GitError("git cat-file --batch-check did not return the requested commits")
    return [int(row[1]) for row in rows]


def _batches(shas: list[str], sizes: list[int], dropped: dict[str, int]) -> list[list[str]]:
    """SHAs in order, in batches of at most ``BATCH_SHAS`` and ``MAX_BATCH_BYTES`` (one object can
    always form a batch). A commit over ``MAX_COMMIT_BYTES`` counts as ``commit_too_large``."""
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
        raise GitError(f"git cat-file --batch failed: {stderr_text(proc)}")
    data, pos, records = proc.stdout, 0, []
    for expected in shas:
        header = _BATCH_HEADER.match(data, pos)
        if header is None or header[1].decode("ascii") != expected or header[2] != b"commit":
            raise GitError(f"git cat-file --batch did not return commit {expected}")
        start, end = header.end(), header.end() + int(header[3])
        if data[end : end + 1] != b"\n":
            raise GitError(f"git cat-file --batch returned a short object for {expected}")
        records.append(parse_commit_object(expected, data[start:end]))
        pos = end + 1
    if pos != len(data):
        raise GitError("git cat-file --batch returned more data than was asked for")
    return records


def origin_web_base(root: Path) -> tuple[Web, str | None]:
    """``web_base`` of origin's fetch URL (``insteadOf`` applied, no fetch) and the ``select_prs``
    base: None if git says ``No such remote`` (any exit code), ``""`` off GitHub and GitLab."""
    proc = git_bytes(root, "remote", "get-url", "origin")
    if proc.returncode != 0 and "No such remote" in stderr_text(proc):
        return None, None
    if proc.returncode != 0:
        raise GitError(f"git remote get-url origin failed: {stderr_text(proc)}")
    web = web_base(proc.stdout.decode("utf-8", "replace"))
    return web, web[1] if web else ""


# GIT_NO_LAZY_FETCH, which stops a partial clone fetching a missing object, came in git 2.45.1
# and the May 2024 security releases of 2.39 to 2.44.
_NO_LAZY_FETCH_GIT = (2, 45, 1)
_NO_LAZY_FETCH_BACKPORTS = {(2, 39): 4, (2, 40): 2, (2, 41): 1, (2, 42): 2, (2, 43): 4, (2, 44): 1}
_PROMISOR = re.compile(  # a partial-clone config line; any filter value counts, even empty
    r"extensions\.partialclone \S|remote\..*\.partialclonefilter(?: |\Z)"
    r"|remote\..*\.promisor(?:\Z| (?!false|no|off|0\b)\S)"  # a bare key means true
)
_GIT_VERSION = re.compile(r"git version ([0-9]+)\.([0-9]+)\.([0-9]+)", re.ASCII)


def refuse_lazy_fetch(root: Path) -> None:
    """Refuse a partial clone on a git that may fetch, so ``scan`` never reaches the network."""
    keys = r"^(extensions\.partialclone|remote\..*\.(promisor|partialclonefilter))$"
    config = git_text(root, "config", "--get-regexp", keys, ok=(0, 1)).stdout.lower()
    found = _GIT_VERSION.match(git_text(root, "version").stdout)
    major, minor, patch = (int(part) for part in found.groups()) if found else (0, 0, 0)
    floor = _NO_LAZY_FETCH_BACKPORTS.get((major, minor))
    honored = (major, minor, patch) >= _NO_LAZY_FETCH_GIT or (floor is not None and patch >= floor)
    if not honored and any(_PROMISOR.match(line) for line in config.splitlines()):
        raise ConfigError(
            "a partial clone on a git without GIT_NO_LAZY_FETCH (before 2.45.1 or its May 2024"
            " backports) may fetch a missing commit; upgrade git or scan a full clone"
        )


def is_shallow(root: Path) -> bool:
    """True for a shallow clone: history older than its boundary was never fetched."""
    return git_text(root, "rev-parse", "--is-shallow-repository").stdout.strip() == "true"


def read_commits(
    root: Path, sha: str, max_commits: int, since: str | None = None, dropped: Drops | None = None
) -> tuple[list[CommitRecord], bool]:
    """Read up to ``max_commits`` commits from ``sha``. The flag is True when more exist."""
    batches, truncated = _record_batches(root, sha, max_commits, since, dropped)
    return [record for batch in batches for record in batch], truncated


def _record_batches(
    root: Path, sha: str, max_commits: int, since: str | None, dropped: Drops | None
) -> tuple[Iterator[list[CommitRecord]], bool]:
    """Commit batches, each read when asked for, and the truncation flag. Sizes come first: no
    batch tops ``MAX_BATCH_BYTES``; a commit over ``MAX_COMMIT_BYTES`` is counted, not read."""
    shas = rev_list(root, sha, max_commits + 1, since)
    kept = shas[:max_commits]
    batches = _batches(kept, _sizes(root, kept), {} if dropped is None else dropped)
    return (_read_batch(root, batch) for batch in batches), len(shas) > max_commits

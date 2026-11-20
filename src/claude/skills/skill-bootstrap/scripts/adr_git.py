# Git access for the ADR backfill CLI, standard library only.
# The commit reader replaces the delimited-text reader of aligndottech/align-cli
# src/lib/git.ts (commit 8d758e9899677b61442b08ffda74b74887bfc42a); see adr_commits.py.
# MIT, Copyright (c) 2026 Align Tech Ltd, see LICENSE-align
"""Run git with a timeout and read commits without trusting message text.

Commits are read in two steps. ``git rev-list`` gives the SHAs in history order. Those
SHAs go to ``git cat-file --batch``, whose reply is size-prefixed
(``<sha> commit <size>`` then exactly ``size`` bytes), so a commit message cannot add
or hide a record. Every reply must name the SHA that was asked for, in order, with the
type ``commit``. Anything else raises ``GitError``; the reader never resynchronizes.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from adr_commits import CommitRecord, parse_commit_object

__all__ = [
    "GIT_TIMEOUT_S",
    "ConfigError",
    "GitError",
    "git_bytes",
    "git_text",
    "origin_web_base",
    "read_commits",
    "repo_root",
    "resolve_rev",
    "rev_list",
    "web_base",
]

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

#!/usr/bin/env python3
"""Bind analysis findings to a verified live default-branch commit (issue #5634).

RCA and review work can run from a stale checkout after the default branch
advanced. A defect fixed upstream then reads as current, and an agent opens
duplicate work. This helper records the live default-branch SHA next to the
local HEAD and classifies the findings that depend on repository state.

Run it at analysis start and again right before creating an issue or applying a
fix. Pass the live SHA from the earlier run as ``--since`` on the second call:
a default branch that moved in between is reported, not hidden.

The record is one JSON object on stdout:

    remote, branch     where the live SHA was read
    live_sha           default-branch tip, read from the remote now
    local_head         HEAD of the checkout under analysis
    retrieved_at       UTC timestamp of the remote read
    status             equal | behind | ahead | diverged | unverified
    grounded_sha       revision the findings were read at (--since, else local_head)
    live_changed       true when --since differs from live_sha, else null
    finding_status     CURRENT | STALE | UNVERIFIED
    citations          one row per --cite and compared revision, each CURRENT/STALE/UNVERIFIED
    reason             one sentence explaining finding_status

``finding_status`` is CURRENT only when local HEAD and the grounded revision are
both the live revision, or when every cited file and line range is
byte-identical between each differing revision and live (an explicit
revalidation). A differing revision with no citation to revalidate is
UNVERIFIED, never CURRENT. ``--since`` equal to live does not vouch for a
checkout that is behind. A STALE or UNVERIFIED
finding must not be the sole basis for an issue.

Exit codes follow ADR-035:
    0 - Record emitted (``--require-current`` unset, or finding_status CURRENT)
    1 - ``--require-current`` set and finding_status is not CURRENT
    2 - Configuration error: not a git repo, bad ``--cite``, unknown branch
    3 - External: the remote read, or the fetch of the live commit, failed
    4 - Auth error reading the remote

Usage:
    python scripts/validation/live_revision_grounding.py
    python scripts/validation/live_revision_grounding.py --since <earlier-live-sha> \\
        --cite <file>:10-20 --cite <other-file> --require-current
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
# subprocess_runner imports ``scripts.cli_exec`` (absolute), so the repo root
# must be importable when this file runs as a plain script.
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.validation.subprocess_runner import _run_subprocess  # noqa: E402

CURRENT = "CURRENT"
STALE = "STALE"
UNVERIFIED = "UNVERIFIED"

_TIMEOUT_SECONDS = 60
_AUTH_HINTS = (
    "authentication failed",
    "could not read username",
    "permission denied",
    "unauthorized",
)
_CITE = re.compile(r"^(?P<path>[^:].*?)(?::(?P<start>\d+)(?:-(?P<end>\d+))?)?$")
_SYMREF_PREFIX = "ref: refs/heads/"
_SHA = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")


class GroundingError(RuntimeError):
    """A step failed in a way that maps to a documented exit code."""

    def __init__(self, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@dataclass(frozen=True, slots=True)
class Citation:
    """A file, optionally narrowed to a one-based inclusive line range."""

    path: str
    start: int | None = None
    end: int | None = None

    @property
    def label(self) -> str:
        if self.start is None:
            return self.path
        if self.end is None or self.end == self.start:
            return f"{self.path}:{self.start}"
        return f"{self.path}:{self.start}-{self.end}"


@dataclass(slots=True)
class Record:
    """The grounding record. ``to_dict`` is the JSON contract."""

    remote: str
    branch: str | None = None
    live_sha: str | None = None
    local_head: str | None = None
    retrieved_at: str = ""
    status: str = "unverified"
    grounded_sha: str | None = None
    live_changed: bool | None = None
    finding_status: str = UNVERIFIED
    citations: list[dict[str, str]] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in self.__slots__}


def parse_citation(text: str) -> Citation:
    """Parse ``path``, ``path:N`` or ``path:N-M`` into a Citation."""
    match = _CITE.match(text.strip())
    if not match or not match.group("path"):
        raise GroundingError(f"Invalid --cite value: {text!r}", 2)
    start = match.group("start")
    end = match.group("end")
    first = int(start) if start else None
    last = int(end) if end else first
    if first is not None and (first < 1 or (last is not None and last < first)):
        raise GroundingError(f"Invalid line range in --cite: {text!r}", 2)
    return Citation(match.group("path"), first, last)


def validate_inputs(remote: str, since: str | None) -> None:
    """Reject values git would read as options, and a malformed ``--since``."""
    if not remote or remote.startswith("-"):
        raise GroundingError(f"Invalid --remote value: {remote!r}", 2)
    if since is not None and not _SHA.match(since):
        raise GroundingError(f"--since must be a full 40 or 64 hex-digit SHA: {since!r}", 2)


def _git(repo: Path, args: list[str]) -> tuple[int, str, str]:
    return _run_subprocess(["git", "-C", str(repo), *args], timeout=_TIMEOUT_SECONDS)


def _remote_failure(stderr: str) -> GroundingError:
    detail = stderr.strip() or "git exited non-zero"
    lowered = detail.lower()
    code = 4 if any(hint in lowered for hint in _AUTH_HINTS) else 3
    return GroundingError(f"Remote read failed: {detail}", code)


def local_head(repo: Path) -> str:
    """Return the full SHA of HEAD, or raise exit 2 outside a git repo."""
    code, out, err = _git(repo, ["rev-parse", "--verify", "HEAD^{commit}"])
    if code != 0:
        raise GroundingError(f"Cannot resolve HEAD in {repo}: {err.strip()}", 2)
    return out.strip()


def _parse_ls_remote(stdout: str) -> tuple[str | None, str | None]:
    """Return (default branch, SHA) from ``ls-remote --symref remote HEAD``."""
    branch = None
    sha = None
    for line in stdout.splitlines():
        target, _sep, ref = line.partition("\t")
        if ref != "HEAD":
            continue
        if target.startswith(_SYMREF_PREFIX):
            branch = target.removeprefix(_SYMREF_PREFIX)
        else:
            sha = target
    return branch, sha


def live_default_branch(repo: Path, remote: str) -> tuple[str, str]:
    """Return (default branch, live SHA) as the remote reports them now."""
    code, out, err = _git(repo, ["ls-remote", "--symref", remote, "HEAD"])
    if code != 0:
        raise _remote_failure(err)
    branch, sha = _parse_ls_remote(out)
    if not branch or not sha:
        raise GroundingError(f"Remote {remote!r} reported no default branch", 3)
    return branch, sha


def live_branch_sha(repo: Path, remote: str, branch: str) -> str:
    """Return the live SHA of a named branch, or raise exit 2 when absent."""
    code, out, err = _git(repo, ["ls-remote", remote, f"refs/heads/{branch}"])
    if code != 0:
        raise _remote_failure(err)
    parts = out.split()
    if not parts:
        raise GroundingError(f"Branch {branch!r} does not exist on {remote!r}", 2)
    return parts[0]


def ensure_commit(repo: Path, remote: str, sha: str) -> None:
    """Make ``sha`` resolvable locally, fetching its objects when absent.

    ``--no-write-fetch-head`` and the bare SHA refspec download objects without
    moving any ref, so the checkout under analysis does not change.
    """
    if _git(repo, ["cat-file", "-e", f"{sha}^{{commit}}"])[0] == 0:
        return
    code, _out, err = _git(
        repo, ["fetch", "--quiet", "--no-tags", "--no-write-fetch-head", remote, sha]
    )
    if code != 0:
        raise _remote_failure(err)


def _is_ancestor(repo: Path, older: str, newer: str) -> bool:
    return _git(repo, ["merge-base", "--is-ancestor", older, newer])[0] == 0


def relation(repo: Path, head: str, live: str) -> str:
    """Classify local HEAD against the live SHA. Both must resolve locally."""
    if head == live:
        return "equal"
    if _is_ancestor(repo, head, live):
        return "behind"
    if _is_ancestor(repo, live, head):
        return "ahead"
    return "diverged"


def _file_lines(repo: Path, sha: str, path: str) -> list[str] | None:
    """Return the LF-split lines of ``path`` at ``sha``, or None when absent."""
    code, out, _err = _git(repo, ["show", f"{sha}:{path}"])
    if code != 0:
        return None
    lines = out.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def _slice(lines: list[str], cite: Citation) -> list[str]:
    if cite.start is None:
        return lines
    return lines[cite.start - 1 : cite.end]


def _range_note(before: list[str], after: list[str], cite: Citation) -> tuple[bool, str]:
    """Return (unreadable, note) for a line range against both revisions.

    A range that starts past the end of either file cites lines that do not
    exist there, so it cannot be revalidated. A range that only ends past the
    end is clamped, and the note says so.
    """
    if cite.start is None:
        return False, ""
    shortest = min(len(before), len(after))
    if cite.start > shortest:
        return (
            True,
            f"cited range starts past the end of the file (shortest revision has {shortest} lines)",
        )
    if cite.end is not None and cite.end > shortest:
        return False, f"; range end clamped to line {shortest}"
    return False, ""


def classify_citation(repo: Path, grounded: str, live: str, cite: Citation) -> tuple[str, str]:
    """Return (status, detail) for one citation between two revisions."""
    before = _file_lines(repo, grounded, cite.path)
    after = _file_lines(repo, live, cite.path)
    if before is None and after is None:
        return UNVERIFIED, "path absent at both revisions"
    if before is None or after is None:
        side = "live revision" if after is None else "grounded revision"
        return STALE, f"path absent at {side}"
    unreadable, note = _range_note(before, after, cite)
    if unreadable:
        return UNVERIFIED, note
    if _slice(before, cite) == _slice(after, cite):
        return CURRENT, "cited content identical at both revisions" + note
    return STALE, "cited content changed between the revisions"


def _revalidate(
    repo: Path, revisions: list[str], live: str, cites: list[Citation]
) -> tuple[list[dict[str, str]], str, str]:
    """Return (rows, finding_status, reason) for revisions that differ from live."""
    if not cites:
        return (
            [],
            UNVERIFIED,
            "The checkout or grounded revision differs from live and no --cite was revalidated.",
        )
    rows = []
    for revision in revisions:
        for cite in cites:
            status, detail = classify_citation(repo, revision, live, cite)
            rows.append(
                {"citation": cite.label, "revision": revision, "status": status, "detail": detail}
            )
    statuses = {row["status"] for row in rows}
    if STALE in statuses:
        return rows, STALE, "A cited file or line range changed since the compared revision."
    if UNVERIFIED in statuses:
        return rows, UNVERIFIED, "A citation could not be read at both revisions."
    return rows, CURRENT, "Every citation is identical at each compared revision and live."


def ground(
    repo: Path,
    remote: str,
    branch: str | None,
    since: str | None,
    cites: list[Citation],
    record: Record,
) -> None:
    """Fill ``record`` in place. Raises GroundingError after partial fill."""
    record.local_head = local_head(repo)
    if branch is None:
        record.branch, record.live_sha = live_default_branch(repo, remote)
    else:
        record.branch = branch
        record.live_sha = live_branch_sha(repo, remote, branch)
    record.retrieved_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    live = record.live_sha
    grounded = since or record.local_head
    record.grounded_sha = grounded
    record.live_changed = None if since is None else since != live
    ensure_commit(repo, remote, live)
    record.status = relation(repo, record.local_head, live)
    # The findings were read from the checkout, so local HEAD must match live
    # (or revalidate) even when --since equals live. --since adds the earlier
    # live revision to the comparison; it never replaces local HEAD.
    behind_live = [rev for rev in dict.fromkeys((record.local_head, grounded)) if rev != live]
    if not behind_live:
        record.finding_status = CURRENT
        record.reason = "Local HEAD and the grounded revision are the live revision."
        return
    for revision in behind_live:
        if revision != record.local_head:
            ensure_commit(repo, remote, revision)
    rows, record.finding_status, record.reason = _revalidate(repo, behind_live, live, cites)
    record.citations = rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo", default=".", help="checkout under analysis (default: .)")
    parser.add_argument("--remote", default="origin", help="remote to read (default: origin)")
    parser.add_argument("--branch", help="branch to read (default: the remote's default branch)")
    parser.add_argument("--since", help="live SHA recorded by an earlier run of this helper")
    parser.add_argument(
        "--cite",
        action="append",
        default=[],
        metavar="PATH[:N[-M]]",
        help="file or line range a finding cites; repeatable",
    )
    parser.add_argument(
        "--require-current",
        action="store_true",
        help="exit 1 unless finding_status is CURRENT",
    )
    return parser


def run(args: argparse.Namespace) -> tuple[Record, int]:
    """Execute one grounding pass and return (record, exit code)."""
    record = Record(remote=args.remote)
    try:
        validate_inputs(args.remote, args.since)
        cites = [parse_citation(text) for text in args.cite]
        ground(Path(args.repo), args.remote, args.branch, args.since, cites, record)
    except GroundingError as error:
        record.status = "unverified"
        record.finding_status = UNVERIFIED
        record.reason = str(error)
        print(f"[live-revision-grounding] {error}", file=sys.stderr)
        return record, error.exit_code
    if args.require_current and record.finding_status != CURRENT:
        print(
            f"[live-revision-grounding] finding_status is {record.finding_status}: {record.reason}",
            file=sys.stderr,
        )
        return record, 1
    return record, 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    record, code = run(args)
    print(json.dumps(record.to_dict(), indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())

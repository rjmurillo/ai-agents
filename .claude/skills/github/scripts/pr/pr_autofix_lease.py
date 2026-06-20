#!/usr/bin/env python3
"""PR-autofix branch-ownership lease, local-only (ADR-076 Phase 1).

The pr-autofix workflow fixes review feedback on open PRs. A remote
automated review/autofix routine (CodeRabbit autofix, a CI workflow, a
sibling agent) can commit to the same PR branch while a local pr-autofix
session has staged but unpushed work. The Force-Push Safety SHA gate
(`.claude/commands/pr-autofix.md`) prevents the dangerous overwrite, but
only at push time, after the duplicate fix work is already done and a
conflict is already likely.

This module is the advisory, fail-open coordination lease that ADR-076
adopts to resolve the common collision *before* the fix work: a second
loop sees a live lease and SKIPs or waits instead of racing to push.

Phase 1 scope (this module): ship `acquire` / `release` / `status`
helpers and wire them into local pr-autofix only. Remote loops do not
participate yet (Phase 2, gated on a BOT_PAT permissions audit); a
non-participating remote loop is exactly today's behavior, so Phase 1 is
safe to ship before any remote integration exists. This module
implements no remote coordination.

Storage (ADR-076 part 1): the lease lives in hidden-marker comments on
the PR timeline (the issue-comment stream). The latest
`<!-- PR-AUTOFIX-LEASE -->` marker comment wins. This is NOT a
worktree-local file: ADR-076 explicitly rejects the git-notes/local
alternative because it is "not in the PR timeline (fails acceptance
criterion 3)". A live lease is one whose `owner` is not `none`, whose
`expires_at` is in the future relative to the READER's clock, AND whose
`expires_at` does not exceed reader-now + MAX_TTL; in all other cases
(expired, tombstoned, absent, beyond-MAX_TTL, malformed) the lock is free.

The lease is advisory. The Force-Push Safety SHA gate remains the only
hard safety boundary and is never replaced or relaxed by this module.

Exit codes (within the ADR-035 range, matching `check_pr_live_state.py`'s
ACT/SKIP convention):
    0 - ACT: caller may proceed (lease acquired, renewed, or released)
    1 - SKIP: a live lease is held by another loop (acquire only)
    2 - PR not found / usage error
    3 - External error (API failure)
    4 - Auth error

Stricter/looser/different than canonical
========================================
Canonical sibling: `check_pr_live_state.py` (sibling in this pr/ directory).
That probe returns ``{"action": "ACT" | "SKIP", "reason": ...}`` and exits
``0`` on ACT / ``1`` on SKIP. This module mirrors that verdict shape and
ACT/SKIP exit convention.

Exit-code provenance (verified 2026-06-19 against the canonical files).
The exit-1 = SKIP meaning is NOT from ADR-035. ADR-035
(ADR-035 (exit-code standardization), the chosen
option's table) defines exit 1 as "General error / Validation failure"
(logic) and exit 2 as "Usage/configuration error". The 1 = SKIP meaning
is `check_pr_live_state.py`'s own docstring convention (exit 0 = ACT,
exit 1 = SKIP), which itself overloads ADR-035's exit 1. This module
mirrors that sibling convention. **Different than canonical:** ADR-035
exit 1 = logic is overloaded here to exit 1 = SKIP. PR-not-found / usage
errors use exit 2, external API errors exit 3, auth exit 4, per ADR-035.

Storage divergence (verified 2026-06-19): `check_pr_live_state.py` reads
only PR state fields via GraphQL (the ``_LIVE_STATE_QUERY``: ``state``,
``merged``, ``isDraft``, ``closed``, ``headRefName``, ``baseRefName``)
plus ``git cherry``; it reads ZERO comments. This module adds a NEW
comment-timeline read path; it does not reuse that probe's store. The
reuse is the ACT/SKIP gate *pattern*, not a shared store (ADR-076 part 1).

Fail-open difference, by design (ADR-076 part 3, step 6): on a lease-store
read/write failure this module FAILS OPEN to ACT (exit 0) with reason
``lease-store-unavailable`` rather than surfacing the API error as exit 3.
The SHA gate is the backstop, so a store outage must degrade to today's
behavior, never to a workflow outage. A genuine PR-not-found or auth
failure still exits 2 / 4.

Security (ADR-076 Security section): the lease comment is untrusted input
read from the PR timeline. Three hardening controls bound forgery:

1. ``parse_lease_block`` is strict and anchored; a malformed marker is
   treated as "no live lease" and never executed (CWE-78 / CWE-502).
2. ``MAX_TTL`` is enforced against the READER's clock, not the forgeable
   body ``acquired_at``. ``Lease.is_live(now)`` requires
   ``now < expires_at <= now + MAX_TTL``. A marker whose ``expires_at``
   lands beyond ``now + MAX_TTL`` (a far-future forgery that would pass a
   body-relative ``expires_at <= acquired_at + MAX_TTL`` check yet read as
   live indefinitely) is treated as "no live lease", so forgery DoS is
   bounded to one TTL from the read instant (CWE-400 / CWE-367). The
   parser still rejects internally-inconsistent markers whose
   ``expires_at > acquired_at + MAX_TTL``.
3. Self-renewal keys on the VERIFIED GitHub comment author
   (``user.login`` from the API), never on the forgeable body ``owner`` /
   ``session`` strings (CWE-345). The body fields are display/traceability
   only; a forged body can at most appear as a *foreign* live lease (a
   bounded self-DoS), never as this loop's own renewable lease.

The timeline scan is bounded to the latest ``MAX_SCAN`` comments so a
flood of forged markers cannot become an unbounded parse-cost DoS
(CWE-400). ``check_pr_live_state.py`` scans no comments, so this bound is
a NEW control this module adds, not a value inherited from that probe.
The lease is never an authorization; only the SHA gate gates a push.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Plugin-root resolution: matches sibling scripts (check_pr_live_state.py,
# post_pr_comment_reply.py). When the script runs inside a deployed Claude
# plugin, CLAUDE_PLUGIN_ROOT points at the plugin's installed path; when it
# runs inside the repo (the case under test), we walk up to the lib root.
# ---------------------------------------------------------------------------
_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
_workspace = os.environ.get("GITHUB_WORKSPACE")
if _plugin_root:
    _lib_dir = os.path.join(_plugin_root, "lib")
elif _workspace:
    _claude_dir = os.path.join(_workspace, ".claude")
    _lib_dir = os.path.join(_claude_dir, "lib")
else:
    _lib_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "lib")
    )
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
    sys.exit(2)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (  # noqa: E402
    assert_gh_authenticated,
    resolve_repo_params,
    safe_log_str,
)
from github_core.output import (  # noqa: E402
    add_output_format_arg,
    write_skill_error,
    write_skill_output,
)

_SCRIPT_NAME = "pr_autofix_lease.py"

# ---------------------------------------------------------------------------
# Lease contract (ADR-076 parts 1, 2, 4). Constants are fixed by the ADR,
# not tunables, so every implementer reads the same protocol.
# ---------------------------------------------------------------------------

#: Hidden marker that makes every lease comment findable in one timeline scan
#: (ADR-076 part 1). Quoted verbatim from the ADR.
LEASE_MARKER = "<!-- PR-AUTOFIX-LEASE -->"

#: Fixed lease lifetime (ADR-076 part 2: "The lease TTL is 15 minutes.").
TTL = timedelta(minutes=15)

#: Upper bound on lease liveness (ADR-076 Security). Enforced TWICE:
#: (1) ``parse_lease_block`` rejects an internally-inconsistent marker whose
#: ``expires_at > acquired_at + MAX_TTL``; (2) ``Lease.is_live`` enforces it
#: against the READER's clock (``expires_at <= now + MAX_TTL``), which is the
#: check that defeats a far-future forgery whose own timestamps are internally
#: consistent. Equal to TTL: a well-formed self-renewal sets
#: ``expires_at = acquired_at + TTL``, so any longer window is forged or corrupt.
MAX_TTL = TTL

#: Upper bound on the number of timeline comments scanned per acquire/status
#: (ADR-076 Security / part 3). A PR flooded with forged ``<!-- PR-AUTOFIX-LEASE
#: -->`` comments cannot turn the scan into an unbounded parse-cost DoS
#: (CWE-400). The latest MAX_SCAN comments are inspected; older ones cannot hold
#: a live lease anyway (TTL is 15 minutes). This is a NEW control; the canonical
#: sibling ``check_pr_live_state.py`` scans no comments at all.
MAX_SCAN = 100

#: Fixed vocabulary of automation identities (ADR-076 part 4). A human reading
#: the timeline sees which automation holds the branch. ``none`` is the
#: tombstone owner written by release.
KNOWN_OWNERS = frozenset(
    {
        "local:pr-autofix",
        "remote:coderabbit-autofix",
        "ci:autofix-workflow",
        "none",
    }
)

#: Owner value of a released (tombstoned) lease.
TOMBSTONE_OWNER = "none"

#: Anchored RFC3339-UTC pattern. ADR-076 stores acquired_at / expires_at as
#: "RFC3339-UTC". We accept the ``...Z`` zulu form the writer below emits.
_RFC3339_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")

#: 40-hex git SHA (ADR-076 part 1: ``base_sha: <40-hex>``).
_SHA40 = re.compile(r"^[0-9a-f]{40}$")

#: Per-key strict line patterns. The block is parsed key-by-key; anything that
#: does not match every required key with a valid value is malformed and
#: treated as "no live lease".
_KEY_LINE = re.compile(r"^([a-z_]+):\s*(.+?)\s*$")

_REQUIRED_KEYS = ("owner", "session", "acquired_at", "expires_at", "base_sha")


# ---------------------------------------------------------------------------
# Value type
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Lease:
    """A parsed, validated lease marker.

    Construction implies validity: ``parse_lease_block`` returns ``None``
    rather than an invalid ``Lease``. ``owner == "none"`` is a tombstone.

    ``owner`` and ``session`` come from the (forgeable) comment body and are
    display/traceability only. ``author`` is the VERIFIED GitHub comment
    author (``user.login`` from the API), the credential that actually
    posted the comment; it is the only field a trust decision keys on
    (ADR-076 part 4, Security). ``parse_lease_block`` cannot know the
    author from the body alone, so it leaves ``author=""``;
    ``select_authoritative_lease`` stamps the verified author from the
    enclosing comment.
    """

    owner: str
    session: str
    acquired_at: datetime
    expires_at: datetime
    base_sha: str
    author: str = ""

    def is_live(self, now: datetime) -> bool:
        """A lease is live, judged against the READER's clock ``now``.

        Live requires three conditions (ADR-076 Security):
        1. not a tombstone (``owner != "none"``),
        2. not expired (``expires_at > now``),
        3. not over-extended past the reader's clock
           (``expires_at <= now + MAX_TTL``).

        Condition 3 is the forgery bound: a marker whose ``expires_at`` is
        far in the future (even one whose body timestamps are internally
        consistent and so passed ``parse_lease_block``) reads as "no live
        lease", capping any forged lease to one TTL of liveness from the
        instant it is read (CWE-400 / CWE-367).
        """
        if self.owner == TOMBSTONE_OWNER:
            return False
        return now < self.expires_at <= now + MAX_TTL


# ---------------------------------------------------------------------------
# Pure core: parsing, selection, classification (no network)
# ---------------------------------------------------------------------------


def _parse_rfc3339_utc(value: str) -> datetime | None:
    """Parse a strict RFC3339-UTC ``...Z`` timestamp, or return None.

    Anchored to the zulu form to keep the parser strict (ADR-076 Security:
    "parsed with a strict, anchored format"). Returns a timezone-aware
    UTC datetime.
    """
    if not _RFC3339_UTC.match(value):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_lease_block(body: str) -> Lease | None:
    """Parse a single lease comment body into a ``Lease``, or ``None``.

    Strict and anchored (ADR-076 Security). A body that lacks the marker,
    is missing a required key, carries an unknown ``owner``, a non-RFC3339
    timestamp, a non-40-hex ``base_sha``, or whose ``expires_at`` exceeds
    ``acquired_at + MAX_TTL`` is malformed and returns ``None``. The caller
    treats ``None`` as "no live lease" and fails open to ACT; the body is
    never executed, evaluated, or used to drive a shell command.
    """
    if LEASE_MARKER not in body:
        return None

    fields: dict[str, str] = {}
    for raw in body.splitlines():
        line = raw.strip()
        match = _KEY_LINE.match(line)
        if match is None:
            continue
        key, value = match.group(1), match.group(2)
        if key in _REQUIRED_KEYS:
            fields[key] = value

    if any(key not in fields for key in _REQUIRED_KEYS):
        return None

    owner = fields["owner"]
    if owner not in KNOWN_OWNERS:
        return None

    base_sha = fields["base_sha"]
    if not _SHA40.match(base_sha):
        return None

    acquired_at = _parse_rfc3339_utc(fields["acquired_at"])
    expires_at = _parse_rfc3339_utc(fields["expires_at"])
    if acquired_at is None or expires_at is None:
        return None

    # MAX_TTL enforcement (ADR-076 Security): a forged marker cannot set
    # expires_at arbitrarily far in the future. A tombstone (expires_at in
    # the past) trivially satisfies this and stays parseable so the
    # latest-marker rule can read it directly.
    if expires_at > acquired_at + MAX_TTL:
        return None

    return Lease(
        owner=owner,
        session=fields["session"],
        acquired_at=acquired_at,
        expires_at=expires_at,
        base_sha=base_sha,
    )


def _comment_author(comment: dict) -> str:
    """Return the verified comment author login (``user.login``), or "".

    GitHub's REST issue-comments payload carries the authenticated author
    under ``user.login``. The canonical sibling that reads the same field
    is github_core.api (under the lib root)
    ``get_trusted_source_comments`` (line 668:
    ``c.get("user", {}).get("login") in trusted_users``). A forger cannot
    set this field without the holder's credential, so it is the field
    self-renewal keys on (ADR-076 part 4, Security). ``.get`` is used
    defensively: a malformed payload yields "", which can never match a
    real acting author and so is treated as a foreign lease.
    """
    user = comment.get("user")
    if not isinstance(user, dict):
        return ""
    login = user.get("login")
    return login if isinstance(login, str) else ""


def select_authoritative_lease(comments: list[dict]) -> Lease | None:
    """Return the lease from the most-recent valid marker comment, or None.

    Latest-marker-wins (ADR-076 part 1: "The latest marker comment wins").
    ``comments`` is the PR timeline in API order (oldest first), each a
    dict with at least ``body``, ``created_at``, and ``user.login``. The
    scan is bounded to the latest ``MAX_SCAN`` comments (ADR-076 Security):
    a flood of forged markers cannot become an unbounded parse-cost DoS,
    and an older comment cannot hold a live lease anyway (TTL is 15 min).

    Each selected lease is stamped with its enclosing comment's VERIFIED
    author (``user.login``), so a later trust decision keys on the
    credential that posted the comment, not on the forgeable body
    ``owner`` / ``session``. Marker comments that fail to parse are skipped
    (treated as "no live lease"); the most recent *parseable* marker wins.
    """
    latest: Lease | None = None
    latest_created: str = ""
    for comment in comments[-MAX_SCAN:]:
        body = comment.get("body") or ""
        if LEASE_MARKER not in body:
            continue
        lease = parse_lease_block(body)
        if lease is None:
            continue
        created = comment.get("created_at") or ""
        if latest is None or created >= latest_created:
            latest = replace(lease, author=_comment_author(comment))
            latest_created = created
    return latest


def classify_acquire(
    lease: Lease | None,
    acting_author: str,
    now: datetime,
) -> dict:
    """Decide ACT vs SKIP for an acquire, given the authoritative lease.

    Mirrors ``check_pr_live_state.classify_live_state`` verdict shape
    (ADR-076 part 3, acquire steps 3-5):

    - A live lease whose VERIFIED comment author is not ``acting_author``
      -> SKIP, reason ``held-by:<owner>``, with ``expires_at`` so the
      caller knows when to retry. (``owner`` in the reason is the body's
      display label; the trust decision used ``author``.)
    - A live lease whose verified author IS ``acting_author``
      (self-renewal) -> ACT, reason ``self-renew``. The match keys on the
      verified GitHub comment author, never on the forgeable body
      ``owner`` / ``session`` (ADR-076 Security, CWE-345).
    - No live lease (absent, tombstoned, expired, beyond-MAX_TTL, or
      malformed/None) -> ACT, reason ``free`` (the caller claims it).

    ``acting_author`` is the login of the credential running acquire. An
    empty ``acting_author`` (caller could not resolve its own login) never
    matches a real lease author, so it can only claim a free lock, never
    self-renew a foreign one. This fails safe: at worst the caller posts a
    fresh claim it cannot later self-renew, and the SHA gate still guards
    the push.
    """
    if lease is not None and lease.is_live(now):
        if acting_author != "" and lease.author == acting_author:
            return {"action": "ACT", "reason": "self-renew"}
        return {
            "action": "SKIP",
            "reason": f"held-by:{lease.owner}",
            "expires_at": _to_rfc3339(lease.expires_at),
        }
    return {"action": "ACT", "reason": "free"}


# ---------------------------------------------------------------------------
# Marker rendering
# ---------------------------------------------------------------------------


def _to_rfc3339(value: datetime) -> str:
    """Render a UTC datetime as the strict RFC3339-UTC ``...Z`` form."""
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def render_lease_comment(lease: Lease) -> str:
    """Render a ``Lease`` as a marker comment body (ADR-076 part 1).

    The output round-trips through ``parse_lease_block``.
    """
    return (
        f"{LEASE_MARKER}\n"
        f"owner: {lease.owner}\n"
        f"session: {lease.session}\n"
        f"acquired_at: {_to_rfc3339(lease.acquired_at)}\n"
        f"expires_at: {_to_rfc3339(lease.expires_at)}\n"
        f"base_sha: {lease.base_sha}\n"
    )


def build_claim(owner: str, session: str, base_sha: str, now: datetime) -> Lease:
    """Build a fresh claim lease starting now with a full TTL window."""
    return Lease(
        owner=owner,
        session=session,
        acquired_at=now,
        expires_at=now + TTL,
        base_sha=base_sha,
    )


def build_tombstone(owner: str, session: str, now: datetime) -> Lease:
    """Build a release tombstone (ADR-076 part 1).

    ``owner`` is set to ``none`` and ``expires_at`` to the past so the
    latest-marker rule reads the lock as free on the next scan, without
    relying on the tombstone itself being non-expired.
    """
    past = now - TTL
    return Lease(
        owner=TOMBSTONE_OWNER,
        session=session,
        acquired_at=past,
        expires_at=past,
        base_sha="0" * 40,
    )


# ---------------------------------------------------------------------------
# I/O adapter (fail-open). Kept thin and separate from the pure core so the
# protocol logic is testable without the network (ADR-076 part 3 step 5).
# ---------------------------------------------------------------------------


class LeaseStoreError(RuntimeError):
    """Raised by the I/O adapter when the lease store is unreachable.

    Callers translate this to a fail-open ACT (ADR-076 part 3 step 5), not
    to an exit-3 external error.
    """


def _git_head_sha() -> str | None:
    """Return the local HEAD SHA, or None if git is unavailable.

    The acquire path records ``base_sha`` so the push-time guard (Phase 2
    integration) can detect a remote advance under the lease. Phase 1 only
    records it; it never gates a push on it (the SHA gate does that).
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        logger.warning("op=lease_head_sha_failed err=%s", safe_log_str(str(exc)))
        return None
    if result.returncode != 0:
        return None
    sha = (result.stdout or "").strip()
    return sha if _SHA40.match(sha) else None


def _gh_authenticated_login() -> str:
    """Return the authenticated GitHub login, or "" if it cannot resolve.

    This is the credential that will POST the lease comment, so it is the
    ``author`` that ``select_authoritative_lease`` will later read back
    from ``user.login`` for self-renewal (ADR-076 part 4). Resolved via
    ``gh api user --jq .login``.

    On any failure (gh missing, network error, non-zero exit, empty body)
    this returns "" and acquire degrades to claim-only: it can take a free
    lock but will not self-renew a foreign one. That fails safe; the SHA
    gate still guards the push.
    """
    try:
        result = subprocess.run(
            ["gh", "api", "user", "--jq", ".login"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        logger.warning("op=lease_login_failed err=%s", safe_log_str(str(exc)))
        return ""
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


def _gh_comment_endpoint(owner: str, repo: str, pr: int) -> str:
    return f"repos/{owner}/{repo}/issues/{pr}/comments"


def _parse_paginated_json_arrays(raw_stdout: str) -> list[dict]:
    """Parse one or more JSON array documents emitted by ``gh api --paginate``."""
    raw = raw_stdout.strip()
    if not raw:
        return []
    decoder = json.JSONDecoder()
    comments: list[dict] = []
    pos = 0
    while pos < len(raw):
        while pos < len(raw) and raw[pos].isspace():
            pos += 1
        if pos >= len(raw):
            break
        payload, pos = decoder.raw_decode(raw, pos)
        if payload is None:
            continue
        if not isinstance(payload, list):
            raise LeaseStoreError("comment list returned non-list JSON payload")
        comments.extend(item for item in payload if isinstance(item, dict))
    return comments


def list_lease_comments(owner: str, repo: str, pr: int) -> list[dict]:
    """Return PR issue comments (oldest first). Raises LeaseStoreError.

    Wraps ``gh api`` paginated read. A non-zero exit or malformed JSON is a
    store failure, surfaced as ``LeaseStoreError`` so the caller fails open.
    """
    endpoint = _gh_comment_endpoint(owner, repo, pr) + "?per_page=100"
    try:
        result = subprocess.run(
            ["gh", "api", "--paginate", endpoint],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise LeaseStoreError(f"comment list failed: {exc}") from exc
    if result.returncode != 0:
        raise LeaseStoreError(
            f"comment list exited {result.returncode}: {safe_log_str((result.stderr or '')[:200])}"
        )
    try:
        parsed = _parse_paginated_json_arrays(result.stdout or "")
    except (json.JSONDecodeError, ValueError, LeaseStoreError) as exc:
        raise LeaseStoreError(f"comment list returned non-JSON: {exc}") from exc
    return parsed


def post_lease_comment(owner: str, repo: str, pr: int, body: str) -> None:
    """Post a new marker comment. Raises LeaseStoreError on failure."""
    endpoint = _gh_comment_endpoint(owner, repo, pr)
    try:
        result = subprocess.run(
            ["gh", "api", "--method", "POST", endpoint, "-f", f"body={body}"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise LeaseStoreError(f"comment post failed: {exc}") from exc
    if result.returncode != 0:
        raise LeaseStoreError(
            f"comment post exited {result.returncode}: {safe_log_str((result.stderr or '')[:200])}"
        )


# ---------------------------------------------------------------------------
# Use cases: acquire / release / status. Each loads the authoritative lease,
# classifies, and (for acquire/release) writes a marker, failing open on any
# store error.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LeaseResult:
    """Outcome of a lease operation. ``action`` is ACT or SKIP."""

    action: str
    reason: str
    expires_at: str | None = None
    base_sha: str | None = None


def acquire(
    owner: str,
    session: str,
    repo_owner: str,
    repo: str,
    pr: int,
    now: datetime | None = None,
    acting_author: str | None = None,
) -> LeaseResult:
    """Acquire (or self-renew) the lease for ``pr`` (ADR-076 part 3 acquire).

    Returns ACT when the caller may proceed (free lock, or self-renewal),
    SKIP when another live lease holds the branch. Fails open to ACT with
    reason ``lease-store-unavailable`` on any store error (step 6).

    Self-renewal keys on ``acting_author``: the VERIFIED login of the
    credential running acquire, matched against the verified author of the
    authoritative lease comment, never against the forgeable body
    ``owner`` / ``session`` (ADR-076 Security, CWE-345). ``acting_author``
    is injectable for deterministic tests; production passes None and the
    authenticated ``gh`` login is resolved. An unresolved login ("") can
    only claim a free lock, never self-renew a foreign one (fails safe).

    ``now`` is injectable for deterministic tests; production passes None
    and the current UTC instant is used.
    """
    now = now or datetime.now(UTC)
    author = _gh_authenticated_login() if acting_author is None else acting_author
    base_sha = _git_head_sha() or ("0" * 40)
    try:
        comments = list_lease_comments(repo_owner, repo, pr)
    except LeaseStoreError as exc:
        logger.warning("op=lease_acquire_failopen pr=%d err=%s", pr, safe_log_str(str(exc)))
        return LeaseResult("ACT", "lease-store-unavailable", base_sha=base_sha)

    current = select_authoritative_lease(comments)
    verdict = classify_acquire(current, author, now)
    if verdict["action"] == "SKIP":
        return LeaseResult("SKIP", verdict["reason"], expires_at=verdict.get("expires_at"))

    claim = build_claim(owner, session, base_sha, now)
    try:
        post_lease_comment(repo_owner, repo, pr, render_lease_comment(claim))
    except LeaseStoreError as exc:
        logger.warning("op=lease_claim_failopen pr=%d err=%s", pr, safe_log_str(str(exc)))
        return LeaseResult("ACT", "lease-store-unavailable", base_sha=base_sha)
    return LeaseResult(
        "ACT", verdict["reason"], expires_at=_to_rfc3339(claim.expires_at), base_sha=base_sha
    )


def release(
    owner: str,
    session: str,
    repo_owner: str,
    repo: str,
    pr: int,
    now: datetime | None = None,
) -> LeaseResult:
    """Release the lease for ``pr`` by writing a tombstone (ADR-076 part 3).

    Best-effort and idempotent: releasing an already-free lock writes a
    tombstone and still returns ACT, and a store error fails open to ACT
    (a missed release is covered by TTL expiry). ``now`` is injectable for
    deterministic tests.
    """
    now = now or datetime.now(UTC)
    tombstone = build_tombstone(owner, session, now)
    try:
        post_lease_comment(repo_owner, repo, pr, render_lease_comment(tombstone))
    except LeaseStoreError as exc:
        logger.warning("op=lease_release_failopen pr=%d err=%s", pr, safe_log_str(str(exc)))
        return LeaseResult("ACT", "lease-store-unavailable")
    return LeaseResult("ACT", "released")


def status(repo_owner: str, repo: str, pr: int, now: datetime | None = None) -> LeaseResult:
    """Report the current lease state for ``pr`` without writing.

    Returns SKIP with ``held-by:<owner>`` when a live lease is held,
    ACT/``free`` otherwise. Fails open to ACT on store error. ``now`` is
    injectable for deterministic tests.
    """
    now = now or datetime.now(UTC)
    try:
        comments = list_lease_comments(repo_owner, repo, pr)
    except LeaseStoreError as exc:
        logger.warning("op=lease_status_failopen pr=%d err=%s", pr, safe_log_str(str(exc)))
        return LeaseResult("ACT", "lease-store-unavailable")
    current = select_authoritative_lease(comments)
    if current is not None and current.is_live(now):
        return LeaseResult(
            "SKIP", f"held-by:{current.owner}", expires_at=_to_rfc3339(current.expires_at)
        )
    return LeaseResult("ACT", "free")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "PR-autofix branch-ownership lease (ADR-076 Phase 1, local-only). "
            "Advisory coordination over the PR timeline; the Force-Push Safety "
            "SHA gate remains the only hard safety boundary."
        ),
    )
    parser.add_argument("command", choices=["acquire", "release", "status"], help="Lease operation")
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument("--pull-request", type=int, required=True, help="Pull request number")
    parser.add_argument(
        "--lease-owner",
        default="local:pr-autofix",
        choices=sorted(KNOWN_OWNERS - {TOMBSTONE_OWNER}),
        help="Automation identity acquiring the lease (ADR-076 part 4)",
    )
    parser.add_argument(
        "--session",
        default="",
        help="Holder session id (e.g. session-2587). Required for acquire/release.",
    )
    add_output_format_arg(parser)
    return parser


def _emit_error(message: str, code: int, error_type: str, output_format: str, pr: int) -> None:
    write_skill_error(
        message,
        code,
        error_type=error_type,
        output_format=output_format,
        script_name=_SCRIPT_NAME,
        extra={"pull_request": pr},
    )
    raise SystemExit(code)


def _run_command(args: argparse.Namespace, owner: str, repo: str) -> LeaseResult:
    if args.command == "status":
        return status(owner, repo, args.pull_request)
    if not args.session:
        _emit_error(
            f"--session is required for '{args.command}'",
            2,
            "InvalidParams",
            args.output_format,
            args.pull_request,
        )
    if args.command == "acquire":
        return acquire(args.lease_owner, args.session, owner, repo, args.pull_request)
    return release(args.lease_owner, args.session, owner, repo, args.pull_request)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_format = args.output_format
    assert_gh_authenticated()

    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo

    result = _run_command(args, owner, repo)

    output = {
        "success": True,
        "pull_request": args.pull_request,
        "owner": owner,
        "repo": repo,
        "command": args.command,
        "action": result.action,
        "reason": result.reason,
        "expires_at": result.expires_at,
        "base_sha": result.base_sha,
    }
    logger.info(
        "op=lease pr=%d command=%s action=%s reason=%s",
        args.pull_request,
        args.command,
        result.action,
        result.reason,
    )
    write_skill_output(
        output,
        output_format=output_format,
        human_summary=(
            f"PR #{args.pull_request} lease {args.command}: {result.action} ({result.reason})"
        ),
        status="PASS" if result.action == "ACT" else "WARNING",
        script_name=_SCRIPT_NAME,
    )
    return 0 if result.action == "ACT" else 1


__all__ = [
    "KNOWN_OWNERS",
    "MAX_SCAN",
    "MAX_TTL",
    "TTL",
    "Lease",
    "LeaseResult",
    "LeaseStoreError",
    "acquire",
    "build_claim",
    "build_parser",
    "build_tombstone",
    "classify_acquire",
    "main",
    "parse_lease_block",
    "release",
    "render_lease_comment",
    "select_authoritative_lease",
    "status",
]


if __name__ == "__main__":
    raise SystemExit(main())

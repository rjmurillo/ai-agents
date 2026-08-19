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
the PR timeline (the issue-comment stream). The latest claim wins. Each
claim has an immutable random ID. A release tombstone applies only to the
exact claim identity it names, so a delayed release cannot clear a newer
claim. This is NOT a
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
    0 - ACT: caller may proceed. Returned on a clean acquire or self-renew,
        a release, or one of the three fail-open paths enumerated in the
        "Fail-open vs fail-closed" section below.
    1 - SKIP: another live lease holds the branch, the ownership read could
        not reach the store (fail-closed; issue #4966, narrowing ADR-076
        part 3 step 6), OR (``renew`` only) the PR has already merged or
        closed, reason ``pr-closed`` (ADR-076 Amendment 2026-08-19, issue
        #5165): there is nothing left to coordinate, so no claim is written.
        A caller that does not distinguish ``pr-closed`` from any other SKIP
        reason degrades safely to today's behavior (decline, retry later).
    2 - PR not found / usage error
    3 - External error (API failure). For ``acquire`` / ``status`` / a
        tokenless ``renew`` this is remapped to exit 1 (SKIP): an
        ownership gate that cannot reach the store must not authorize a
        mutation (issue #4966). ``release`` and a token-backed ``renew``
        still fail open to exit 0.
    4 - Auth error. Same remapping as exit 3: fresh ``acquire`` / ``status``
        fail closed to SKIP; ``release`` and a token-backed ``renew`` fail
        open to exit 0 (ADR-076 part 3 step 6, narrowed by issue #4966).

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

Fail-open vs fail-closed, by design. The default is fail CLOSED: ACT is
returned only when this session provably holds the branch. Fail-open
survives only where relinquishing or extending-a-confirmed-hold cannot
create a race.

Record reconciliation. This narrows ADR-076 part 3 step 6, whose accepted
text still reads "Fail open ... return ACT with reason
lease-store-unavailable" for the read/write path. Issue #4966 (P0)
authorizes the narrowing: a blanket fail-open lets two sessions race one
branch. ADR-090 (proposed, issue #3413) formalizes the fail-closed
direction but is not yet accepted or implemented, so issue #4966 is the
operative authority here, not ADR-090. This module also does not adopt
ADR-090's distinct exit-3/4 table; store and auth failures are remapped to
SKIP (exit 1), this tool's native "do not mutate" verdict, which is stricter
than and consistent with ADR-090's "must not mutate" intent.

* Any store failure that leaves ownership UNVERIFIABLE fails CLOSED to
  SKIP (exit 1) with reason ``lease-store-unavailable``. This covers a
  ``status`` read, a fresh ``acquire``'s first read, a fresh acquire's
  claim WRITE or post-claim RE-READ (ACT requires a published-and-
  confirmed claim, so two sessions that both read free cannot both
  proceed), an unresolved login, and auth/transport failure (exit 3/4)
  for ``acquire`` / ``status`` / a tokenless ``renew``. An unreadable
  store leaves ownership unknown, and a gate that cannot determine
  ownership must not act on the branch (issue #4966;
  ``.claude/rules/security.md`` MUST-7, "infrastructure failure is not a
  security pass"). Reporting ACT here told every concurrent session the
  branch was free at the one moment none of them could tell.
* Only three paths FAIL OPEN to ACT (exit 0). (1) ``release``: TTL expiry
  covers a missed tombstone, so relinquishing under an unreadable store
  cannot create a race. (2) A ``renew`` whose earlier read CONFIRMED a
  still-live self-owned lease (a self-renew), whose only remaining failure
  is the TTL-extension write or its re-read: the prior claim is still
  live, so the holder keeps it (issue #4376). (3) A ``renew`` whose store
  read or auth failed BEFORE any confirmation, but which presents a
  durable local ownership token this session wrote on its last confirmed
  acquire/renew: the token, not the ``renew`` command name, is the
  ownership proof (issue #4966 HIGH). In all three the SHA gate remains
  the mutation backstop.

A genuine PR-not-found or usage error still exits 2. The "no store yet"
cold start (a successful read that returns no live lease) is distinct from
"a store that could not be read": the former ACTs, the latter SKIPs.

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
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Plugin-root resolution: matches sibling scripts (check_pr_live_state.py,
# post_pr_comment_reply.py). When the script runs inside a deployed Claude
# plugin, CLAUDE_PLUGIN_ROOT points at the plugin's installed path; when it
# runs inside the repo (the case under test), we walk up to the lib root.
# ---------------------------------------------------------------------------
_plugin_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
_workspace = os.environ.get("GITHUB_WORKSPACE")
if _plugin_root and os.path.isdir(os.path.join(_plugin_root, "lib", "github_core")):
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

from github_core.api import (
    assert_gh_authenticated,
    resolve_repo_params,
    safe_log_str,
)
from github_core.output import (
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

#: Worst-case gh CLI I/O between ``acquire`` reading the entry-time clock and a
#: self-renew fail-open decision: gh auth login, the git head read, the lease
#: list, the PR head read, the claim POST, and the authoritative re-read (30s
#: each plus the 10s git head). A self-renew only extends its prior claim
#: through a store outage when the claim stays live across this whole window.
#: A claim that could expire mid-operation fails CLOSED instead, so a partial
#: outage (this session's write fails while a competitor can still read) cannot
#: let a fresh session acquire the branch under a stale ACT (issue #4966
#: review). The SHA gate stays authoritative regardless.
RENEW_FAILOPEN_LIVENESS_MARGIN = timedelta(seconds=180)

#: A confirmed self-renew skips the write (returns ACT/self-renew-noop with no
#: POST) when the held lease's remaining life still exceeds this margin. The
#: marker's information content (owner, session, expiry) is unchanged until
#: the lease nears expiry, so writing a fresh comment before then adds PR
#: timeline noise and an API call with no informational benefit (issue
#: #5160). This is independent of how often a caller invokes ``renew``: a
#: caller polling every few seconds against the 15-minute TTL produced ~500
#: marker comments on one PR over 33 hours, all but the last few redundant.
#: Set comfortably above RENEW_FAILOPEN_LIVENESS_MARGIN so a real renewal
#: still lands with margin to spare before the fail-open boundary matters.
RENEW_SKIP_MARGIN = timedelta(minutes=5)

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
_CLAIM_ID = re.compile(r"^[0-9a-f]{32}$")

#: Per-key strict line patterns. The block is parsed key-by-key; anything that
#: does not match every required key with a valid value is malformed and
#: treated as "no live lease".
_KEY_LINE = re.compile(r"^([a-z_]+):\s*(.+?)\s*$")

_REQUIRED_KEYS = ("owner", "session", "acquired_at", "expires_at", "base_sha")
_OPTIONAL_KEYS = ("target_owner", "claim_id")


# ---------------------------------------------------------------------------
# Value type
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Lease:
    """A parsed, validated lease marker.

    Construction implies validity: ``parse_lease_block`` returns ``None``
    rather than an invalid ``Lease``. ``owner == "none"`` is a tombstone.

    ``owner``, ``session``, ``target_owner``, and ``claim_id`` come from the
    forgeable comment body. ``author`` is the VERIFIED GitHub comment author
    (``user.login`` from the API), the credential that posted the comment.
    Tombstone causality matches all body identity fields plus the verified
    author. ``parse_lease_block`` cannot know the author from the body, so
    it leaves ``author=""``; ``select_authoritative_lease`` stamps it from
    the enclosing comment.
    """

    owner: str
    session: str
    acquired_at: datetime
    expires_at: datetime
    base_sha: str
    author: str = ""
    target_owner: str = ""
    claim_id: str = ""

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


def _parse_identity_fields(
    fields: dict[str, str],
) -> tuple[str, str, str, str] | None:
    """Validate and return owner, target owner, base SHA, and claim ID."""
    owner = fields["owner"]
    if owner not in KNOWN_OWNERS:
        return None
    target_owner = fields.get("target_owner", "")
    if target_owner and target_owner not in KNOWN_OWNERS - {TOMBSTONE_OWNER}:
        return None
    base_sha = fields["base_sha"]
    if not _SHA40.match(base_sha):
        return None
    claim_id = fields.get("claim_id", "")
    if claim_id and not _CLAIM_ID.match(claim_id):
        return None
    return owner, target_owner, base_sha, claim_id


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
        if key in (*_REQUIRED_KEYS, *_OPTIONAL_KEYS):
            fields[key] = value

    if any(key not in fields for key in _REQUIRED_KEYS):
        return None

    identity = _parse_identity_fields(fields)
    if identity is None:
        return None
    owner, target_owner, base_sha, claim_id = identity

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
        target_owner=target_owner,
        claim_id=claim_id,
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


def _tombstone_matches(tombstone: Lease, claim: Lease) -> bool:
    """Return whether a tombstone causally targets the current claim."""
    return (
        tombstone.target_owner == claim.owner
        and tombstone.session == claim.session
        and tombstone.base_sha == claim.base_sha
        and tombstone.claim_id != ""
        and tombstone.claim_id == claim.claim_id
        and tombstone.author != ""
        and tombstone.author == claim.author
    )


def select_authoritative_lease(comments: list[dict]) -> Lease | None:
    """Return the lease from the most-recent valid marker comment, or None.

    Claims use latest-marker-wins ordering (ADR-076 part 1). Tombstones are
    causal: they replace the current claim only when owner, session, base
    SHA, immutable claim ID, and verified author match. A delayed release
    therefore cannot clear a newer claim. ``comments`` is the PR timeline
    in API order
    (oldest first), each a dict with at least ``body``, ``created_at``, and
    ``user.login``. The scan is bounded to the latest ``MAX_SCAN`` comments
    (ADR-076 Security): a flood of forged markers cannot become an unbounded
    parse-cost DoS, and an older comment cannot hold a live lease anyway.

    Each selected lease is stamped with its enclosing comment's VERIFIED
    author (``user.login``), so a later trust decision keys on the
    credential that posted the comment, not on the forgeable body
    ``owner`` / ``session``. Marker comments that fail to parse are skipped
    (treated as "no live lease"); the most recent *parseable* marker wins.
    """
    candidates: list[tuple[str, Lease]] = []
    for comment in comments[-MAX_SCAN:]:
        body = comment.get("body") or ""
        if LEASE_MARKER not in body:
            continue
        lease = parse_lease_block(body)
        if lease is None:
            continue
        created = comment.get("created_at") or ""
        candidates.append((created, replace(lease, author=_comment_author(comment))))

    latest: Lease | None = None
    for _, candidate in sorted(candidates, key=lambda item: item[0]):
        if (
            candidate.owner == TOMBSTONE_OWNER
            and latest is not None
            and not _tombstone_matches(candidate, latest)
        ):
            continue
        latest = candidate
    return latest


def classify_acquire(
    lease: Lease | None,
    acting_author: str,
    session: str,
    now: datetime,
) -> dict:
    """Decide ACT vs SKIP for an acquire, given the authoritative lease.

    Mirrors ``check_pr_live_state.classify_live_state`` verdict shape
    (ADR-076 part 3, acquire steps 3-5):

    - A live lease whose VERIFIED comment author is not ``acting_author``
      -> SKIP, reason ``held-by:<owner>``, with ``expires_at`` so the
      caller knows when to retry. (``owner`` in the reason is the body's
      display label; the trust decision used ``author``.)
    - A live lease whose verified author IS ``acting_author`` and whose
      session matches the caller (self-renewal) -> ACT, reason
      ``self-renew``. The verified author is the trust boundary. Session
      identity prevents two agents sharing one login from renewing each
      other's lease.
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
        if acting_author != "" and lease.author == acting_author and lease.session == session:
            return {"action": "ACT", "reason": "self-renew"}
        return {
            "action": "SKIP",
            "reason": f"held-by:{lease.owner}",
            "expires_at": _to_rfc3339(lease.expires_at),
        }
    return {"action": "ACT", "reason": "free"}


def _claim_is_authoritative(lease: Lease | None, claim: Lease, author: str) -> bool:
    """Return True when a reread lease still matches the posted claim.

    The posted body is serialized to whole-second RFC3339 timestamps, so
    the in-memory claim must be normalized to the same precision before
    comparing.
    """
    normalized = replace(
        claim,
        author=author,
        acquired_at=claim.acquired_at.replace(microsecond=0),
        expires_at=claim.expires_at.replace(microsecond=0),
    )
    return lease == normalized


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
    target_owner = f"target_owner: {lease.target_owner}\n" if lease.target_owner else ""
    claim_id = f"claim_id: {lease.claim_id}\n" if lease.claim_id else ""
    return (
        f"{LEASE_MARKER}\n"
        f"owner: {lease.owner}\n"
        f"session: {lease.session}\n"
        f"acquired_at: {_to_rfc3339(lease.acquired_at)}\n"
        f"expires_at: {_to_rfc3339(lease.expires_at)}\n"
        f"base_sha: {lease.base_sha}\n"
        f"{target_owner}"
        f"{claim_id}"
    )


def build_claim(
    owner: str,
    session: str,
    base_sha: str,
    now: datetime,
    claim_id: str | None = None,
) -> Lease:
    """Build a fresh claim lease starting now with a full TTL window."""
    return Lease(
        owner=owner,
        session=session,
        acquired_at=now,
        expires_at=now + TTL,
        base_sha=base_sha,
        claim_id=claim_id or uuid.uuid4().hex,
    )


def build_tombstone(
    owner: str,
    session: str,
    now: datetime,
    base_sha: str = "0" * 40,
    claim_id: str = "",
) -> Lease:
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
        base_sha=base_sha,
        target_owner=owner,
        claim_id=claim_id,
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

    This answers "what is checked out here", which is NOT what ``base_sha``
    means. ADR-076 part 1 defines ``base_sha`` as the "PR head.sha the
    holder fetched before acquiring", and acquire step 1 fetches it from
    GitHub. Acquire records this value only as the observed local checkout,
    so a caller standing on the wrong branch is reported rather than
    published as the PR's head (issues #4357, #4375).
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


@dataclass(frozen=True, slots=True)
class _PrHeadState:
    """PR head SHA plus live merge/close state, read in one REST call.

    ADR-076 Amendment 2026-08-19 (issue #5165): widens the single REST call
    ``acquire()`` already made for ``base_sha`` to also project ``state`` and
    ``merged``, so a renew on an already-closed PR can be detected at zero
    added round-trips over what the module already spends today.
    """

    sha: str
    state: str
    merged: bool


def _pr_head_state(owner: str, repo: str, pr: int) -> _PrHeadState:
    """Return the PR's authoritative head SHA, ``state``, and ``merged``.

    ADR-076 part 3 acquire step 1: "Fetch the PR ``head.sha`` and the latest
    N lease comments in one bounded read". The value is read from GitHub, so
    it describes the PR branch no matter which checkout the caller stands
    in. Acquire catches the failure and records the zero sentinel rather
    than failing open, because losing freshness evidence must not also lose
    the lock (see ``acquire``).

    Raises LeaseStoreError on any read, transport, or payload failure.
    """
    try:
        result = subprocess.run(
            [
                "gh",
                "api",
                f"repos/{owner}/{repo}/pulls/{pr}",
                "--jq",
                "{sha:.head.sha, state:.state, merged:.merged}",
            ],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise LeaseStoreError(f"pr head read failed: {exc}") from exc
    if result.returncode != 0:
        raise LeaseStoreError(
            f"pr head read exited {result.returncode}: {safe_log_str((result.stderr or '')[:200])}"
        )
    try:
        payload = json.loads((result.stdout or "").strip() or "{}")
    except json.JSONDecodeError as exc:
        raise LeaseStoreError(f"pr head read returned non-JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise LeaseStoreError("pr head read returned a non-object payload")
    sha = payload.get("sha")
    if not isinstance(sha, str) or not _SHA40.match(sha):
        raise LeaseStoreError("pr head read returned no 40-hex sha")
    state = payload.get("state")
    return _PrHeadState(
        sha=sha,
        state=state if isinstance(state, str) else "",
        merged=bool(payload.get("merged")),
    )


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
    """Outcome of a lease operation. ``action`` is ACT or SKIP.

    ``base_sha`` is the PR's head SHA read from GitHub (ADR-076 part 1), and
    is populated only on the ACT path. ``acquire`` returns SKIP before it
    reads the PR head, so both ``base_sha`` and ``local_head_sha`` stay None
    on that path; a caller must not read them as evidence about the PR.

    On ACT, ``local_head_sha`` is what the caller's checkout had at ``HEAD``,
    or None when git could not answer. The two differ whenever acquire runs
    from a checkout that is not the PR branch; the caller reports both so
    the divergence is visible instead of silently recorded as the PR's head
    (issue #4357 acceptance criterion 4).
    """

    action: str
    reason: str
    expires_at: str | None = None
    base_sha: str | None = None
    local_head_sha: str | None = None


def _warn_on_checkout_mismatch(pr: int, local_sha: str | None, base_sha: str) -> None:
    """Log both SHAs when the caller's checkout is not the PR head.

    The lease still publishes the authoritative PR head, so the recorded
    evidence is correct either way. The warning tells the operator that the
    session doing the fix work is standing somewhere else, which is what
    produced the wrong lease on #4294 (issue #4357).
    """
    if local_sha is None or local_sha == base_sha:
        return
    logger.warning(
        "op=lease_checkout_mismatch pr=%d local_head_sha=%s pr_head_sha=%s",
        pr,
        safe_log_str(local_sha),
        safe_log_str(base_sha),
    )


# ---------------------------------------------------------------------------
# Local ownership token. A ``renew`` fails open to ACT when the store is
# unreachable so a long pre-push validation keeps its lease (issue #4376).
# That fail-open is only safe for a caller that actually acquired the lease.
# The command name alone is not proof: ``renew --session never-acquired``
# must not mint ACT during an outage (issue #4966 HIGH finding). This token is
# the independent ownership proof: ``acquire`` writes it on a confirmed win,
# ``renew`` reads it before the fail-open, and ``release`` clears it.
#
# It is a LOCAL identity artifact, never the lease store. The lease store is
# the PR timeline (ADR-076 part 1); this file only records "this session, on
# this machine, won the lease for this (repository, PR) at time T". The
# repository identity is part of the token key and payload, so a token written
# for one repository cannot authorize a renew in another repository that
# shares the global token directory (issue #4966 review). It grants no push
# (the SHA gate does) and is bounded by MAX_TTL, so an abandoned token cannot
# grant fail-open past one lease lifetime. Acquire/renew run in the same
# session on the same machine (ADR-076 Phase 1 is local-only), so the token is
# always co-located with the caller that needs it.
# ---------------------------------------------------------------------------

#: Override for the ownership-token directory. Tests point this at a temp dir;
#: production uses the XDG state directory. Not the lease store.
_OWNERSHIP_TOKEN_DIR_ENV = "PR_AUTOFIX_LEASE_STATE_DIR"


def _ownership_token_dir() -> str:
    override = os.environ.get(_OWNERSHIP_TOKEN_DIR_ENV)
    if override:
        return override
    base = os.environ.get("XDG_STATE_HOME") or os.path.join(
        os.path.expanduser("~"), ".local", "state"
    )
    return os.path.join(base, "pr-autofix-lease")


def _normalize_repo_identity(repo_owner: str, repo: str) -> tuple[str, str]:
    """Lowercase the repository identity so a case variant maps to one key.

    GitHub owner and repository names are case-insensitive, so ``Octo/Repo`` and
    ``octo/repo`` name one repository addressing one remote lease. Normalizing
    the identity in the key, payload, and validation keeps a case-variant
    release matched to the token its acquire wrote. Without it, release computes
    a different path, misses the token, posts the tombstone, and leaves the
    original valid token able to authorize a post-release fail-open renew
    (issue #4966 review).
    """
    return repo_owner.lower(), repo.lower()


def _ownership_token_path(owner: str, session: str, repo_owner: str, repo: str, pr: int) -> str:
    """Return the token path for one (repo, owner, session, pr) holder.

    The repository identity (``repo_owner``/``repo``) is part of the key so a
    token written for PR #1 in one repository cannot authorize a token-backed
    renew of PR #1 in a different repository sharing the same global token
    directory (issue #4966 review). The identity is hashed so a forgeable
    ``owner`` (``local:pr-autofix``) or ``session`` string cannot craft a path
    outside the token directory (CWE-22). The identity is lowercased first so a
    case-variant caller resolves the same path (issue #4966 review).
    """
    repo_owner, repo = _normalize_repo_identity(repo_owner, repo)
    key = hashlib.sha256(
        f"{repo_owner}\x00{repo}\x00{owner}\x00{session}\x00{pr}".encode()
    ).hexdigest()
    return os.path.join(_ownership_token_dir(), f"{key}.json")


def _write_ownership_token(
    owner: str, session: str, repo_owner: str, repo: str, pr: int, now: datetime
) -> None:
    """Record that this session holds the lease (called on a confirmed ACT).

    Best-effort: a write failure only weakens a future ``renew``'s ability to
    fail open, never correctness. The worst case of a lost token is a renew
    that fails closed to SKIP, which is the safe direction.
    """
    repo_owner, repo = _normalize_repo_identity(repo_owner, repo)
    path = _ownership_token_path(owner, session, repo_owner, repo, pr)
    payload = json.dumps(
        {
            "owner": owner,
            "session": session,
            "repo_owner": repo_owner,
            "repo": repo,
            "pr": pr,
            "written_at": _to_rfc3339(now),
        }
    )
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(payload)
    except OSError as exc:
        logger.warning("op=lease_ownership_write_failed pr=%d err=%s", pr, safe_log_str(str(exc)))


def _has_valid_ownership_token(
    owner: str, session: str, repo_owner: str, repo: str, pr: int, now: datetime
) -> bool:
    """Return True iff this session recorded a lease win within MAX_TTL.

    This is the ownership proof ``renew`` needs to fail open when the store
    is unreadable (issue #4966 HIGH). A caller that never acquired has no
    token, so it fails closed to SKIP. The token key and payload both carry
    the repository identity, so a token from another repository cannot satisfy
    this check (issue #4966 review). The MAX_TTL freshness bound stops an
    abandoned token from granting fail-open past one lease lifetime; a healthy
    holder rewrites it on every successful renew, well inside that window. The
    upper bound is strict (``< MAX_TTL``) to match ``Lease.is_live``'s strict
    expiry (``now < expires_at``): a token exactly one TTL old coincides with
    the instant the remote lease dies, so it must not authorize a fail-open
    renew at that boundary (issue #4966 review).
    """
    repo_owner, repo = _normalize_repo_identity(repo_owner, repo)
    path = _ownership_token_path(owner, session, repo_owner, repo, pr)
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.warning("op=lease_ownership_absent pr=%d err=%s", pr, safe_log_str(str(exc)))
        return False
    if not isinstance(data, dict):
        # A syntactically valid but non-object token (``[]``, a bare number, a
        # string) decodes cleanly, then the field reads below would raise
        # AttributeError on ``.get`` and crash the CLI during the very outage
        # this fail-open path exists to survive. An unrecognizable token proves
        # no ownership, so fail closed to SKIP (issue #4966 review).
        logger.warning("op=lease_ownership_malformed pr=%d", pr)
        return False
    if (
        data.get("owner") != owner
        or data.get("session") != session
        or data.get("repo_owner") != repo_owner
        or data.get("repo") != repo
        or data.get("pr") != pr
    ):
        return False
    written = _parse_rfc3339_utc(str(data.get("written_at", "")))
    if written is None:
        return False
    return timedelta() <= now - written < MAX_TTL


def _clear_ownership_token(owner: str, session: str, repo_owner: str, repo: str, pr: int) -> bool:
    """Revoke this session's ownership token (called on release).

    Returns True when the token is gone or provably invalidated, False when
    revocation could not be persisted. Revocation is NOT best-effort. The token
    is ownership proof, so a residual valid token would let a post-release renew
    fail open after the lease was already relinquished (issue #4966 review).
    This is the asymmetric opposite of the acquire WRITE, which is safe as
    best-effort because a lost write only makes a later renew fail CLOSED.

    Removal escalates: unlink, then overwrite with a revoked marker that a later
    ``_has_valid_ownership_token`` rejects on the field match. When both fail,
    return False; the caller then keeps the remote lease held, so the surviving
    token still matches a live lease this session owns and its fail-open renew
    stays correct.
    """
    path = _ownership_token_path(owner, session, repo_owner, repo, pr)
    try:
        os.remove(path)
        return True
    except FileNotFoundError:
        return True
    except OSError as exc:
        logger.warning("op=lease_ownership_unlink_failed pr=%d err=%s", pr, safe_log_str(str(exc)))
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"revoked": True, "pr": pr}))
        return True
    except OSError as exc:
        logger.error("op=lease_ownership_revoke_failed pr=%d err=%s", pr, safe_log_str(str(exc)))
        return False


def _self_renew_survives_store_io(current: Lease | None, now: datetime) -> bool:
    """True when a confirmed-live self-lease outlasts a fail-open's store I/O.

    ``acquire`` reads the authoritative lease once at entry-time ``now``, then
    makes up to three 30s gh CLI calls (PR head, claim POST, authoritative
    re-read) before a self-renew may fail open. If the prior claim would expire
    inside that window, a partial store outage (this session's write fails while
    a competitor can still read) lets a fresh session acquire the branch
    mid-operation. Requiring the claim to stay live across
    ``RENEW_FAILOPEN_LIVENESS_MARGIN`` keeps the fail-open on the safe side of
    that boundary (issue #4966 review); a claim expiring sooner fails CLOSED to
    SKIP. The SHA gate stays authoritative regardless.
    """
    return current is not None and current.expires_at > now + RENEW_FAILOPEN_LIVENESS_MARGIN


def acquire(
    owner: str,
    session: str,
    repo_owner: str,
    repo: str,
    pr: int,
    now: datetime | None = None,
    acting_author: str | None = None,
    renewing: bool = False,
) -> LeaseResult:
    """Acquire (or self-renew) the lease for ``pr`` (ADR-076 part 3 acquire).

    Returns ACT only when the caller provably holds the branch: a fresh
    claim that was published AND confirmed as the latest live marker, or a
    self-renewal of a lease the read confirmed this session already holds.
    Every store failure that leaves ownership unverifiable returns
    SKIP/``lease-store-unavailable`` (issue #4966). The failure
    verdicts are:

    - First store READ fails: a fresh acquire SKIPs (no prior ownership).
      A renew ACTs ONLY when a durable ownership token proves this session
      won the lease earlier; without a token it SKIPs, so the ``renew``
      command name alone never mints ACT (issue #4966 HIGH; #4376).
    - Login unresolved (``gh api user`` blip): same rule as the read
      failure, since the session cannot verify its own identity.
    - Claim WRITE fails / post-claim RE-READ fails: a fresh acquire SKIPs,
      because ACT requires a published-and-confirmed claim; two sessions
      that both read free and both fail here must not both proceed (issue
      #4966 CRITICAL). A self-renew ACTs, because the read already
      confirmed a still-live prior claim (issue #4376).

    Self-renewal keys on ``acting_author``: the VERIFIED login of the
    credential running acquire, matched against the verified author of the
    authoritative lease comment, never against the forgeable body
    ``owner`` / ``session`` (ADR-076 Security, CWE-345). ``acting_author``
    is injectable for deterministic tests; production passes None and the
    authenticated ``gh`` login is resolved.

    ``base_sha`` is the PR head SHA read from GitHub (ADR-076 part 3 step
    1), never the caller's local HEAD, so an acquire run from the wrong
    checkout cannot publish freshness evidence for another branch. The
    local HEAD is still read and reported as ``local_head_sha``, and a
    mismatch is logged with both values (issues #4357, #4375). The head
    read runs after the lease verdict and records the zero sentinel on
    failure, so a transient error on it cannot skip the read that enforces
    mutual exclusion, and it costs nothing on the SKIP path.

    On a confirmed ACT the session writes a durable ownership token
    (``_write_ownership_token``); ``release`` clears it. The token is the
    only proof a later renew uses to fail open through a store outage; it
    is a local identity artifact, never the lease store, and grants no push
    (the SHA gate does).

    ``now`` is injectable for deterministic tests; production passes None
    and the current UTC instant is used.
    """
    now = now or datetime.now(UTC)
    author = _gh_authenticated_login() if acting_author is None else acting_author
    local_sha = _git_head_sha()
    if acting_author is None and author == "":
        # The login could not be resolved (auth/transport blip on `gh api
        # user`), so this session cannot verify its own identity against the
        # authoritative lease. A fresh acquire fails CLOSED to SKIP: it cannot
        # tell a free branch from one it holds, and a gate that cannot
        # determine ownership must not mutate (issue #4966). A renew
        # may still fail OPEN, but only against a durable ownership token this
        # session wrote at acquire time, never on the command name alone
        # (issue #4966 HIGH; the `renew --session never-acquired` repro).
        logger.warning("op=lease_login_unavailable pr=%d renewing=%s", pr, renewing)
        if renewing and _has_valid_ownership_token(owner, session, repo_owner, repo, pr, now):
            logger.warning("op=lease_renew_failopen_ownership pr=%d cause=login-unresolved", pr)
            return LeaseResult(
                "ACT", "lease-store-unavailable", base_sha="0" * 40, local_head_sha=local_sha
            )
        return LeaseResult("SKIP", "lease-store-unavailable")
    try:
        comments = list_lease_comments(repo_owner, repo, pr)
    except LeaseStoreError as exc:
        if renewing and _has_valid_ownership_token(owner, session, repo_owner, repo, pr, now):
            # A renew whose store read fails extends in place ONLY when a
            # durable ownership token proves this session already won the
            # lease. It fails open to ACT; the SHA gate stays authoritative
            # while the advisory store is down (ADR-076 step 6; issue #4376).
            # The token, not the "renew" command name, is the proof (issue
            # #4966 HIGH). A fresh acquire fails closed below, so no competitor
            # can enter during the outage; the holder proceeding adds no new
            # concurrency. Residual lease-loss is issue #4926.
            logger.warning(
                "op=lease_renew_failopen_ownership pr=%d err=%s", pr, safe_log_str(str(exc))
            )
            return LeaseResult(
                "ACT", "lease-store-unavailable", base_sha="0" * 40, local_head_sha=local_sha
            )
        # Fail closed: a fresh acquire (or a renew with no ownership token) has
        # no prior ownership evidence, so an unreadable store leaves ownership
        # unknown. A gate that cannot determine ownership must not mutate the
        # branch (issue #4966), so SKIP rather than blindly claim a
        # branch a foreign live lease may already hold.
        logger.warning("op=lease_acquire_failclosed pr=%d err=%s", pr, safe_log_str(str(exc)))
        return LeaseResult("SKIP", "lease-store-unavailable")

    current = select_authoritative_lease(comments)
    verdict = classify_acquire(current, author, session, now)
    if verdict["action"] == "SKIP":
        return LeaseResult("SKIP", verdict["reason"], expires_at=verdict.get("expires_at"))
    # ``self-renew`` means the read CONFIRMED this session already holds a live
    # lease. That confirmation, not a token, lets a failed TTL extension below
    # fail open: the prior claim is still live. A ``free`` verdict is a fresh
    # claim with no such proof, so its write/re-read failures fail closed.
    already_holds = verdict["reason"] == "self-renew"

    # A confirmed self-renew with plenty of TTL left has nothing to extend yet:
    # skip the write entirely rather than posting a redundant marker comment
    # (issue #5160). This bounds worst-case comment volume no matter how often
    # the caller invokes ``renew`` above the module's own polling cadence.
    if renewing and already_holds and current is not None and current.expires_at - now > RENEW_SKIP_MARGIN:
        return LeaseResult(
            "ACT",
            "self-renew-noop",
            expires_at=_to_rfc3339(current.expires_at),
            base_sha=current.base_sha,
            local_head_sha=local_sha,
        )

    # The head read is freshness evidence, not the lock. Failing it open to ACT
    # alongside the comment read would let a transient API error skip the read
    # that enforces mutual exclusion, so it is scoped to the sentinel instead.
    pr_state: _PrHeadState | None = None
    try:
        pr_state = _pr_head_state(repo_owner, repo, pr)
        base_sha = pr_state.sha
    except LeaseStoreError as exc:
        logger.warning("op=lease_pr_head_unavailable pr=%d err=%s", pr, safe_log_str(str(exc)))
        base_sha = "0" * 40

    # ADR-076 Amendment 2026-08-19 (issue #5165): a renew against a PR that
    # has already merged or closed has nothing left to coordinate. This check
    # is scoped to renewing=True only (a fresh acquire's cost is bounded by
    # how many PRs pr-autofix walks; an unbounded renew loop is not) and to
    # the write path specifically (after the RENEW_SKIP_MARGIN noop check
    # above), so it never adds a round-trip beyond the one acquire() already
    # spends here. A failed read (pr_state is None) falls through unchanged,
    # exactly as it does today.
    if renewing and pr_state is not None and (pr_state.merged or pr_state.state == "CLOSED"):
        logger.info(
            "op=lease_renew_pr_closed pr=%d state=%s merged=%s",
            pr,
            pr_state.state,
            pr_state.merged,
        )
        return LeaseResult(
            "SKIP", "pr-closed", base_sha=base_sha, local_head_sha=local_sha
        )

    _warn_on_checkout_mismatch(pr, local_sha, base_sha)

    claim = build_claim(owner, session, base_sha, now)
    try:
        post_lease_comment(repo_owner, repo, pr, render_lease_comment(claim))
    except LeaseStoreError as exc:
        if already_holds and _self_renew_survives_store_io(current, now):
            # A self-renew whose TTL-extension write fails keeps the prior,
            # still-live claim it confirmed on the read above, so it fails open
            # to ACT (issue #4376; SHA gate backstop). The liveness margin
            # ensures the prior claim cannot expire during the store I/O.
            logger.warning(
                "op=lease_renew_write_failopen pr=%d err=%s", pr, safe_log_str(str(exc))
            )
            return LeaseResult(
                "ACT", "lease-store-unavailable", base_sha=base_sha, local_head_sha=local_sha
            )
        if already_holds:
            # The confirmed-live prior claim could expire inside the store-I/O
            # window, so a partial outage might let a fresh session acquire the
            # branch mid-operation. Fail CLOSED to SKIP rather than extend a
            # claim that may already be dead (issue #4966 review).
            logger.warning(
                "op=lease_renew_expiry_failclosed pr=%d err=%s", pr, safe_log_str(str(exc))
            )
            return LeaseResult("SKIP", "lease-store-unavailable")
        # A fresh claim that cannot be published fails CLOSED to SKIP. Two
        # sessions can both read a free branch, both fail to POST, and both
        # would ACT if this failed open: the original race one step later
        # (issue #4966 CRITICAL). ACT requires a published claim, so an
        # unpublished one cannot proceed.
        logger.warning("op=lease_claim_write_failclosed pr=%d err=%s", pr, safe_log_str(str(exc)))
        return LeaseResult("SKIP", "lease-store-unavailable")

    try:
        latest_comments = list_lease_comments(repo_owner, repo, pr)
    except LeaseStoreError as exc:
        if already_holds and _self_renew_survives_store_io(current, now):
            # A self-renew that cannot re-read still holds the confirmed-live
            # prior claim; no competitor can steal a live lease, so it fails
            # open to ACT (issue #4376). The liveness margin ensures the prior
            # claim cannot expire during the store I/O.
            logger.warning(
                "op=lease_renew_recheck_failopen pr=%d err=%s", pr, safe_log_str(str(exc))
            )
            return LeaseResult(
                "ACT", "lease-store-unavailable", base_sha=base_sha, local_head_sha=local_sha
            )
        if already_holds:
            # The confirmed-live prior claim could expire inside the store-I/O
            # window, so a partial outage might let a fresh session acquire the
            # branch mid-operation. Fail CLOSED to SKIP (issue #4966 review).
            logger.warning(
                "op=lease_renew_expiry_failclosed pr=%d err=%s", pr, safe_log_str(str(exc))
            )
            return LeaseResult("SKIP", "lease-store-unavailable")
        # A fresh claim that cannot be re-read cannot confirm it won the post
        # race, so it fails CLOSED to SKIP. ACT requires an authoritative
        # re-read confirming this session's claim is the latest live marker
        # (issue #4966 CRITICAL).
        logger.warning(
            "op=lease_claim_recheck_failclosed pr=%d err=%s", pr, safe_log_str(str(exc))
        )
        return LeaseResult("SKIP", "lease-store-unavailable")

    current_after_post = select_authoritative_lease(latest_comments)
    if not _claim_is_authoritative(current_after_post, claim, author):
        if current_after_post is not None and current_after_post.author not in ("", author):
            return LeaseResult(
                "SKIP",
                f"held-by:{current_after_post.owner}",
                expires_at=_to_rfc3339(current_after_post.expires_at),
            )
        return LeaseResult("SKIP", "lease-race-lost", expires_at=_to_rfc3339(claim.expires_at))

    # A published claim confirmed as the latest live marker: this session holds
    # the lease. Record the durable ownership token so a later renew can prove
    # prior ownership and fail open through a store outage (issue #4966 HIGH,
    # #4376). A token write failure is non-fatal (renew would just fail closed).
    _write_ownership_token(owner, session, repo_owner, repo, pr, now)
    return LeaseResult(
        "ACT",
        verdict["reason"],
        expires_at=_to_rfc3339(claim.expires_at),
        base_sha=base_sha,
        local_head_sha=local_sha,
    )


def release(
    owner: str,
    session: str,
    repo_owner: str,
    repo: str,
    pr: int,
    now: datetime | None = None,
    acting_author: str | None = None,
) -> LeaseResult:
    """Release the lease for ``pr`` by writing a tombstone (ADR-076 part 3).

    Best-effort and idempotent: a tombstone is posted only when the latest
    live lease still matches this owner, session, verified author, and an
    immutable claim ID. An already-free, legacy, or foreign lease returns
    ACT without writing. A store error fails open to ACT because TTL expiry
    covers a missed release (relinquishing under an unreadable store cannot
    create a race; the worst case is the lease lingers one TTL). Releasing
    also clears this session's durable ownership token so a later renew
    cannot fail open after the session has relinquished. ``now`` and
    ``acting_author`` are injectable for deterministic tests.
    """
    now = now or datetime.now(UTC)
    # Revoke the local ownership proof BEFORE relinquishing the remote lease.
    # Once a tombstone is posted this session no longer holds the lease, so a
    # residual valid token must never survive that transition (issue #4966
    # review). If revocation cannot be persisted, keep the remote lease held by
    # returning without posting a tombstone: the surviving token then still
    # matches a live lease this session owns, so its fail-open renew stays
    # correct, and TTL expiry eventually reaps the lease.
    if not _clear_ownership_token(owner, session, repo_owner, repo, pr):
        logger.warning("op=lease_release_ownership_revoke_failed pr=%d", pr)
        return LeaseResult("SKIP", "token-revocation-failed")
    author = _gh_authenticated_login() if acting_author is None else acting_author
    try:
        comments = list_lease_comments(repo_owner, repo, pr)
    except LeaseStoreError as exc:
        logger.warning("op=lease_release_failopen pr=%d err=%s", pr, safe_log_str(str(exc)))
        return LeaseResult("ACT", "lease-store-unavailable")

    current = select_authoritative_lease(comments)
    if current is None or not current.is_live(now):
        return LeaseResult("ACT", "already-free")
    if (
        current.owner != owner
        or current.session != session
        or author == ""
        or current.author != author
        or current.claim_id == ""
    ):
        return LeaseResult("ACT", "not-owner")

    tombstone = build_tombstone(
        owner,
        session,
        now,
        current.base_sha,
        current.claim_id,
    )
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
        # Fail closed: an unreadable store leaves ownership unknown, and the
        # safe reading of unknown is decline (issue #4966).
        # Reporting ACT here told concurrent sessions the branch was free at
        # the one moment none of them could tell.
        logger.warning("op=lease_status_failclosed pr=%d err=%s", pr, safe_log_str(str(exc)))
        return LeaseResult("SKIP", "lease-store-unavailable")
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
    parser.add_argument(
        "command",
        choices=["acquire", "renew", "release", "status"],
        help=(
            "Lease operation. 'renew' extends the TTL in place (call periodically "
            "during a long pre-push validation so the lease outlives the hook; "
            "issue #4376). Internally identical to 'acquire' on an existing live "
            "lease held by this credential (self-renewal via ADR-076 part 3 step 4)."
        ),
    )
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
    # 'renew' is acquire with self-renewal semantics: the caller already holds
    # the lease and wants to extend the TTL in place. The acquire() function
    # handles this via classify_acquire's self-renew branch (ADR-076 part 3
    # step 4). Callers should invoke 'renew' periodically during a long
    # pre-push validation run to keep the lease live for the full critical
    # section (issue #4376). A renew that finds the lease free (e.g. expired)
    # re-claims it, which is the correct recovery.
    if args.command in ("acquire", "renew"):
        return acquire(
            args.lease_owner,
            args.session,
            owner,
            repo,
            args.pull_request,
            renewing=args.command == "renew",
        )
    return release(args.lease_owner, args.session, owner, repo, args.pull_request)


def _handle_unreachable_auth(
    args: argparse.Namespace, code: int, output_format: str, repo_owner: str, repo: str
) -> int:
    """Emit a verdict when auth/transport fails before any lease read.

    ``assert_gh_authenticated`` exits 4 on a genuine auth misconfiguration and
    3 on a transport failure. Neither can reach the store, so neither can
    verify branch ownership. For ``acquire`` and ``status`` that means SKIP:
    an ownership gate that cannot read the store must not authorize a mutation
    (issue #4966 CRITICAL; ``.claude/rules/security.md`` MUST-7,
    "infrastructure failure is not a security pass"). ``release`` still fails
    open to ACT because a missed tombstone is covered by TTL expiry.
    ``renew`` fails open ONLY when a durable ownership token proves this
    session already holds the lease (issue #4966 HIGH; #4376); without a token
    it SKIPs, so the ``renew`` command name alone never mints ACT. The token
    check uses the resolved repository identity, so a token from another
    repository cannot mint ACT here (issue #4966 review).

    The exit code is preserved in the log and human summary so an operator can
    tell a persistent auth misconfiguration (exit 4) from a transient
    transport blip (exit 3). The machine ``reason`` stays
    ``lease-store-unavailable`` so callers branch on one sentinel.
    """
    if args.command == "release":
        action = "ACT"
    elif args.command == "renew" and _has_valid_ownership_token(
        args.lease_owner, args.session, repo_owner, repo, args.pull_request, datetime.now(UTC)
    ):
        action = "ACT"
    else:
        action = "SKIP"
    cause = "auth misconfiguration" if code == 4 else "transport failure"
    logger.warning(
        "op=lease_main_unreachable exit_code=%d command=%s pr=%d action=%s",
        code,
        args.command,
        args.pull_request,
        action,
    )
    result = {
        "success": True,
        "pull_request": args.pull_request,
        "owner": repo_owner,
        "repo": repo,
        "command": args.command,
        "action": action,
        "reason": "lease-store-unavailable",
        "expires_at": None,
        "base_sha": None,
        "local_head_sha": None,
    }
    write_skill_output(
        result,
        output_format=output_format,
        human_summary=(
            f"PR #{args.pull_request} lease {args.command}: {action} "
            f"(lease-store-unavailable; {cause}, exit {code} before store read)"
        ),
        status="PASS" if action == "ACT" else "WARNING",
        script_name=_SCRIPT_NAME,
    )
    return 0 if action == "ACT" else 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_format = args.output_format
    # ADR-076 part 3 step 6: repo-parameter validation must run before any
    # auth handling so malformed owner/repo still exits 2. A resolvable-but-
    # unreachable auth/transport failure (exit 3/4) then routes through
    # _handle_unreachable_auth: acquire/status fail CLOSED to SKIP because they
    # cannot verify ownership (issue #4966), release fails open, and renew
    # fails open only against a durable ownership token. This narrows the prior
    # blanket auth fail-open (issues #4375/#4376) for the ownership-read path
    # only; release's fail-open and the SHA-gate backstop are unchanged.
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo
    try:
        assert_gh_authenticated()
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 3
        if code not in (3, 4):
            raise
        return _handle_unreachable_auth(args, code, output_format, owner, repo)

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
        "local_head_sha": result.local_head_sha,
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

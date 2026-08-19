# taste-lint: ignore file-size
# This test module covers ADR-076 Phase 1 (lease acquire/release/renew/status),
# security must_fix items #6-8, CLI exit codes, and mutation-proven defect fixes
# for issues #4375, #4376. Splitting it would scatter related ADR-076 scenarios
# across files with no cohesion gain; the line count is test coverage, not debt.
"""Tests for pr_autofix_lease.py (ADR-076 Phase 1, local-only).

The script is the advisory, fail-open branch-ownership lease that local
pr-autofix acquires before fixing review feedback on a PR and releases when
done. The lease lives in `<!-- PR-AUTOFIX-LEASE -->` marker comments on the
PR timeline (ADR-076 part 1); the latest valid marker wins. The lease never
gates a push; the Force-Push Safety SHA gate is the only hard boundary.

Coverage maps to ADR-076 Implementation Notes Phase 1 pytest list:
    - live lease held by another owner returns SKIP
    - expired lease returns ACT and overwrites
    - missing lease returns ACT
    - malformed lease returns ACT and overwrites (treated as "no live lease")
    - self-renewal of own live lease returns ACT and extends expires_at
    - store error returns ACT (fail-open)
plus the three debate-log security must_fix items:
    - #6 reader-clock MAX_TTL: far-future forgery reads as "no live lease"
    - #7 trusted self-renew: verified user.login plus session identity
    - #8 bounded scan: at most MAX_SCAN comments parsed
plus the TESTING-RIGOR matrix (positive, negative, edge, every branch, CLI
exit codes) with all I/O mocked.

Exit codes follow the sibling check_pr_live_state.py ACT/SKIP convention,
within the ADR-035 numeric range:
    0 - ACT (proceed)
    1 - SKIP (another live lease holds the branch)
    2 - PR not found / usage error
    3 - External error
    4 - Auth error
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import logging
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Import the script via importlib (not a package), matching sibling tests.
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1] / ".claude" / "skills" / "github" / "scripts" / "pr"
)


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("pr_autofix_lease")

LEASE_MARKER = _mod.LEASE_MARKER
TTL = _mod.TTL
MAX_TTL = _mod.MAX_TTL
MAX_SCAN = _mod.MAX_SCAN
TOMBSTONE_OWNER = _mod.TOMBSTONE_OWNER
Lease = _mod.Lease
LeaseStoreError = _mod.LeaseStoreError
parse_lease_block = _mod.parse_lease_block
select_authoritative_lease = _mod.select_authoritative_lease
classify_acquire = _mod.classify_acquire
render_lease_comment = _mod.render_lease_comment
build_claim = _mod.build_claim
build_tombstone = _mod.build_tombstone
acquire = _mod.acquire
release = _mod.release
status = _mod.status
build_parser = _mod.build_parser
main = _mod.main


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 6, 19, 12, 0, 0, tzinfo=UTC)
_SHA = "a" * 40
_CLAIM_ID = "1" * 32
_OWNER = "local:pr-autofix"
_SESSION = "session-2587"
_AUTHOR = "octocat"  # verified GitHub comment author (user.login)


def _rfc(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _body(
    owner: str = _OWNER,
    session: str = _SESSION,
    acquired: datetime | None = None,
    expires: datetime | None = None,
    base_sha: str = _SHA,
    claim_id: str = _CLAIM_ID,
    marker: bool = True,
) -> str:
    acquired = acquired or _NOW
    expires = expires or (_NOW + TTL)
    head = f"{LEASE_MARKER}\n" if marker else ""
    claim_line = f"claim_id: {claim_id}\n" if claim_id else ""
    return (
        f"{head}"
        f"owner: {owner}\n"
        f"session: {session}\n"
        f"acquired_at: {_rfc(acquired)}\n"
        f"expires_at: {_rfc(expires)}\n"
        f"base_sha: {base_sha}\n"
        f"{claim_line}"
    )


def _comment(body: str, created: str, author: str = _AUTHOR) -> dict:
    """A PR issue comment. ``author`` populates the verified ``user.login``."""
    return {"body": body, "created_at": created, "user": {"login": author}}


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def _now_iso() -> str:
    return _rfc(datetime.now(UTC))


def _live_held_body(owner: str = _OWNER, session: str = _SESSION) -> str:
    # A lease window that is live relative to the REAL clock, for the main()
    # exit-code tests, which do not inject `now`.
    real_now = datetime.now(UTC)
    return _body(
        owner=owner,
        session=session,
        acquired=real_now,
        expires=real_now + timedelta(minutes=10),
    )


@pytest.fixture(autouse=True)
def _isolate_ownership_token_dir(tmp_path, monkeypatch):
    """Redirect the durable ownership token at a per-test temp directory.

    acquire() writes a token on a confirmed ACT and release() clears it. This
    autouse fixture keeps those writes out of the developer's real XDG state
    dir and gives every test an isolated token namespace (issue #4966 HIGH).
    """
    monkeypatch.setenv("PR_AUTOFIX_LEASE_STATE_DIR", str(tmp_path / "lease-tokens"))
    yield


def _write_token(
    owner: str = _OWNER,
    session: str = _SESSION,
    pr: int = 1,
    now: datetime | None = None,
    repo_owner: str = "o",
    repo: str = "r",
) -> None:
    _mod._write_ownership_token(owner, session, repo_owner, repo, pr, now or datetime.now(UTC))


def _has_token(
    owner: str = _OWNER,
    session: str = _SESSION,
    pr: int = 1,
    now: datetime | None = None,
    repo_owner: str = "o",
    repo: str = "r",
) -> bool:
    return _mod._has_valid_ownership_token(
        owner, session, repo_owner, repo, pr, now or datetime.now(UTC)
    )


# ===========================================================================
# parse_lease_block: positive
# ===========================================================================


class TestParsePositive:
    def test_parses_well_formed_live_lease(self):
        lease = parse_lease_block(_body())
        assert lease is not None
        assert lease.owner == _OWNER
        assert lease.session == _SESSION
        assert lease.base_sha == _SHA
        assert lease.is_live(_NOW)

    def test_parse_leaves_author_empty(self):
        # parse_lease_block sees only the body; the verified author is stamped
        # later by select_authoritative_lease (ADR-076 part 4).
        lease = parse_lease_block(_body())
        assert lease is not None
        assert lease.author == ""

    def test_round_trips_through_render(self):
        original = build_claim(_OWNER, _SESSION, _SHA, _NOW)
        reparsed = parse_lease_block(render_lease_comment(original))
        assert reparsed == original

    def test_tombstone_parses_and_is_not_live(self):
        tomb = build_tombstone(_OWNER, _SESSION, _NOW)
        lease = parse_lease_block(render_lease_comment(tomb))
        assert lease is not None
        assert lease.owner == TOMBSTONE_OWNER
        assert not lease.is_live(_NOW)


# ===========================================================================
# parse_lease_block: negative and edge (malformed -> None)
# ===========================================================================


class TestParseNegative:
    def test_no_marker_returns_none(self):
        assert parse_lease_block(_body(marker=False)) is None

    def test_empty_body_returns_none(self):
        assert parse_lease_block("") is None

    def test_missing_required_key_returns_none(self):
        body = f"{LEASE_MARKER}\nowner: {_OWNER}\nsession: {_SESSION}\n"
        assert parse_lease_block(body) is None

    def test_unknown_owner_returns_none(self):
        assert parse_lease_block(_body(owner="attacker:evil")) is None

    def test_unknown_tombstone_target_owner_returns_none(self):
        body = render_lease_comment(build_tombstone(_OWNER, _SESSION, _NOW))
        assert parse_lease_block(f"{body}target_owner: attacker:evil\n") is None

    def test_invalid_claim_id_returns_none(self):
        assert parse_lease_block(_body(claim_id="not-a-claim-id")) is None

    def test_non_hex_base_sha_returns_none(self):
        assert parse_lease_block(_body(base_sha="not-a-sha")) is None

    def test_short_base_sha_returns_none(self):
        assert parse_lease_block(_body(base_sha="a" * 39)) is None

    def test_non_rfc3339_timestamp_returns_none(self):
        body = (
            f"{LEASE_MARKER}\nowner: {_OWNER}\nsession: {_SESSION}\n"
            f"acquired_at: yesterday\nexpires_at: {_rfc(_NOW + TTL)}\n"
            f"base_sha: {_SHA}\n"
        )
        assert parse_lease_block(body) is None

    def test_non_utc_offset_timestamp_returns_none(self):
        body = (
            f"{LEASE_MARKER}\nowner: {_OWNER}\nsession: {_SESSION}\n"
            f"acquired_at: 2026-06-19T12:00:00+05:00\n"
            f"expires_at: 2026-06-19T12:05:00+05:00\nbase_sha: {_SHA}\n"
        )
        assert parse_lease_block(body) is None

    def test_expires_beyond_max_ttl_returns_none(self):
        # ADR-076 Security: an internally-inconsistent over-extended marker
        # (expires_at > acquired_at + MAX_TTL) is treated as malformed.
        far = _NOW + MAX_TTL + timedelta(minutes=1)
        assert parse_lease_block(_body(expires=far)) is None

    def test_expires_exactly_at_max_ttl_boundary_parses(self):
        # Edge: expires_at == acquired_at + MAX_TTL is the allowed maximum.
        lease = parse_lease_block(_body(expires=_NOW + MAX_TTL))
        assert lease is not None


# ===========================================================================
# Lease.is_live branches (incl. reader-clock MAX_TTL, must_fix #6)
# ===========================================================================


class TestIsLive:
    def test_future_expiry_non_tombstone_is_live(self):
        lease = build_claim(_OWNER, _SESSION, _SHA, _NOW)
        assert lease.is_live(_NOW)

    def test_expired_lease_is_not_live(self):
        lease = build_claim(_OWNER, _SESSION, _SHA, _NOW)
        assert not lease.is_live(_NOW + TTL + timedelta(seconds=1))

    def test_exact_expiry_instant_is_not_live(self):
        lease = build_claim(_OWNER, _SESSION, _SHA, _NOW)
        # expires_at == now is not "in the future".
        assert not lease.is_live(_NOW + TTL)

    def test_tombstone_is_never_live(self):
        tomb = build_tombstone(_OWNER, _SESSION, _NOW)
        assert not tomb.is_live(_NOW)

    # --- must_fix #6: reader-clock MAX_TTL bound ---------------------------

    def test_far_future_forgery_reads_as_not_live(self):
        # A forged marker whose acquired_at AND expires_at are both far in the
        # future is internally consistent (expires_at == acquired_at + TTL) so
        # it parses, but is_live judged at the reader's clock rejects it
        # because expires_at > now + MAX_TTL. Without this, the lease would
        # read as live indefinitely (CWE-400 / CWE-367).
        far_acquired = _NOW + timedelta(days=1000)
        forged = parse_lease_block(_body(acquired=far_acquired, expires=far_acquired + TTL))
        assert forged is not None  # parses: internally consistent
        assert not forged.is_live(_NOW)  # but not live at the reader's clock

    def test_expiry_just_beyond_reader_max_ttl_is_not_live(self):
        # expires_at = now + MAX_TTL + 1s, judged at the reader's now, is dead.
        over = Lease(
            owner=_OWNER,
            session=_SESSION,
            acquired_at=_NOW,
            expires_at=_NOW + MAX_TTL + timedelta(seconds=1),
            base_sha=_SHA,
        )
        assert not over.is_live(_NOW)

    def test_expiry_exactly_at_reader_max_ttl_is_live(self):
        # Edge: expires_at == now + MAX_TTL is the inclusive upper bound.
        at_bound = Lease(
            owner=_OWNER,
            session=_SESSION,
            acquired_at=_NOW,
            expires_at=_NOW + MAX_TTL,
            base_sha=_SHA,
        )
        assert at_bound.is_live(_NOW)


# ===========================================================================
# select_authoritative_lease: latest-marker-wins, author-stamping, bounded scan
# ===========================================================================


class TestSelect:
    def test_empty_timeline_returns_none(self):
        assert select_authoritative_lease([]) is None

    def test_ignores_non_marker_comments(self):
        comments = [_comment("just a normal review comment", "2026-06-19T11:00:00Z")]
        assert select_authoritative_lease(comments) is None

    def test_latest_marker_wins(self):
        old = _comment(_body(session="session-1", expires=_NOW + TTL), "2026-06-19T11:00:00Z")
        new = _comment(_body(session="session-2", expires=_NOW + TTL), "2026-06-19T11:30:00Z")
        chosen = select_authoritative_lease([old, new])
        assert chosen is not None
        assert chosen.session == "session-2"

    def test_skips_malformed_marker_and_uses_valid_one(self):
        valid = _comment(_body(session="good"), "2026-06-19T11:00:00Z")
        malformed = _comment(f"{LEASE_MARKER}\nowner: attacker:x\n", "2026-06-19T11:30:00Z")
        chosen = select_authoritative_lease([valid, malformed])
        assert chosen is not None
        assert chosen.session == "good"

    def test_latest_tombstone_wins_over_earlier_live(self):
        live = _comment(_body(), "2026-06-19T11:00:00Z")
        tomb = _comment(
            render_lease_comment(build_tombstone(_OWNER, _SESSION, _NOW, _SHA, _CLAIM_ID)),
            "2026-06-19T11:30:00Z",
        )
        chosen = select_authoritative_lease([live, tomb])
        assert chosen is not None
        assert not chosen.is_live(_NOW)

    def test_stale_tombstone_does_not_clear_newer_session(self):
        first = _comment(_body(session="session-a"), "2026-06-19T11:00:00Z")
        second = _comment(_body(session="session-b"), "2026-06-19T11:30:00Z")
        stale_tombstone = _comment(
            render_lease_comment(build_tombstone(_OWNER, "session-a", _NOW)),
            "2026-06-19T11:45:00Z",
        )
        chosen = select_authoritative_lease([first, second, stale_tombstone])
        assert chosen is not None
        assert chosen.session == "session-b"
        assert chosen.owner == _OWNER

    def test_tombstone_does_not_clear_foreign_claim_with_same_session(self):
        created = "2026-06-19T11:00:00Z"
        first = _comment(_body(session="shared"), created, author=_AUTHOR)
        foreign = _comment(
            _body(owner="remote:coderabbit-autofix", session="shared"),
            created,
            author="coderabbit[bot]",
        )
        stale_tombstone = _comment(
            render_lease_comment(build_tombstone(_OWNER, "shared", _NOW, _SHA, _CLAIM_ID)),
            created,
            author=_AUTHOR,
        )
        chosen = select_authoritative_lease([first, foreign, stale_tombstone])
        assert chosen is not None
        assert chosen.owner == "remote:coderabbit-autofix"
        assert chosen.author == "coderabbit[bot]"

    def test_tombstone_does_not_clear_new_claim_with_same_identity(self):
        first = _comment(_body(claim_id="1" * 32), "2026-06-19T11:00:00Z")
        renewed = _comment(_body(claim_id="2" * 32), "2026-06-19T11:30:00Z")
        stale_tombstone = _comment(
            render_lease_comment(build_tombstone(_OWNER, _SESSION, _NOW, _SHA, "1" * 32)),
            "2026-06-19T11:45:00Z",
        )
        chosen = select_authoritative_lease([first, renewed, stale_tombstone])
        assert chosen is not None
        assert chosen.claim_id == "2" * 32

    # --- must_fix #7: verified author is stamped from user.login -----------

    def test_stamps_verified_author_from_user_login(self):
        c = _comment(_body(), "2026-06-19T11:00:00Z", author="real-holder")
        chosen = select_authoritative_lease([c])
        assert chosen is not None
        assert chosen.author == "real-holder"

    def test_missing_user_object_yields_empty_author(self):
        c = {"body": _body(), "created_at": "2026-06-19T11:00:00Z"}  # no user key
        chosen = select_authoritative_lease([c])
        assert chosen is not None
        assert chosen.author == ""

    def test_malformed_user_object_yields_empty_author(self):
        c = {"body": _body(), "created_at": "2026-06-19T11:00:00Z", "user": "not-a-dict"}
        chosen = select_authoritative_lease([c])
        assert chosen is not None
        assert chosen.author == ""

    # --- must_fix #8: bounded scan ----------------------------------------

    def test_scan_is_bounded_to_latest_max_scan_comments(self):
        # The authoritative live marker sits at the very front (oldest) of a
        # timeline longer than MAX_SCAN. Because only the latest MAX_SCAN are
        # scanned, that old marker is NOT seen, so the lock reads as free.
        old_live = _comment(_body(session="ancient"), "2026-06-19T00:00:00Z")
        filler = [
            _comment(
                "noise comment",
                _rfc(datetime(2026, 6, 19, 10, tzinfo=UTC) + timedelta(minutes=i)),
            )
            for i in range(MAX_SCAN)
        ]
        chosen = select_authoritative_lease([old_live, *filler])
        assert chosen is None

    def test_recent_marker_within_window_is_found(self):
        # A marker within the latest MAX_SCAN comments IS found.
        filler = [
            _comment(
                "noise comment",
                _rfc(datetime(2026, 6, 19, 9, tzinfo=UTC) + timedelta(minutes=i)),
            )
            for i in range(MAX_SCAN - 1)
        ]
        recent = _comment(_body(session="recent"), "2026-06-19T11:59:00Z")
        chosen = select_authoritative_lease([*filler, recent])
        assert chosen is not None
        assert chosen.session == "recent"


# ===========================================================================
# classify_acquire: every verdict branch (trusted author and session)
# ===========================================================================


def _stamped(lease, author: str):
    from dataclasses import replace

    return replace(lease, author=author)


class TestClassifyAcquire:
    def test_no_lease_returns_act_free(self):
        verdict = classify_acquire(None, _AUTHOR, _SESSION, _NOW)
        assert verdict == {"action": "ACT", "reason": "free"}

    def test_expired_lease_returns_act_free(self):
        expired = build_claim(_OWNER, _SESSION, _SHA, _NOW - TTL - timedelta(minutes=1))
        verdict = classify_acquire(_stamped(expired, "someone"), _AUTHOR, _SESSION, _NOW)
        assert verdict["action"] == "ACT"
        assert verdict["reason"] == "free"

    def test_live_lease_other_author_returns_skip(self):
        held = build_claim("remote:coderabbit-autofix", "ci-99", _SHA, _NOW)
        held = _stamped(held, "coderabbit[bot]")
        verdict = classify_acquire(held, _AUTHOR, _SESSION, _NOW)
        assert verdict["action"] == "SKIP"
        assert verdict["reason"] == "held-by:remote:coderabbit-autofix"
        assert verdict["expires_at"] == _rfc(_NOW + TTL)

    def test_live_lease_same_author_returns_self_renew(self):
        mine = build_claim(_OWNER, _SESSION, _SHA, _NOW)
        mine = _stamped(mine, _AUTHOR)
        verdict = classify_acquire(mine, _AUTHOR, _SESSION, _NOW)
        assert verdict == {"action": "ACT", "reason": "self-renew"}

    def test_live_lease_same_author_different_session_returns_skip(self):
        mine = build_claim(_OWNER, "other-session", _SHA, _NOW)
        mine = _stamped(mine, _AUTHOR)
        verdict = classify_acquire(mine, _AUTHOR, _SESSION, _NOW)
        assert verdict["action"] == "SKIP"

    def test_self_renew_keys_on_author_not_body_owner(self):
        # must_fix #7: a forged body that copies a legitimate owner/session but
        # was posted by a DIFFERENT credential must NOT be treated as the
        # acting loop's own lease. The verified author differs, so it is SKIP.
        forged = build_claim(_OWNER, _SESSION, _SHA, _NOW)  # same body owner/session
        forged = _stamped(forged, "attacker-login")  # but a foreign author
        verdict = classify_acquire(forged, _AUTHOR, _SESSION, _NOW)
        assert verdict["action"] == "SKIP"

    def test_empty_acting_author_never_self_renews(self):
        # An unresolved acting login ("") can only claim a free lock, never
        # self-renew a foreign one, even one whose author is also "".
        mine = _stamped(build_claim(_OWNER, _SESSION, _SHA, _NOW), "")
        verdict = classify_acquire(mine, "", _SESSION, _NOW)
        assert verdict["action"] == "SKIP"

    def test_far_future_forged_lease_classifies_as_free(self):
        # must_fix #6 wired through classify: a far-future forgery is not live
        # at the reader's clock, so acquire treats it as free and ACTs.
        far_acquired = _NOW + timedelta(days=1000)
        forged = parse_lease_block(_body(acquired=far_acquired, expires=far_acquired + TTL))
        assert forged is not None
        forged = _stamped(forged, "attacker-login")
        verdict = classify_acquire(forged, _AUTHOR, _SESSION, _NOW)
        assert verdict == {"action": "ACT", "reason": "free"}


# ===========================================================================
# build_tombstone
# ===========================================================================


class TestTombstone:
    def test_tombstone_owner_is_none(self):
        tomb = build_tombstone(_OWNER, _SESSION, _NOW)
        assert tomb.owner == TOMBSTONE_OWNER

    def test_tombstone_expires_in_the_past(self):
        tomb = build_tombstone(_OWNER, _SESSION, _NOW)
        assert tomb.expires_at < _NOW
        assert not tomb.is_live(_NOW)


# ===========================================================================
# acquire use case (I/O mocked)
# ===========================================================================


_LEASE_TIMELINE: list[dict] | None = None


def _patch_list(comments):
    global _LEASE_TIMELINE
    _LEASE_TIMELINE = list(comments)

    def _list(*args, **kwargs):
        return _LEASE_TIMELINE

    return patch.object(_mod, "list_lease_comments", side_effect=_list)


def _patch_post(author: str = _AUTHOR, created_at: datetime | None = None):
    def _capture(owner, repo, pr, body):
        if _LEASE_TIMELINE is not None:
            stamp = _rfc(created_at or datetime.now(UTC))
            _LEASE_TIMELINE.append(_comment(body, stamp, author=author))

    return patch.object(_mod, "post_lease_comment", side_effect=_capture)


@contextlib.contextmanager
def _patch_head(sha=_SHA, pr_head=_SHA, *, pr_state="OPEN", pr_merged=False):
    """Patch both SHA reads acquire performs.

    ``sha`` is what the caller's checkout reports at HEAD; ``pr_head`` is
    what GitHub reports as the PR head. They are separate inputs because
    the defect in #4357 was acquire publishing the first as if it were the
    second. ``pr_state``/``pr_merged`` default to an open, unmerged PR
    (issue #5165); pass ``pr_state="CLOSED"`` or ``pr_merged=True`` to
    exercise the renew/pr-closed path.
    """
    with (
        patch.object(_mod, "_git_head_sha", return_value=sha),
        patch.object(
            _mod,
            "_pr_head_state",
            return_value=_mod._PrHeadState(sha=pr_head, state=pr_state, merged=pr_merged),
        ),
    ):
        yield


def _patch_login(login=_AUTHOR):
    return patch.object(_mod, "_gh_authenticated_login", return_value=login)


class TestAcquire:
    def test_acquire_on_free_pr_returns_act(self):
        with _patch_list([]), _patch_post() as post, _patch_head(), _patch_login():
            result = acquire(_OWNER, _SESSION, "o", "r", 1, now=_NOW)
        assert result.action == "ACT"
        assert result.reason == "free"
        post.assert_called_once()

    def test_acquire_loses_the_post_race_returns_skip(self):
        competitor = _comment(
            _body(owner="remote:coderabbit-autofix", session="ci-9"),
            "2026-06-19T12:00:01Z",
            author="coderabbit[bot]",
        )
        with (
            patch.object(_mod, "list_lease_comments", side_effect=[[], [competitor]]),
            patch.object(_mod, "post_lease_comment", return_value=None) as post,
            _patch_head(),
            _patch_login(),
        ):
            result = acquire(_OWNER, _SESSION, "o", "r", 1, now=_NOW)
        assert result.action == "SKIP"
        assert result.reason.startswith("held-by:")
        post.assert_called_once()

    def test_acquire_on_held_pr_returns_skip_without_posting(self):
        held = _comment(
            _body(owner="remote:coderabbit-autofix", session="ci-1"),
            "2026-06-19T11:59:00Z",
            author="coderabbit[bot]",
        )
        with _patch_list([held]), _patch_post() as post, _patch_head(), _patch_login():
            result = acquire(_OWNER, _SESSION, "o", "r", 1, now=_NOW)
        assert result.action == "SKIP"
        assert result.reason.startswith("held-by:")
        post.assert_not_called()

    def test_acquire_over_expired_lease_returns_act_and_posts(self):
        stale = _comment(
            _body(
                acquired=_NOW - timedelta(hours=2),
                expires=_NOW - timedelta(hours=1, minutes=45),
            ),
            "2026-06-19T10:00:00Z",
        )
        with _patch_list([stale]), _patch_post() as post, _patch_head(), _patch_login():
            result = acquire("ci:autofix-workflow", "ci-7", "o", "r", 1, now=_NOW)
        assert result.action == "ACT"
        post.assert_called_once()

    def test_acquire_over_malformed_lease_returns_act_and_posts(self):
        bad = _comment(f"{LEASE_MARKER}\nowner: attacker:x\nbogus", "2026-06-19T11:59:00Z")
        with _patch_list([bad]), _patch_post() as post, _patch_head(), _patch_login():
            result = acquire(_OWNER, _SESSION, "o", "r", 1, now=_NOW)
        assert result.action == "ACT"
        assert result.reason == "free"
        post.assert_called_once()

    def test_self_renew_returns_act_when_author_matches(self):
        mine = _comment(
            _body(owner=_OWNER, session=_SESSION), "2026-06-19T11:59:00Z", author=_AUTHOR
        )
        with _patch_list([mine]), _patch_post() as post, _patch_head(), _patch_login(_AUTHOR):
            result = acquire(_OWNER, _SESSION, "o", "r", 1, now=_NOW)
        assert result.action == "ACT"
        assert result.reason == "self-renew"
        post.assert_called_once()

    def test_self_renew_rotates_claim_id(self):
        mine = _comment(_body(), "2026-06-19T11:59:00Z", author=_AUTHOR)
        post, bodies = _captured_post()
        with _patch_list([mine]), post, _patch_head(), _patch_login(_AUTHOR):
            result = acquire(_OWNER, _SESSION, "o", "r", 1, now=_NOW)
        renewed = parse_lease_block(bodies[0])
        assert result.reason == "self-renew"
        assert renewed is not None
        assert renewed.claim_id != _CLAIM_ID

    def test_forged_body_by_foreign_author_returns_skip(self):
        # must_fix #7 end-to-end: a comment whose BODY claims our owner/session
        # but was posted by a different login is a foreign lease -> SKIP.
        forged = _comment(
            _body(owner=_OWNER, session=_SESSION),
            "2026-06-19T11:59:00Z",
            author="attacker-login",
        )
        with _patch_list([forged]), _patch_post() as post, _patch_head(), _patch_login(_AUTHOR):
            result = acquire(_OWNER, _SESSION, "o", "r", 1, now=_NOW)
        assert result.action == "SKIP"
        post.assert_not_called()

    def test_acquire_passes_injected_acting_author(self):
        # The acting_author override bypasses _gh_authenticated_login.
        mine = _comment(_body(), "2026-06-19T11:59:00Z", author="injected-login")
        with _patch_list([mine]), _patch_post(author="injected-login"), _patch_head():
            result = acquire(
                _OWNER, _SESSION, "o", "r", 1, now=_NOW, acting_author="injected-login"
            )
        assert result.action == "ACT"
        assert result.reason == "self-renew"

    def test_acquire_over_far_future_forgery_returns_act(self):
        # must_fix #6 end-to-end: a far-future forged lease is not live at the
        # reader's clock, so acquire treats it as free and posts a real claim.
        far_acquired = _NOW + timedelta(days=1000)
        forged = _comment(
            _body(acquired=far_acquired, expires=far_acquired + TTL),
            "2026-06-19T11:59:00Z",
            author="attacker-login",
        )
        with _patch_list([forged]), _patch_post() as post, _patch_head(), _patch_login():
            result = acquire(_OWNER, _SESSION, "o", "r", 1, now=_NOW)
        assert result.action == "ACT"
        assert result.reason == "free"
        post.assert_called_once()

    def test_store_read_error_fails_closed_to_skip(self):
        # Issue #4966: an unreadable store leaves ownership unknown, so acquire
        # must decline (SKIP) instead of claiming a branch a foreign live lease
        # may hold. It must not post a claim on that blind path.
        with (
            patch.object(_mod, "list_lease_comments", side_effect=LeaseStoreError("boom")),
            _patch_post() as post,
            _patch_head(),
            _patch_login(),
        ):
            result = acquire(_OWNER, _SESSION, "o", "r", 1, now=_NOW)
        assert result.action == "SKIP"
        assert result.reason == "lease-store-unavailable"
        post.assert_not_called()

    def test_renewing_store_read_error_with_token_fails_open_to_act(self):
        # Issue #4966 HIGH: a renew fails open through an unreadable store ONLY
        # when a durable ownership token proves this session won the lease at
        # an earlier acquire. The token, not the "renew" command name, is the
        # proof. It extends in place; the SHA gate stays authoritative (#4376).
        _write_token(now=_NOW)
        with (
            patch.object(_mod, "list_lease_comments", side_effect=LeaseStoreError("boom")),
            _patch_post() as post,
            _patch_head(),
            _patch_login(),
        ):
            result = acquire(_OWNER, _SESSION, "o", "r", 1, now=_NOW, renewing=True)
        assert result.action == "ACT"
        assert result.reason == "lease-store-unavailable"
        post.assert_not_called()

    def test_renewing_store_read_error_without_token_fails_closed_to_skip(self):
        # Issue #4966 HIGH repro: `renew --session never-acquired` on an
        # unreadable store. No ownership token exists, so the command name is
        # not proof of ownership and the renew fails CLOSED to SKIP.
        with (
            patch.object(_mod, "list_lease_comments", side_effect=LeaseStoreError("boom")),
            _patch_post() as post,
            _patch_head(),
            _patch_login(),
        ):
            result = acquire(_OWNER, _SESSION, "o", "r", 1, now=_NOW, renewing=True)
        assert result.action == "SKIP"
        assert result.reason == "lease-store-unavailable"
        post.assert_not_called()

    def test_store_write_error_on_fresh_acquire_fails_closed_to_skip(self):
        # Issue #4966 CRITICAL: a fresh acquire that reads free but cannot
        # PUBLISH its claim fails CLOSED. Two sessions can both read free and
        # both fail to POST; if this failed open both would ACT (the original
        # race one step later). ACT requires a published claim.
        with (
            _patch_list([]),
            patch.object(_mod, "post_lease_comment", side_effect=LeaseStoreError("boom")),
            _patch_head(),
            _patch_login(),
        ):
            result = acquire(_OWNER, _SESSION, "o", "r", 1, now=_NOW)
        assert result.action == "SKIP"
        assert result.reason == "lease-store-unavailable"

    def test_store_write_error_on_self_renew_fails_open_to_act(self):
        # A self-renew whose read CONFIRMED a still-live self-owned lease keeps
        # that prior claim when the TTL-extension write fails: it fails open to
        # ACT (issue #4376). Contrast with the fresh-acquire write failure.
        mine = _comment(
            _body(owner=_OWNER, session=_SESSION), "2026-06-19T11:59:00Z", author=_AUTHOR
        )
        with (
            _patch_list([mine]),
            patch.object(_mod, "post_lease_comment", side_effect=LeaseStoreError("boom")),
            _patch_head(),
            _patch_login(_AUTHOR),
        ):
            result = acquire(_OWNER, _SESSION, "o", "r", 1, now=_NOW)
        assert result.action == "ACT"
        assert result.reason == "lease-store-unavailable"

    def test_post_claim_reread_error_on_fresh_acquire_fails_closed_to_skip(self):
        # Issue #4966 CRITICAL (reviewer UNCOVERED gap): a fresh acquire posts
        # its claim, then the authoritative RE-READ fails. It cannot confirm it
        # won the post race, so it fails CLOSED to SKIP. Two sessions that both
        # read free and both lose the re-read must not both proceed.
        with (
            patch.object(_mod, "list_lease_comments", side_effect=[[], LeaseStoreError("boom")]),
            patch.object(_mod, "post_lease_comment", return_value=None) as post,
            _patch_head(),
            _patch_login(),
        ):
            result = acquire(_OWNER, _SESSION, "o", "r", 1, now=_NOW)
        assert result.action == "SKIP"
        assert result.reason == "lease-store-unavailable"
        post.assert_called_once()

    def test_post_claim_reread_error_on_self_renew_fails_open_to_act(self):
        # A self-renew that cannot re-read still holds the confirmed-live prior
        # claim; no competitor can steal a live lease, so it fails open to ACT
        # (issue #4376). Contrast with the fresh-acquire re-read failure.
        mine = _comment(
            _body(owner=_OWNER, session=_SESSION), "2026-06-19T11:59:00Z", author=_AUTHOR
        )
        with (
            patch.object(
                _mod, "list_lease_comments", side_effect=[[mine], LeaseStoreError("boom")]
            ),
            patch.object(_mod, "post_lease_comment", return_value=None),
            _patch_head(),
            _patch_login(_AUTHOR),
        ):
            result = acquire(_OWNER, _SESSION, "o", "r", 1, now=_NOW)
        assert result.action == "ACT"
        assert result.reason == "lease-store-unavailable"

    def test_confirmed_acquire_writes_ownership_token(self):
        # A confirmed ACT persists the durable ownership token a later renew
        # relies on to fail open through a store outage (issue #4966 HIGH).
        with _patch_list([]), _patch_post(), _patch_head(), _patch_login():
            result = acquire(_OWNER, _SESSION, "o", "r", 1, now=_NOW)
        assert result.action == "ACT"
        assert _has_token(now=_NOW)

    def test_store_write_error_on_near_expiry_self_renew_fails_closed_to_skip(self):
        # A self-renew whose confirmed-live prior claim would expire inside the
        # store-I/O window fails CLOSED on a write failure. A partial outage
        # (this write fails while a competitor can still read) could let a fresh
        # session acquire the branch mid-operation, so extending the claim is
        # unsafe (issue #4966 review). Contrast with the ample-margin self-renew.
        near = _NOW + timedelta(seconds=30)
        mine = _comment(
            _body(owner=_OWNER, session=_SESSION, expires=near),
            "2026-06-19T11:59:00Z",
            author=_AUTHOR,
        )
        with (
            _patch_list([mine]),
            patch.object(_mod, "post_lease_comment", side_effect=LeaseStoreError("boom")),
            _patch_head(),
            _patch_login(_AUTHOR),
        ):
            result = acquire(_OWNER, _SESSION, "o", "r", 1, now=_NOW)
        assert result.action == "SKIP"
        assert result.reason == "lease-store-unavailable"

    def test_reread_error_on_near_expiry_self_renew_fails_closed_to_skip(self):
        # Same boundary on the post-claim re-read path: a self-renew whose prior
        # claim could expire during the store I/O fails CLOSED to SKIP rather
        # than fail open on a claim that may already be dead (issue #4966
        # review).
        near = _NOW + timedelta(seconds=30)
        mine = _comment(
            _body(owner=_OWNER, session=_SESSION, expires=near),
            "2026-06-19T11:59:00Z",
            author=_AUTHOR,
        )
        with (
            patch.object(
                _mod, "list_lease_comments", side_effect=[[mine], LeaseStoreError("boom")]
            ),
            patch.object(_mod, "post_lease_comment", return_value=None),
            _patch_head(),
            _patch_login(_AUTHOR),
        ):
            result = acquire(_OWNER, _SESSION, "o", "r", 1, now=_NOW)
        assert result.action == "SKIP"
        assert result.reason == "lease-store-unavailable"


class TestOwnershipTokenRepoIsolation:
    """The durable ownership token is scoped to one repository.

    The token directory is global (XDG state), so the repository identity must
    be part of the key and payload. Otherwise a token for PR #1 in repo A would
    authorize a token-backed renew of PR #1 in repo B during a store outage
    (issue #4966 review finding).
    """

    def test_token_from_other_repo_does_not_satisfy_check(self):
        # Same owner, session, and PR number, different repository: the token
        # written for repo A must NOT prove ownership in repo B.
        _write_token(pr=1, repo_owner="octo", repo="alpha", now=_NOW)
        assert _has_token(pr=1, repo_owner="octo", repo="alpha", now=_NOW)
        assert not _has_token(pr=1, repo_owner="octo", repo="beta", now=_NOW)
        assert not _has_token(pr=1, repo_owner="acme", repo="alpha", now=_NOW)

    def test_token_path_differs_by_repository(self):
        # The hashed key includes the repository, so two repositories map to
        # two distinct token files even for the same (owner, session, pr).
        path_a = _mod._ownership_token_path(_OWNER, _SESSION, "octo", "alpha", 1)
        path_b = _mod._ownership_token_path(_OWNER, _SESSION, "octo", "beta", 1)
        assert path_a != path_b

    def test_token_payload_records_repository(self):
        # Defense in depth: the payload carries the repository identity so a
        # relocated or hash-colliding file still fails the field match.
        _write_token(pr=1, repo_owner="octo", repo="alpha", now=_NOW)
        path = _mod._ownership_token_path(_OWNER, _SESSION, "octo", "alpha", 1)
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        assert data["repo_owner"] == "octo"
        assert data["repo"] == "alpha"

    def test_case_variant_repository_maps_to_one_token_path(self):
        # GitHub owner/repo names are case-insensitive, so ``Octo/Repo`` and
        # ``octo/repo`` name one repository and must hash to one token path
        # (issue #4966 review).
        path_mixed = _mod._ownership_token_path(_OWNER, _SESSION, "Octo", "Repo", 1)
        path_lower = _mod._ownership_token_path(_OWNER, _SESSION, "octo", "repo", 1)
        assert path_mixed == path_lower

    def test_case_variant_release_revokes_the_acquire_token(self):
        # Acquire writes the token under one casing; a release under a different
        # casing must find and revoke that same token. Without normalization the
        # release computes a different path, misses the token, posts the
        # tombstone anyway, and leaves the original valid token able to
        # authorize a post-release fail-open renew (issue #4966 review).
        _write_token(pr=1, repo_owner="Octo", repo="Repo", now=_NOW)
        assert _has_token(pr=1, repo_owner="octo", repo="repo", now=_NOW)
        assert _mod._clear_ownership_token(_OWNER, _SESSION, "octo", "repo", 1) is True
        assert not _has_token(pr=1, repo_owner="Octo", repo="Repo", now=_NOW)

    def test_token_at_max_ttl_boundary_is_not_valid(self):
        # The freshness bound is strict (< MAX_TTL) to match Lease.is_live's
        # strict expiry (now < expires_at). A token exactly one TTL old
        # coincides with the instant the remote lease dies, so it must not
        # authorize a fail-open renew at that boundary (issue #4966 review).
        _write_token(pr=1, now=_NOW)
        assert _has_token(pr=1, now=_NOW + MAX_TTL) is False
        assert _has_token(pr=1, now=_NOW + MAX_TTL - timedelta(seconds=1)) is True

    def test_non_object_token_fails_closed_without_crashing(self):
        # A syntactically valid but non-object token (a JSON array) decodes
        # cleanly, then .get would raise AttributeError and crash the CLI during
        # the outage this fail-open path exists to survive. It must fail closed
        # to False instead (issue #4966 review).
        path = Path(_mod._ownership_token_path(_OWNER, _SESSION, "o", "r", 1))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[]", encoding="utf-8")
        assert _has_token(pr=1, now=_NOW) is False

    def test_scalar_token_fails_closed_without_crashing(self):
        # A bare JSON number is also a valid non-object token and must not crash
        # the field reads (issue #4966 review).
        path = Path(_mod._ownership_token_path(_OWNER, _SESSION, "o", "r", 1))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("42", encoding="utf-8")
        assert _has_token(pr=1, now=_NOW) is False

    def test_invalid_utf8_token_fails_closed_without_crashing(self):
        # A token file that is not valid UTF-8 raises UnicodeDecodeError during
        # the read. That is not a JSONDecodeError, so it must be caught
        # explicitly and treated as no proof of ownership (issue #4966 review).
        path = Path(_mod._ownership_token_path(_OWNER, _SESSION, "o", "r", 1))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\xff\xfe\x00\x01")
        assert _has_token(pr=1, now=_NOW) is False


# ===========================================================================
# base_sha provenance: the PR head, never the caller's checkout
# (issues #4357, #4375; ADR-076 part 1 and part 3 acquire step 1)
# ===========================================================================


_PR_HEAD = "b" * 40
_OTHER_CHECKOUT = "c" * 40


def _captured_post():
    """Patch post_lease_comment and hand back the bodies it was given."""
    bodies: list[str] = []

    def _capture(owner, repo, pr, body):
        bodies.append(body)
        if _LEASE_TIMELINE is not None:
            _LEASE_TIMELINE.append(_comment(body, _now_iso(), author=_AUTHOR))

    return patch.object(_mod, "post_lease_comment", side_effect=_capture), bodies


class TestBaseShaProvenance:
    def test_base_sha_is_the_pr_head_not_the_local_checkout(self):
        # The discriminating input: acquire runs from a checkout whose HEAD
        # is NOT the PR head (the #4294 coordinator-on-main case). The
        # pre-fix code published the local SHA here.
        post, bodies = _captured_post()
        with (
            _patch_list([]),
            post,
            _patch_head(sha=_OTHER_CHECKOUT, pr_head=_PR_HEAD),
            _patch_login(),
        ):
            result = acquire(_OWNER, _SESSION, "o", "r", 1, now=_NOW)
        assert result.base_sha == _PR_HEAD
        published = parse_lease_block(bodies[0])
        assert published is not None
        assert published.base_sha == _PR_HEAD

    def test_mismatch_reports_both_shas(self):
        with (
            _patch_list([]),
            _patch_post(),
            _patch_head(sha=_OTHER_CHECKOUT, pr_head=_PR_HEAD),
            _patch_login(),
        ):
            result = acquire(_OWNER, _SESSION, "o", "r", 1, now=_NOW)
        assert result.local_head_sha == _OTHER_CHECKOUT
        assert result.base_sha == _PR_HEAD

    def test_mismatch_logs_both_shas(self, caplog):
        with caplog.at_level(logging.WARNING):
            with (
                _patch_list([]),
                _patch_post(),
                _patch_head(sha=_OTHER_CHECKOUT, pr_head=_PR_HEAD),
                _patch_login(),
            ):
                acquire(_OWNER, _SESSION, "o", "r", 1, now=_NOW)
        warnings = [rec.getMessage() for rec in caplog.records]
        assert any("lease_checkout_mismatch" in line for line in warnings)
        assert any(_OTHER_CHECKOUT in line and _PR_HEAD in line for line in warnings)

    def test_matching_checkout_logs_no_mismatch(self, caplog):
        with caplog.at_level(logging.WARNING):
            with (
                _patch_list([]),
                _patch_post(),
                _patch_head(sha=_PR_HEAD, pr_head=_PR_HEAD),
                _patch_login(),
            ):
                result = acquire(_OWNER, _SESSION, "o", "r", 1, now=_NOW)
        assert result.local_head_sha == _PR_HEAD
        assert not any("lease_checkout_mismatch" in rec.getMessage() for rec in caplog.records)

    def test_detached_or_missing_git_still_records_the_pr_head(self):
        # git unavailable (or a checkout git cannot resolve): the lease is
        # still correct, because base_sha never depended on git.
        with (
            _patch_list([]),
            _patch_post(),
            _patch_head(sha=None, pr_head=_PR_HEAD),
            _patch_login(),
        ):
            result = acquire(_OWNER, _SESSION, "o", "r", 1, now=_NOW)
        assert result.base_sha == _PR_HEAD
        assert result.local_head_sha is None

    def test_pr_head_read_failure_still_claims_a_free_lock(self):
        # The head read is freshness evidence, not the lock. Failing it open
        # would surrender mutual exclusion over a transient API error, so a
        # failure records the sentinel and the claim is still posted.
        with (
            patch.object(_mod, "_pr_head_state", side_effect=LeaseStoreError("api down")),
            patch.object(_mod, "_git_head_sha", return_value=_OTHER_CHECKOUT),
            _patch_list([]),
            _patch_post() as post,
            _patch_login(),
        ):
            result = acquire(_OWNER, _SESSION, "o", "r", 1, now=_NOW)
        assert result.action == "ACT"
        assert result.reason == "free"
        assert result.base_sha == "0" * 40
        assert result.local_head_sha == _OTHER_CHECKOUT
        post.assert_called_once()

    def test_pr_head_read_failure_cannot_steal_a_live_foreign_lease(self):
        # The regression this ordering exists to prevent: with both reads in
        # one fail-open block, a failed head read returned ACT without ever
        # reading the lease comments, so a live foreign lease was ignored.
        live = _comment(
            _body(owner="remote:coderabbit-autofix", session="ci-1"),
            "2026-06-19T11:59:00Z",
            author="coderabbit[bot]",
        )
        with (
            patch.object(_mod, "_pr_head_state", side_effect=LeaseStoreError("api down")),
            patch.object(_mod, "_git_head_sha", return_value=_OTHER_CHECKOUT),
            _patch_list([live]),
            _patch_post() as post,
            _patch_login(),
        ):
            result = acquire(_OWNER, _SESSION, "o", "r", 1, now=_NOW)
        assert result.action == "SKIP"
        post.assert_not_called()

    def test_store_read_failure_skips_without_pr_head(self):
        # Issue #4966: the ownership read now fails closed to SKIP. On that path
        # acquire never reaches the PR head read, so base_sha stays None and no
        # zero sentinel is fabricated for a branch it declined.
        with (
            _patch_head(sha=_OTHER_CHECKOUT, pr_head=_PR_HEAD),
            patch.object(_mod, "list_lease_comments", side_effect=LeaseStoreError("boom")),
            _patch_post(),
            _patch_login(),
        ):
            result = acquire(_OWNER, _SESSION, "o", "r", 1, now=_NOW)
        assert result.action == "SKIP"
        assert result.reason == "lease-store-unavailable"
        assert result.base_sha is None


# ===========================================================================
# release use case (idempotent, fail-open)
# ===========================================================================


class TestRelease:
    def test_release_writes_tombstone_and_returns_act(self):
        captured = {}

        def _capture(owner, repo, pr, body):
            captured["body"] = body

        held = _comment(_body(), "2026-06-19T11:59:00Z")
        with _patch_list([held]), patch.object(_mod, "post_lease_comment", side_effect=_capture):
            result = release(_OWNER, _SESSION, "o", "r", 1, now=_NOW, acting_author=_AUTHOR)
        assert result.action == "ACT"
        assert result.reason == "released"
        parsed = parse_lease_block(captured["body"])
        assert parsed is not None
        assert parsed.owner == TOMBSTONE_OWNER

    def test_release_is_idempotent_on_already_free_lock(self):
        with _patch_list([]), _patch_post() as post:
            result = release(_OWNER, _SESSION, "o", "r", 1, now=_NOW, acting_author=_AUTHOR)
        assert result.action == "ACT"
        assert result.reason == "already-free"
        post.assert_not_called()

    def test_expired_then_reacquired_lease_is_not_cleared_by_stale_session(self):
        expired = _comment(
            _body(
                session="session-a",
                acquired=_NOW - timedelta(minutes=30),
                expires=_NOW - timedelta(minutes=15),
            ),
            "2026-06-19T11:30:00Z",
        )
        reacquired = _comment(
            _body(session="session-b"),
            "2026-06-19T11:59:00Z",
        )
        with _patch_list([expired, reacquired]), _patch_post() as post:
            result = release(_OWNER, "session-a", "o", "r", 1, now=_NOW, acting_author=_AUTHOR)
        assert result.action == "ACT"
        assert result.reason == "not-owner"
        post.assert_not_called()

    def test_release_tombstone_cannot_clear_interleaved_reacquisition(self):
        first = _comment(_body(session="session-a"), "2026-06-19T11:59:00Z")
        posted: list[str] = []

        def _capture(owner, repo, pr, body):
            posted.append(body)

        with _patch_list([first]), patch.object(_mod, "post_lease_comment", side_effect=_capture):
            result = release(_OWNER, "session-a", "o", "r", 1, now=_NOW, acting_author=_AUTHOR)

        second = _comment(
            _body(session="session-a", claim_id="2" * 32),
            "2026-06-19T12:00:01Z",
        )
        stale_tombstone = _comment(posted[0], "2026-06-19T12:00:02Z")
        chosen = select_authoritative_lease([first, second, stale_tombstone])
        assert result.reason == "released"
        assert chosen is not None
        assert chosen.claim_id == "2" * 32
        assert chosen.owner == _OWNER

    @pytest.mark.parametrize(
        ("owner", "session"),
        [
            ("remote:coderabbit-autofix", _SESSION),
            (_OWNER, "foreign-session"),
        ],
    )
    def test_release_does_not_clear_foreign_live_lease(self, owner, session):
        held = _comment(
            _body(owner=owner, session=session),
            "2026-06-19T11:59:00Z",
        )
        with _patch_list([held]), _patch_post() as post:
            result = release(_OWNER, _SESSION, "o", "r", 1, now=_NOW, acting_author=_AUTHOR)
        assert result.action == "ACT"
        assert result.reason == "not-owner"
        post.assert_not_called()

    def test_release_does_not_clear_same_body_identity_from_foreign_author(self):
        held = _comment(
            _body(),
            "2026-06-19T11:59:00Z",
            author="foreign-login",
        )
        with _patch_list([held]), _patch_post() as post:
            result = release(_OWNER, _SESSION, "o", "r", 1, now=_NOW, acting_author=_AUTHOR)
        assert result.action == "ACT"
        assert result.reason == "not-owner"
        post.assert_not_called()

    def test_release_does_not_post_for_legacy_claim_without_claim_id(self):
        held = _comment(_body(claim_id=""), "2026-06-19T11:59:00Z")
        with _patch_list([held]), _patch_post() as post:
            result = release(_OWNER, _SESSION, "o", "r", 1, now=_NOW, acting_author=_AUTHOR)
        assert result.action == "ACT"
        assert result.reason == "not-owner"
        post.assert_not_called()

    def test_release_does_not_post_for_expired_own_lease(self):
        expired = _comment(
            _body(
                acquired=_NOW - timedelta(minutes=30),
                expires=_NOW - timedelta(minutes=15),
            ),
            "2026-06-19T11:30:00Z",
        )
        with _patch_list([expired]), _patch_post() as post:
            result = release(_OWNER, _SESSION, "o", "r", 1, now=_NOW, acting_author=_AUTHOR)
        assert result.action == "ACT"
        assert result.reason == "already-free"
        post.assert_not_called()

    def test_release_read_error_fails_open_to_act(self):
        with patch.object(_mod, "list_lease_comments", side_effect=LeaseStoreError("boom")):
            result = release(_OWNER, _SESSION, "o", "r", 1, now=_NOW, acting_author=_AUTHOR)
        assert result.action == "ACT"
        assert result.reason == "lease-store-unavailable"

    def test_release_write_error_fails_open_to_act(self):
        held = _comment(_body(), "2026-06-19T11:59:00Z")
        with (
            _patch_list([held]),
            patch.object(_mod, "post_lease_comment", side_effect=LeaseStoreError("boom")),
        ):
            result = release(_OWNER, _SESSION, "o", "r", 1, now=_NOW, acting_author=_AUTHOR)
        assert result.action == "ACT"
        assert result.reason == "lease-store-unavailable"

    def test_release_token_revocation_failure_fails_closed_to_skip(self):
        # The token is ownership proof, so a residual valid token must never
        # outlive the remote relinquishment (issue #4966 review). When
        # revocation cannot be persisted, release keeps the remote lease held
        # (no tombstone) and reports SKIP so the surviving token still matches
        # a live lease this session owns.
        with (
            patch.object(_mod, "_clear_ownership_token", return_value=False),
            _patch_post() as post,
        ):
            result = release(_OWNER, _SESSION, "o", "r", 1, now=_NOW, acting_author=_AUTHOR)
        assert result.action == "SKIP"
        assert result.reason == "token-revocation-failed"
        post.assert_not_called()

    def test_release_token_unlink_failure_overwrites_revoked_marker(self):
        # os.remove fails but the overwrite succeeds: the token is invalidated
        # in place (revoked marker) so a later renew fails CLOSED, and release
        # proceeds normally.
        _write_token(pr=1, now=_NOW)
        assert _has_token(pr=1, now=_NOW)
        with patch.object(_mod.os, "remove", side_effect=OSError("unlink blocked")):
            cleared = _mod._clear_ownership_token(_OWNER, _SESSION, "o", "r", 1)
        assert cleared is True
        assert not _has_token(pr=1, now=_NOW)

    def test_release_token_total_revocation_failure_returns_false(self):
        # Both os.remove and the overwrite fail (the token path is occupied by
        # a directory), so revocation cannot be persisted and clear reports
        # False, driving the release fail-closed branch above.
        path = _mod._ownership_token_path(_OWNER, _SESSION, "o", "r", 1)
        os.makedirs(path, exist_ok=True)
        assert _mod._clear_ownership_token(_OWNER, _SESSION, "o", "r", 1) is False


# ===========================================================================
# status use case (read-only)
# ===========================================================================


class TestStatus:
    def test_status_free_returns_act(self):
        with _patch_list([]):
            result = status("o", "r", 1, now=_NOW)
        assert result.action == "ACT"
        assert result.reason == "free"

    def test_status_held_returns_skip(self):
        held = _comment(_body(), "2026-06-19T11:59:00Z")
        with _patch_list([held]):
            result = status("o", "r", 1, now=_NOW)
        assert result.action == "SKIP"
        assert result.reason.startswith("held-by:")

    def test_status_far_future_forgery_returns_act(self):
        # must_fix #6: status uses the same reader-clock liveness check.
        far_acquired = _NOW + timedelta(days=1000)
        forged = _comment(
            _body(acquired=far_acquired, expires=far_acquired + TTL),
            "2026-06-19T11:59:00Z",
        )
        with _patch_list([forged]):
            result = status("o", "r", 1, now=_NOW)
        assert result.action == "ACT"
        assert result.reason == "free"

    def test_status_store_error_fails_closed_to_skip(self):
        # Issue #4966: reporting ACT told concurrent sessions the branch was
        # free at the one moment none of them could read the store. Unknown
        # ownership must read as decline.
        with patch.object(_mod, "list_lease_comments", side_effect=LeaseStoreError("boom")):
            result = status("o", "r", 1, now=_NOW)
        assert result.action == "SKIP"
        assert result.reason == "lease-store-unavailable"

    def test_cold_start_acts_but_unreadable_store_skips(self):
        # The three-state distinction issue #4966 requires: a readable store
        # with no live lease (cold start) still ACTs, while a store that could
        # not be read SKIPs. "No store yet" is not "a store that failed to read".
        with _patch_list([]):
            cold = status("o", "r", 1, now=_NOW)
        with patch.object(_mod, "list_lease_comments", side_effect=LeaseStoreError("boom")):
            unreadable = status("o", "r", 1, now=_NOW)
        assert (cold.action, cold.reason) == ("ACT", "free")
        assert (unreadable.action, unreadable.reason) == ("SKIP", "lease-store-unavailable")


# ===========================================================================
# I/O adapter error translation (subprocess mocked)
# ===========================================================================


class TestIOAdapter:
    def test_list_raises_store_error_on_nonzero_exit(self):
        with patch.object(_mod.subprocess, "run", return_value=_completed(rc=1, stderr="x")):
            with pytest.raises(LeaseStoreError):
                _mod.list_lease_comments("o", "r", 1)

    def test_list_raises_store_error_on_bad_json(self):
        with patch.object(_mod.subprocess, "run", return_value=_completed(stdout="{bad")):
            with pytest.raises(LeaseStoreError):
                _mod.list_lease_comments("o", "r", 1)

    def test_list_returns_parsed_array(self):
        payload = json.dumps([{"body": "hi", "created_at": "2026-06-19T11:00:00Z"}])
        with patch.object(_mod.subprocess, "run", return_value=_completed(stdout=payload)):
            comments = _mod.list_lease_comments("o", "r", 1)
        assert comments[0]["body"] == "hi"

    def test_list_returns_parsed_concatenated_arrays(self):
        payload = '[{"body": "hi"}][{"body": "there"}]'
        with patch.object(_mod.subprocess, "run", return_value=_completed(stdout=payload)):
            comments = _mod.list_lease_comments("o", "r", 1)
        assert [comment["body"] for comment in comments] == ["hi", "there"]

    def test_list_handles_null_payload(self):
        with patch.object(_mod.subprocess, "run", return_value=_completed(stdout="null")):
            assert _mod.list_lease_comments("o", "r", 1) == []

    def test_list_raises_store_error_on_non_list_payload(self):
        with patch.object(_mod.subprocess, "run", return_value=_completed(stdout='{"bad": true}')):
            with pytest.raises(LeaseStoreError):
                _mod.list_lease_comments("o", "r", 1)

    def test_post_raises_store_error_on_nonzero_exit(self):
        with patch.object(_mod.subprocess, "run", return_value=_completed(rc=1, stderr="x")):
            with pytest.raises(LeaseStoreError):
                _mod.post_lease_comment("o", "r", 1, "body")

    def test_list_raises_store_error_on_oserror(self):
        with patch.object(_mod.subprocess, "run", side_effect=OSError("gh missing")):
            with pytest.raises(LeaseStoreError):
                _mod.list_lease_comments("o", "r", 1)

    def test_post_raises_store_error_on_oserror(self):
        with patch.object(_mod.subprocess, "run", side_effect=OSError("gh missing")):
            with pytest.raises(LeaseStoreError):
                _mod.post_lease_comment("o", "r", 1, "body")

    def test_head_sha_returns_none_on_oserror(self):
        with patch.object(_mod.subprocess, "run", side_effect=OSError("git missing")):
            assert _mod._git_head_sha() is None

    def test_head_sha_returns_none_on_nonzero(self):
        with patch.object(_mod.subprocess, "run", return_value=_completed(rc=128)):
            assert _mod._git_head_sha() is None

    def test_head_sha_returns_sha_on_success(self):
        with patch.object(_mod.subprocess, "run", return_value=_completed(stdout=_SHA + "\n")):
            assert _mod._git_head_sha() == _SHA


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
class TestGitHeadShaAgainstRealGit:
    """#4357 acceptance criterion 3, run against the real git binary.

    The mocked tests above prove the parsing. They cannot prove that the
    command answers correctly in a detached checkout or once refs are
    packed, because both change what git reads, not what it prints.
    """

    def _git(self, repo, *args):
        # GIT_DIR and GIT_WORK_TREE leak in from an outer checkout and would
        # point every command at the wrong repository.
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env["HOME"] = str(repo)
        result = subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@e", *args],
            cwd=repo,
            env=env,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        return result.stdout.strip()

    def _repo(self, tmp_path):
        repo = tmp_path / "wt"
        repo.mkdir()
        self._git(repo, "init", "-b", "main", "-q")
        (repo / "f.txt").write_text("one", encoding="utf-8")
        self._git(repo, "add", "f.txt")
        self._git(repo, "commit", "-qm", "one")
        return repo

    @pytest.fixture(autouse=True)
    def _isolated(self, monkeypatch):
        for name in [k for k in os.environ if k.startswith("GIT_")]:
            monkeypatch.delenv(name, raising=False)

    def test_reads_the_checked_out_branch_head(self, tmp_path, monkeypatch):
        repo = self._repo(tmp_path)
        expected = self._git(repo, "rev-parse", "HEAD")

        monkeypatch.chdir(repo)

        assert _mod._git_head_sha() == expected

    def test_a_second_branch_does_not_change_the_answer(self, tmp_path, monkeypatch):
        # The #4357 defect shape: standing on one branch while the PR is on
        # another. _git_head_sha must report where it stands, nothing else.
        repo = self._repo(tmp_path)
        on_main = self._git(repo, "rev-parse", "HEAD")
        self._git(repo, "checkout", "-qb", "feature")
        (repo / "f.txt").write_text("two", encoding="utf-8")
        self._git(repo, "commit", "-qam", "two")
        on_feature = self._git(repo, "rev-parse", "HEAD")
        self._git(repo, "checkout", "-q", "main")

        monkeypatch.chdir(repo)

        assert on_feature != on_main
        assert _mod._git_head_sha() == on_main

    def test_detached_head_still_resolves(self, tmp_path, monkeypatch):
        repo = self._repo(tmp_path)
        expected = self._git(repo, "rev-parse", "HEAD")
        self._git(repo, "checkout", "-q", "--detach")

        monkeypatch.chdir(repo)

        assert _mod._git_head_sha() == expected

    def test_packed_refs_still_resolve(self, tmp_path, monkeypatch):
        repo = self._repo(tmp_path)
        expected = self._git(repo, "rev-parse", "HEAD")
        self._git(repo, "pack-refs", "--all")
        assert not (repo / ".git" / "refs" / "heads" / "main").exists()

        monkeypatch.chdir(repo)

        assert _mod._git_head_sha() == expected

    # --- _pr_head_state adapter (issues #4357, #4375, #5165) --------------

    def test_pr_head_returns_sha_and_state_on_success(self):
        payload = json.dumps({"sha": _SHA, "state": "OPEN", "merged": False})
        with patch.object(_mod.subprocess, "run", return_value=_completed(stdout=payload + "\n")):
            result = _mod._pr_head_state("o", "r", 1)
        assert result.sha == _SHA
        assert result.state == "OPEN"
        assert result.merged is False

    def test_pr_head_returns_merged_state(self):
        payload = json.dumps({"sha": _SHA, "state": "MERGED", "merged": True})
        with patch.object(_mod.subprocess, "run", return_value=_completed(stdout=payload)):
            result = _mod._pr_head_state("o", "r", 1)
        assert result.state == "MERGED"
        assert result.merged is True

    def test_pr_head_raises_store_error_on_nonzero_exit(self):
        with patch.object(_mod.subprocess, "run", return_value=_completed(rc=1, stderr="404")):
            with pytest.raises(LeaseStoreError):
                _mod._pr_head_state("o", "r", 1)

    def test_pr_head_raises_store_error_on_oserror(self):
        with patch.object(_mod.subprocess, "run", side_effect=OSError("gh missing")):
            with pytest.raises(LeaseStoreError):
                _mod._pr_head_state("o", "r", 1)

    def test_pr_head_raises_store_error_on_non_sha_payload(self):
        with patch.object(_mod.subprocess, "run", return_value=_completed(stdout="null\n")):
            with pytest.raises(LeaseStoreError):
                _mod._pr_head_state("o", "r", 1)

    def test_pr_head_raises_store_error_on_non_json_payload(self):
        with patch.object(_mod.subprocess, "run", return_value=_completed(stdout="not json\n")):
            with pytest.raises(LeaseStoreError):
                _mod._pr_head_state("o", "r", 1)

    def test_pr_head_reads_the_requested_pull_request(self):
        seen: dict = {}

        def _run(argv, **kwargs):
            seen["argv"] = argv
            return _completed(stdout=json.dumps({"sha": _SHA, "state": "OPEN", "merged": False}))

        with patch.object(_mod.subprocess, "run", side_effect=_run):
            _mod._pr_head_state("acme", "widgets", 42)
        assert "repos/acme/widgets/pulls/42" in seen["argv"]
        assert ".head.sha" in seen["argv"][-1]
        assert ".state" in seen["argv"][-1]
        assert ".merged" in seen["argv"][-1]

    # --- _gh_authenticated_login adapter (must_fix #7) --------------------

    def test_login_returns_login_on_success(self):
        with patch.object(_mod.subprocess, "run", return_value=_completed(stdout="octocat\n")):
            assert _mod._gh_authenticated_login() == "octocat"

    def test_login_returns_empty_on_nonzero(self):
        with patch.object(_mod.subprocess, "run", return_value=_completed(rc=4, stderr="auth")):
            assert _mod._gh_authenticated_login() == ""

    def test_login_returns_empty_on_oserror(self):
        with patch.object(_mod.subprocess, "run", side_effect=OSError("gh missing")):
            assert _mod._gh_authenticated_login() == ""


# ===========================================================================
# CLI: parser and exit codes
# ===========================================================================


class TestParser:
    def test_requires_command(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--pull-request", "1"])

    def test_requires_pull_request(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["status"])

    def test_rejects_unknown_command(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["frobnicate", "--pull-request", "1"])

    def test_rejects_tombstone_as_lease_owner(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["acquire", "--pull-request", "1", "--lease-owner", "none"])


class TestMainExitCodes:
    def _repo(self):
        from types import SimpleNamespace

        return SimpleNamespace(owner="o", repo="r")

    def test_acquire_free_exits_zero(self, capsys):
        with (
            patch.object(_mod, "assert_gh_authenticated", return_value=None),
            patch.object(_mod, "resolve_repo_params", return_value=self._repo()),
            _patch_list([]),
            _patch_post(),
            _patch_head(),
            _patch_login(),
        ):
            rc = main(
                ["acquire", "--pull-request", "1", "--session", _SESSION, "--output-format", "json"]
            )
        assert rc == 0

    def test_acquire_output_carries_both_shas(self, capsys):
        with (
            patch.object(_mod, "assert_gh_authenticated", return_value=None),
            patch.object(_mod, "resolve_repo_params", return_value=self._repo()),
            _patch_list([]),
            _patch_post(),
            _patch_head(sha=_OTHER_CHECKOUT, pr_head=_PR_HEAD),
            _patch_login(),
        ):
            rc = main(
                ["acquire", "--pull-request", "1", "--session", _SESSION, "--output-format", "json"]
            )
        payload = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert payload["Data"]["base_sha"] == _PR_HEAD
        assert payload["Data"]["local_head_sha"] == _OTHER_CHECKOUT

    def test_acquire_held_exits_one(self):
        held = _comment(
            _live_held_body(owner="remote:coderabbit-autofix", session="ci-1"),
            _now_iso(),
            author="coderabbit[bot]",
        )
        with (
            patch.object(_mod, "assert_gh_authenticated", return_value=None),
            patch.object(_mod, "resolve_repo_params", return_value=self._repo()),
            _patch_list([held]),
            _patch_post(),
            _patch_head(),
            _patch_login(),
        ):
            rc = main(
                ["acquire", "--pull-request", "1", "--session", _SESSION, "--output-format", "json"]
            )
        assert rc == 1

    def test_status_held_exits_one(self):
        held = _comment(_live_held_body(), _now_iso())
        with (
            patch.object(_mod, "assert_gh_authenticated", return_value=None),
            patch.object(_mod, "resolve_repo_params", return_value=self._repo()),
            _patch_list([held]),
        ):
            rc = main(["status", "--pull-request", "1", "--output-format", "json"])
        assert rc == 1

    def test_acquire_without_session_exits_two(self):
        with (
            patch.object(_mod, "assert_gh_authenticated", return_value=None),
            patch.object(_mod, "resolve_repo_params", return_value=self._repo()),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["acquire", "--pull-request", "1", "--output-format", "json"])
        assert exc.value.code == 2

    def test_invalid_repo_params_exit_two_before_auth_fail_open(self):
        auth = patch.object(_mod, "assert_gh_authenticated", side_effect=AssertionError("auth"))
        with auth, pytest.raises(SystemExit) as exc:
            main(
                [
                    "acquire",
                    "--owner",
                    "bad owner",
                    "--repo",
                    "repo",
                    "--pull-request",
                    "1",
                    "--session",
                    _SESSION,
                    "--output-format",
                    "json",
                ]
            )
        assert exc.value.code == 2

    def test_auth_failure_on_acquire_fails_closed_to_skip(self, capsys):
        # Issue #4966 CRITICAL: assert_gh_authenticated exit 4 reaches main
        # before any lease read. acquire cannot verify ownership through a
        # dead credential, so it fails CLOSED to SKIP (was ACT/exit 0, the
        # transport-failure fail-open the reviewer flagged).
        with (
            patch.object(_mod, "assert_gh_authenticated", side_effect=SystemExit(4)),
            patch.object(_mod, "resolve_repo_params", return_value=self._repo()),
        ):
            rc = main(
                ["acquire", "--pull-request", "1", "--session", _SESSION, "--output-format", "json"]
            )
        payload = json.loads(capsys.readouterr().out)
        assert rc == 1
        assert payload["Data"]["action"] == "SKIP"
        assert payload["Data"]["reason"] == "lease-store-unavailable"

    def test_release_exits_zero(self):
        with (
            patch.object(_mod, "assert_gh_authenticated", return_value=None),
            patch.object(_mod, "resolve_repo_params", return_value=self._repo()),
            _patch_post(),
        ):
            rc = main(
                ["release", "--pull-request", "1", "--session", _SESSION, "--output-format", "json"]
            )
        assert rc == 0

    def test_store_error_fails_closed_exits_one(self, capsys):
        # Issue #4966: a lease-store read failure is now SKIP (exit 1), so the
        # caller declines the branch. Distinct from a resolved-auth failure,
        # which still fails open to ACT (issue #4375, TestAuthFailOpenFix).
        with (
            patch.object(_mod, "assert_gh_authenticated", return_value=None),
            patch.object(_mod, "resolve_repo_params", return_value=self._repo()),
            patch.object(_mod, "list_lease_comments", side_effect=LeaseStoreError("down")),
            _patch_head(),
            _patch_login(),
        ):
            rc = main(
                ["acquire", "--pull-request", "1", "--session", _SESSION, "--output-format", "json"]
            )
        payload = json.loads(capsys.readouterr().out)
        assert rc == 1
        assert payload["Data"]["action"] == "SKIP"
        assert payload["Data"]["reason"] == "lease-store-unavailable"

    def test_status_store_error_exits_one(self, capsys):
        # CLI status path: an unreadable store fails closed to SKIP (exit 1),
        # matching the reproduction in issue #4966 (was ACT/exit 0).
        with (
            patch.object(_mod, "assert_gh_authenticated", return_value=None),
            patch.object(_mod, "resolve_repo_params", return_value=self._repo()),
            patch.object(_mod, "list_lease_comments", side_effect=LeaseStoreError("down")),
        ):
            rc = main(["status", "--pull-request", "1", "--output-format", "json"])
        payload = json.loads(capsys.readouterr().out)
        assert rc == 1
        assert payload["Data"]["action"] == "SKIP"
        assert payload["Data"]["reason"] == "lease-store-unavailable"


# ===========================================================================
# Issue #4966: assert_gh_authenticated() exit 3/4 before any lease read must
# fail CLOSED to SKIP for acquire/status (it cannot verify ownership). This
# narrows the prior blanket fail-open (issues #4375/#4376): release still
# fails open (TTL covers relinquish) and renew fails open only with a token.
# ===========================================================================


class TestAuthCloseFix:
    """main() catches SystemExit(3) transport and SystemExit(4) auth from
    assert_gh_authenticated() before any lease read. acquire and status fail
    CLOSED to SKIP (exit 1); release fails open to ACT; renew fails open only
    against a durable ownership token. Invalid repo arguments remain exit 2."""

    def test_auth_failure_on_acquire_fails_closed_to_skip(self, capsys):
        # assert_gh_authenticated raises SystemExit(4) on auth failure. acquire
        # cannot verify ownership, so main() returns SKIP/exit 1 (issue #4966).
        with patch.object(_mod, "assert_gh_authenticated", side_effect=SystemExit(4)):
            rc = main(
                ["acquire", "--pull-request", "1", "--session", _SESSION, "--output-format", "json"]
            )
        assert rc == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["Data"]["action"] == "SKIP"
        assert payload["Data"]["reason"] == "lease-store-unavailable"

    def test_transport_failure_on_acquire_fails_closed_to_skip(self, capsys):
        # Reviewer UNCOVERED gap: transport failure maps to exit 3, which main()
        # previously converted to ACT/exit 0. acquire now fails CLOSED to SKIP.
        with patch.object(_mod, "assert_gh_authenticated", side_effect=SystemExit(3)):
            rc = main(
                ["acquire", "--pull-request", "1", "--session", _SESSION, "--output-format", "json"]
            )
        assert rc == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["Data"]["action"] == "SKIP"
        assert payload["Data"]["reason"] == "lease-store-unavailable"

    def test_auth_failure_on_status_fails_closed_to_skip(self, capsys):
        # status path also goes through main(); same contract as acquire.
        with patch.object(_mod, "assert_gh_authenticated", side_effect=SystemExit(4)):
            rc = main(["status", "--pull-request", "1", "--output-format", "json"])
        assert rc == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["Data"]["action"] == "SKIP"
        assert payload["Data"]["reason"] == "lease-store-unavailable"

    def test_transport_failure_on_status_fails_closed_to_skip(self, capsys):
        with patch.object(_mod, "assert_gh_authenticated", side_effect=SystemExit(3)):
            rc = main(["status", "--pull-request", "1", "--output-format", "json"])
        assert rc == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["Data"]["action"] == "SKIP"
        assert payload["Data"]["reason"] == "lease-store-unavailable"

    def test_auth_failure_on_release_exits_zero_act(self, capsys):
        # release still fails open: relinquishing under an unreadable store is
        # safe because TTL expiry covers a missed tombstone (ADR-076 step 6).
        with patch.object(_mod, "assert_gh_authenticated", side_effect=SystemExit(4)):
            rc = main(
                ["release", "--pull-request", "1", "--session", _SESSION, "--output-format", "json"]
            )
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["Data"]["action"] == "ACT"
        assert payload["Data"]["reason"] == "lease-store-unavailable"

    def test_auth_failure_on_renew_with_token_exits_zero_act(self, capsys):
        # A renew whose credential dies before the read fails open ONLY with a
        # durable ownership token proving this session already won the lease
        # (issue #4966 HIGH). The token is written at the last confirmed
        # acquire; here it is seeded directly against the real clock main uses.
        _write_token(pr=1)
        with patch.object(_mod, "assert_gh_authenticated", side_effect=SystemExit(4)):
            rc = main(
                [
                    "renew",
                    "--pull-request",
                    "1",
                    "--session",
                    _SESSION,
                    "--owner",
                    "o",
                    "--repo",
                    "r",
                    "--output-format",
                    "json",
                ]
            )
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["Data"]["action"] == "ACT"
        assert payload["Data"]["reason"] == "lease-store-unavailable"

    def test_auth_failure_on_renew_without_token_fails_closed_to_skip(self, capsys):
        # `renew --session never-acquired` with a dead credential: no token, so
        # the command name is not proof of ownership. Fails CLOSED to SKIP.
        with patch.object(_mod, "assert_gh_authenticated", side_effect=SystemExit(4)):
            rc = main(
                ["renew", "--pull-request", "1", "--session", _SESSION, "--output-format", "json"]
            )
        assert rc == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["Data"]["action"] == "SKIP"
        assert payload["Data"]["reason"] == "lease-store-unavailable"

    def test_repo_resolution_failure_propagates(self):
        # resolve_repo_params failures stay outside the auth fail-open path.
        with (
            patch.object(_mod, "assert_gh_authenticated", return_value=None),
            patch.object(_mod, "resolve_repo_params", side_effect=SystemExit(3)),
        ):
            with pytest.raises(SystemExit) as exc:
                main(
                    [
                        "acquire",
                        "--pull-request",
                        "1",
                        "--session",
                        _SESSION,
                        "--output-format",
                        "json",
                    ]
                )
        assert exc.value.code == 3

    def test_invalid_repo_argument_preserves_exit_two(self):
        with (
            patch.object(_mod, "assert_gh_authenticated", return_value=None),
            patch.object(_mod, "resolve_repo_params", side_effect=SystemExit(2)),
        ):
            with pytest.raises(SystemExit) as exc:
                main(
                    [
                        "acquire",
                        "--pull-request",
                        "1",
                        "--session",
                        _SESSION,
                        "--owner",
                        "invalid owner",
                        "--repo",
                        "r",
                        "--output-format",
                        "json",
                    ]
                )
        assert exc.value.code == 2

    def test_auth_success_proceeds_to_acquire(self, capsys):
        # Positive control: when auth succeeds, normal acquire runs.
        from types import SimpleNamespace

        with (
            patch.object(_mod, "assert_gh_authenticated", return_value=None),
            patch.object(
                _mod, "resolve_repo_params", return_value=SimpleNamespace(owner="o", repo="r")
            ),
            _patch_list([]),
            _patch_post(),
            _patch_head(),
            _patch_login(),
        ):
            rc = main(
                ["acquire", "--pull-request", "1", "--session", _SESSION, "--output-format", "json"]
            )
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        # Free lock: reason is "free", not "lease-store-unavailable".
        assert payload["Data"]["reason"] == "free"


# ===========================================================================
# Issue #4376: 'renew' subcommand extends TTL for long pre-push validations.
# ===========================================================================


class TestRenewSubcommand:
    """Fix: 'renew' is a subcommand alias for self-renewal acquire. A holder
    running a pre-push validation that exceeds 15 minutes (the measured
    python-tests ceiling is 1740s) calls 'renew' periodically to keep the
    lease live for the full critical section."""

    def _repo(self):
        from types import SimpleNamespace

        return SimpleNamespace(owner="o", repo="r")

    def test_renew_on_own_live_lease_extends_ttl(self, capsys):
        # Positive: holder calls renew close to expiry. Self-renewal branch
        # returns ACT with self-renew reason and a fresh expires_at.
        # Use real-clock timestamps so main() (which doesn't inject `now`)
        # sees a live lease. _live_held_body() is the pattern for this.
        # Expiry is inside RENEW_SKIP_MARGIN (2 min < 5 min) so this exercises
        # the real renewal write, not the ample-TTL no-op path (issue #5160;
        # see test_renew_on_own_live_lease_with_ample_ttl_is_a_noop below for
        # that path).
        real_now = datetime.now(UTC)
        live_body = _body(
            owner=_OWNER,
            session=_SESSION,
            acquired=real_now - timedelta(minutes=13),
            expires=real_now + timedelta(minutes=2),
        )
        mine = _comment(live_body, _rfc(real_now - timedelta(minutes=13)), author=_AUTHOR)
        with (
            patch.object(_mod, "assert_gh_authenticated", return_value=None),
            patch.object(_mod, "resolve_repo_params", return_value=self._repo()),
            _patch_list([mine]),
            _patch_post() as post,
            _patch_head(),
            _patch_login(login=_AUTHOR),
        ):
            rc = main(
                ["renew", "--pull-request", "1", "--session", _SESSION, "--output-format", "json"]
            )
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["Data"]["action"] == "ACT"
        assert payload["Data"]["reason"] == "self-renew"
        assert post.call_count == 1

    def test_renew_on_own_live_lease_with_ample_ttl_is_a_noop(self, capsys):
        # Issue #5160: a renew called while the held lease still has most of
        # its TTL left (10 of 15 min, well outside the 5-min skip margin)
        # must not write a fresh marker comment. A caller polling far tighter
        # than the TTL requires must not multiply PR comment volume.
        real_now = datetime.now(UTC)
        live_body = _body(
            owner=_OWNER,
            session=_SESSION,
            acquired=real_now - timedelta(minutes=1),
            expires=real_now + timedelta(minutes=10),
        )
        mine = _comment(live_body, _rfc(real_now - timedelta(minutes=1)), author=_AUTHOR)
        with (
            patch.object(_mod, "assert_gh_authenticated", return_value=None),
            patch.object(_mod, "resolve_repo_params", return_value=self._repo()),
            _patch_list([mine]),
            _patch_post() as post,
            _patch_head(),
            _patch_login(login=_AUTHOR),
        ):
            rc = main(
                ["renew", "--pull-request", "1", "--session", _SESSION, "--output-format", "json"]
            )
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["Data"]["action"] == "ACT"
        assert payload["Data"]["reason"] == "self-renew-noop"
        assert payload["Data"]["expires_at"] == _rfc(real_now + timedelta(minutes=10))
        assert post.call_count == 0

    def test_renew_on_merged_pr_with_ample_ttl_returns_skip_pr_closed(self, capsys):
        # Round-2 finding (AI spec validator, PR #5167): the pr-closed check
        # must run BEFORE the RENEW_SKIP_MARGIN noop fast path, not after it.
        # Same fixture as test_renew_on_own_live_lease_with_ample_ttl_is_a_noop
        # (10 of 15 min left, well outside the 5-min skip margin) except the
        # PR has merged. If the pr-closed check were gated behind the noop
        # fast path, this would incorrectly return ACT/self-renew-noop
        # instead of SKIP/pr-closed for up to RENEW_SKIP_MARGIN of the TTL.
        real_now = datetime.now(UTC)
        live_body = _body(
            owner=_OWNER,
            session=_SESSION,
            acquired=real_now - timedelta(minutes=1),
            expires=real_now + timedelta(minutes=10),
        )
        mine = _comment(live_body, _rfc(real_now - timedelta(minutes=1)), author=_AUTHOR)
        with (
            patch.object(_mod, "assert_gh_authenticated", return_value=None),
            patch.object(_mod, "resolve_repo_params", return_value=self._repo()),
            _patch_list([mine]),
            _patch_post() as post,
            _patch_head(pr_merged=True, pr_state="MERGED"),
            _patch_login(login=_AUTHOR),
        ):
            rc = main(
                ["renew", "--pull-request", "1", "--session", _SESSION, "--output-format", "json"]
            )
        assert rc == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["Data"]["action"] == "SKIP"
        assert payload["Data"]["reason"] == "pr-closed"
        post.assert_not_called()

    # --- PR-closed check on the renew path (ADR-076 Amendment 2026-08-19,
    # issue #5165) -----------------------------------------------------------

    def test_renew_on_merged_pr_returns_skip_pr_closed_without_writing(self, capsys):
        # A self-renew whose PR has since merged must stop coordinating
        # instead of writing another marker comment forever.
        real_now = datetime.now(UTC)
        live_body = _body(
            owner=_OWNER,
            session=_SESSION,
            acquired=real_now - timedelta(minutes=13),
            expires=real_now + timedelta(minutes=2),
        )
        mine = _comment(live_body, _rfc(real_now - timedelta(minutes=13)), author=_AUTHOR)
        with (
            patch.object(_mod, "assert_gh_authenticated", return_value=None),
            patch.object(_mod, "resolve_repo_params", return_value=self._repo()),
            _patch_list([mine]),
            _patch_post() as post,
            _patch_head(pr_merged=True, pr_state="MERGED"),
            _patch_login(login=_AUTHOR),
        ):
            rc = main(
                ["renew", "--pull-request", "1", "--session", _SESSION, "--output-format", "json"]
            )
        assert rc == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["Data"]["action"] == "SKIP"
        assert payload["Data"]["reason"] == "pr-closed"
        post.assert_not_called()

    def test_renew_on_closed_unmerged_pr_returns_skip_pr_closed(self, capsys):
        # A renew that would otherwise re-claim a free lock (no live lease
        # held) must still stop when the target PR is closed, not merged.
        with (
            patch.object(_mod, "assert_gh_authenticated", return_value=None),
            patch.object(_mod, "resolve_repo_params", return_value=self._repo()),
            _patch_list([]),
            _patch_post() as post,
            _patch_head(pr_state="CLOSED", pr_merged=False),
            _patch_login(login=_AUTHOR),
        ):
            rc = main(
                ["renew", "--pull-request", "1", "--session", _SESSION, "--output-format", "json"]
            )
        assert rc == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["Data"]["action"] == "SKIP"
        assert payload["Data"]["reason"] == "pr-closed"
        post.assert_not_called()

    def test_renew_on_open_pr_is_unaffected(self, capsys):
        # Negative control: the overwhelming majority of renews, against a
        # still-open PR, must be unaffected by the new check.
        real_now = datetime.now(UTC)
        live_body = _body(
            owner=_OWNER,
            session=_SESSION,
            acquired=real_now - timedelta(minutes=13),
            expires=real_now + timedelta(minutes=2),
        )
        mine = _comment(live_body, _rfc(real_now - timedelta(minutes=13)), author=_AUTHOR)
        with (
            patch.object(_mod, "assert_gh_authenticated", return_value=None),
            patch.object(_mod, "resolve_repo_params", return_value=self._repo()),
            _patch_list([mine]),
            _patch_post() as post,
            _patch_head(pr_state="OPEN", pr_merged=False),
            _patch_login(login=_AUTHOR),
        ):
            rc = main(
                ["renew", "--pull-request", "1", "--session", _SESSION, "--output-format", "json"]
            )
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["Data"]["action"] == "ACT"
        assert payload["Data"]["reason"] == "self-renew"
        post.assert_called_once()

    def test_renew_pr_state_read_failure_falls_through_unchanged(self, capsys):
        # A failed live-state read must not block a renew; it degrades to
        # exactly today's behavior (fresh claim on a free lock).
        with (
            patch.object(_mod, "assert_gh_authenticated", return_value=None),
            patch.object(_mod, "resolve_repo_params", return_value=self._repo()),
            patch.object(_mod, "_pr_head_state", side_effect=LeaseStoreError("api down")),
            patch.object(_mod, "_git_head_sha", return_value=_SHA),
            _patch_list([]),
            _patch_post() as post,
            _patch_login(login=_AUTHOR),
        ):
            rc = main(
                ["renew", "--pull-request", "1", "--session", _SESSION, "--output-format", "json"]
            )
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["Data"]["action"] == "ACT"
        assert payload["Data"]["reason"] == "free"
        post.assert_called_once()

    def test_fresh_acquire_on_closed_pr_is_unaffected(self):
        # Documented residual (ADR-076 Amendment 2026-08-19): the pr-closed
        # check is scoped to renewing=True only. A fresh (non-renewing)
        # acquire against a closed PR still claims it.
        with (
            _patch_list([]),
            _patch_post() as post,
            _patch_head(pr_state="CLOSED", pr_merged=False),
            _patch_login(),
        ):
            result = acquire(_OWNER, _SESSION, "o", "r", 1, now=_NOW, renewing=False)
        assert result.action == "ACT"
        assert result.reason == "free"
        post.assert_called_once()

    def test_renew_on_free_lease_re_claims(self, capsys):
        # Edge: renew when lease already expired re-claims it (same as acquire).
        with (
            patch.object(_mod, "assert_gh_authenticated", return_value=None),
            patch.object(_mod, "resolve_repo_params", return_value=self._repo()),
            _patch_list([]),
            _patch_post(),
            _patch_head(),
            _patch_login(login=_AUTHOR),
        ):
            rc = main(
                ["renew", "--pull-request", "1", "--session", _SESSION, "--output-format", "json"]
            )
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["Data"]["action"] == "ACT"
        assert payload["Data"]["reason"] == "free"

    def test_renew_returns_skip_when_held_by_other(self, capsys):
        # Negative: another loop holds the lease; renew sees SKIP (exit 1).
        held = _comment(
            _live_held_body(owner="remote:coderabbit-autofix", session="ci-1"),
            _now_iso(),
            author="coderabbit[bot]",
        )
        with (
            patch.object(_mod, "assert_gh_authenticated", return_value=None),
            patch.object(_mod, "resolve_repo_params", return_value=self._repo()),
            _patch_list([held]),
            _patch_post(),
            _patch_head(),
            _patch_login(login=_AUTHOR),
        ):
            rc = main(
                ["renew", "--pull-request", "1", "--session", _SESSION, "--output-format", "json"]
            )
        assert rc == 1

    def test_renew_returns_skip_for_same_login_different_session(self, capsys):
        mine = _comment(
            _live_held_body(session="other-session"),
            _now_iso(),
            author=_AUTHOR,
        )
        with (
            patch.object(_mod, "assert_gh_authenticated", return_value=None),
            patch.object(_mod, "resolve_repo_params", return_value=self._repo()),
            _patch_list([mine]),
            _patch_post(),
            _patch_head(),
            _patch_login(login=_AUTHOR),
        ):
            rc = main(
                ["renew", "--pull-request", "1", "--session", _SESSION, "--output-format", "json"]
            )
        assert rc == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["Data"]["action"] == "SKIP"

    def test_renew_without_session_exits_two(self):
        # Session is required for renew (same as acquire).
        with (
            patch.object(_mod, "assert_gh_authenticated", return_value=None),
            patch.object(_mod, "resolve_repo_params", return_value=self._repo()),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["renew", "--pull-request", "1", "--output-format", "json"])
        assert exc.value.code == 2

    def test_renew_store_error_with_token_fails_open_to_act(self, capsys):
        # A renew whose store read fails extends in place ONLY with a durable
        # ownership token (issue #4966 HIGH). The SHA gate stays authoritative
        # while the advisory store is down (issue #4376).
        _write_token(pr=1)
        with (
            patch.object(_mod, "assert_gh_authenticated", return_value=None),
            patch.object(_mod, "resolve_repo_params", return_value=self._repo()),
            patch.object(_mod, "list_lease_comments", side_effect=LeaseStoreError("down")),
            _patch_head(),
            _patch_login(),
        ):
            rc = main(
                ["renew", "--pull-request", "1", "--session", _SESSION, "--output-format", "json"]
            )
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["Data"]["action"] == "ACT"
        assert payload["Data"]["reason"] == "lease-store-unavailable"

    def test_renew_store_error_without_token_fails_closed_to_skip(self, capsys):
        # No ownership token: a renew on an unreadable store cannot prove prior
        # ownership, so it fails CLOSED to SKIP (issue #4966 HIGH repro).
        with (
            patch.object(_mod, "assert_gh_authenticated", return_value=None),
            patch.object(_mod, "resolve_repo_params", return_value=self._repo()),
            patch.object(_mod, "list_lease_comments", side_effect=LeaseStoreError("down")),
            _patch_head(),
            _patch_login(),
        ):
            rc = main(
                ["renew", "--pull-request", "1", "--session", _SESSION, "--output-format", "json"]
            )
        assert rc == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["Data"]["action"] == "SKIP"
        assert payload["Data"]["reason"] == "lease-store-unavailable"

    def test_renew_login_lookup_failure_with_token_fails_open_to_act(self, capsys):
        # The login lookup (`gh api user`) blips, so acquire cannot verify its
        # own identity. A token proves prior ownership, so renew fails open.
        _write_token(pr=1)
        with (
            patch.object(_mod, "assert_gh_authenticated", return_value=None),
            patch.object(_mod, "resolve_repo_params", return_value=self._repo()),
            patch.object(_mod, "_gh_authenticated_login", return_value=""),
        ):
            rc = main(
                ["renew", "--pull-request", "1", "--session", _SESSION, "--output-format", "json"]
            )
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["Data"]["action"] == "ACT"
        assert payload["Data"]["reason"] == "lease-store-unavailable"

    def test_renew_login_lookup_failure_without_token_fails_closed_to_skip(self, capsys):
        # Without a token, an unresolved login cannot verify ownership: SKIP.
        with (
            patch.object(_mod, "assert_gh_authenticated", return_value=None),
            patch.object(_mod, "resolve_repo_params", return_value=self._repo()),
            patch.object(_mod, "_gh_authenticated_login", return_value=""),
        ):
            rc = main(
                ["renew", "--pull-request", "1", "--session", _SESSION, "--output-format", "json"]
            )
        assert rc == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["Data"]["action"] == "SKIP"
        assert payload["Data"]["reason"] == "lease-store-unavailable"

    def test_duration_exceeding_ttl_covered_by_two_renewals(self):
        # Integration-style: simulate a 30-minute validation run (2x TTL).
        # Two renew calls, each at the 14-minute mark, keep the lease live.
        # Each renew is a self-renewal (ACT/self-renew). This documents the
        # intended usage pattern for pre-push hooks longer than TTL
        # (issue #4376; measured ceiling: python-tests 1740s > 15min TTL).
        timeline = []
        now_ptr = [_NOW]

        def _advance_and_renew(minutes: int):
            now_ptr[0] = now_ptr[0] + timedelta(minutes=minutes)
            with (
                patch.object(_mod, "list_lease_comments", side_effect=lambda *a, **k: timeline),
                patch.object(
                    _mod,
                    "post_lease_comment",
                    side_effect=lambda o, r, p, b: timeline.append(
                        {"body": b, "created_at": _rfc(now_ptr[0]), "user": {"login": _AUTHOR}}
                    ),
                ),
                _patch_head(),
            ):
                return acquire(_OWNER, _SESSION, "o", "r", 1, now=now_ptr[0], acting_author=_AUTHOR)

        # Initial acquire at t=0.
        with (
            patch.object(_mod, "list_lease_comments", side_effect=lambda *a, **k: timeline),
            patch.object(
                _mod,
                "post_lease_comment",
                side_effect=lambda o, r, p, b: timeline.append(
                    {"body": b, "created_at": _rfc(_NOW), "user": {"login": _AUTHOR}}
                ),
            ),
            _patch_head(),
        ):
            r0 = acquire(_OWNER, _SESSION, "o", "r", 1, now=_NOW, acting_author=_AUTHOR)
        assert r0.action == "ACT"

        # First renew at t+14m (within TTL; self-renewal should work).
        r1 = _advance_and_renew(14)
        assert r1.action == "ACT"

        # Second renew at t+28m (14m after first renew; still within that
        # lease's TTL window). Covers the 30-minute validation scenario.
        r2 = _advance_and_renew(14)
        assert r2.action == "ACT"

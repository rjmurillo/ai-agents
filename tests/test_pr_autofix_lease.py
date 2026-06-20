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
    - #7 author-keyed self-renew: keyed on verified user.login, not body owner
    - #8 bounded scan: at most MAX_SCAN comments parsed
plus the TESTING-RIGOR matrix (positive, negative, edge, every branch, CLI
exit codes) with all I/O mocked.

Exit codes follow ADR-035:
    0 - ACT (proceed)
    1 - SKIP (another live lease holds the branch)
    2 - PR not found / usage error
    3 - External error
    4 - Auth error
"""

from __future__ import annotations

import importlib.util
import json
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
    marker: bool = True,
) -> str:
    acquired = acquired or _NOW
    expires = expires or (_NOW + TTL)
    head = f"{LEASE_MARKER}\n" if marker else ""
    return (
        f"{head}"
        f"owner: {owner}\n"
        f"session: {session}\n"
        f"acquired_at: {_rfc(acquired)}\n"
        f"expires_at: {_rfc(expires)}\n"
        f"base_sha: {base_sha}\n"
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
            render_lease_comment(build_tombstone(_OWNER, _SESSION, _NOW)),
            "2026-06-19T11:30:00Z",
        )
        chosen = select_authoritative_lease([live, tomb])
        assert chosen is not None
        assert not chosen.is_live(_NOW)

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
            _comment("noise comment", f"2026-06-19T10:{i:02d}:00Z") for i in range(MAX_SCAN)
        ]
        chosen = select_authoritative_lease([old_live, *filler])
        assert chosen is None

    def test_recent_marker_within_window_is_found(self):
        # A marker within the latest MAX_SCAN comments IS found.
        filler = [
            _comment("noise comment", f"2026-06-19T09:{i:02d}:00Z")
            for i in range(MAX_SCAN - 1)
        ]
        recent = _comment(_body(session="recent"), "2026-06-19T11:59:00Z")
        chosen = select_authoritative_lease([*filler, recent])
        assert chosen is not None
        assert chosen.session == "recent"


# ===========================================================================
# classify_acquire: every verdict branch (author-keyed, must_fix #7)
# ===========================================================================


def _stamped(lease: Lease, author: str) -> Lease:
    from dataclasses import replace

    return replace(lease, author=author)


class TestClassifyAcquire:
    def test_no_lease_returns_act_free(self):
        verdict = classify_acquire(None, _AUTHOR, _NOW)
        assert verdict == {"action": "ACT", "reason": "free"}

    def test_expired_lease_returns_act_free(self):
        expired = build_claim(_OWNER, _SESSION, _SHA, _NOW - TTL - timedelta(minutes=1))
        verdict = classify_acquire(_stamped(expired, "someone"), _AUTHOR, _NOW)
        assert verdict["action"] == "ACT"
        assert verdict["reason"] == "free"

    def test_live_lease_other_author_returns_skip(self):
        held = build_claim("remote:coderabbit-autofix", "ci-99", _SHA, _NOW)
        held = _stamped(held, "coderabbit[bot]")
        verdict = classify_acquire(held, _AUTHOR, _NOW)
        assert verdict["action"] == "SKIP"
        assert verdict["reason"] == "held-by:remote:coderabbit-autofix"
        assert verdict["expires_at"] == _rfc(_NOW + TTL)

    def test_live_lease_same_author_returns_self_renew(self):
        mine = build_claim(_OWNER, _SESSION, _SHA, _NOW)
        mine = _stamped(mine, _AUTHOR)
        verdict = classify_acquire(mine, _AUTHOR, _NOW)
        assert verdict == {"action": "ACT", "reason": "self-renew"}

    def test_self_renew_keys_on_author_not_body_owner(self):
        # must_fix #7: a forged body that copies a legitimate owner/session but
        # was posted by a DIFFERENT credential must NOT be treated as the
        # acting loop's own lease. The verified author differs, so it is SKIP.
        forged = build_claim(_OWNER, _SESSION, _SHA, _NOW)  # same body owner/session
        forged = _stamped(forged, "attacker-login")  # but a foreign author
        verdict = classify_acquire(forged, _AUTHOR, _NOW)
        assert verdict["action"] == "SKIP"

    def test_empty_acting_author_never_self_renews(self):
        # An unresolved acting login ("") can only claim a free lock, never
        # self-renew a foreign one, even one whose author is also "".
        mine = _stamped(build_claim(_OWNER, _SESSION, _SHA, _NOW), "")
        verdict = classify_acquire(mine, "", _NOW)
        assert verdict["action"] == "SKIP"

    def test_far_future_forged_lease_classifies_as_free(self):
        # must_fix #6 wired through classify: a far-future forgery is not live
        # at the reader's clock, so acquire treats it as free and ACTs.
        far_acquired = _NOW + timedelta(days=1000)
        forged = parse_lease_block(_body(acquired=far_acquired, expires=far_acquired + TTL))
        assert forged is not None
        forged = _stamped(forged, "attacker-login")
        verdict = classify_acquire(forged, _AUTHOR, _NOW)
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


def _patch_list(comments):
    return patch.object(_mod, "list_lease_comments", return_value=comments)


def _patch_post():
    return patch.object(_mod, "post_lease_comment", return_value=None)


def _patch_head(sha=_SHA):
    return patch.object(_mod, "_git_head_sha", return_value=sha)


def _patch_login(login=_AUTHOR):
    return patch.object(_mod, "_gh_authenticated_login", return_value=login)


class TestAcquire:
    def test_acquire_on_free_pr_returns_act(self):
        with _patch_list([]), _patch_post() as post, _patch_head(), _patch_login():
            result = acquire(_OWNER, _SESSION, "o", "r", 1, now=_NOW)
        assert result.action == "ACT"
        assert result.reason == "free"
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
        with _patch_list([mine]), _patch_post(), _patch_head():
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

    def test_store_read_error_fails_open_to_act(self):
        with (
            patch.object(_mod, "list_lease_comments", side_effect=LeaseStoreError("boom")),
            _patch_post() as post,
            _patch_head(),
            _patch_login(),
        ):
            result = acquire(_OWNER, _SESSION, "o", "r", 1, now=_NOW)
        assert result.action == "ACT"
        assert result.reason == "lease-store-unavailable"
        post.assert_not_called()

    def test_store_write_error_fails_open_to_act(self):
        with (
            _patch_list([]),
            patch.object(_mod, "post_lease_comment", side_effect=LeaseStoreError("boom")),
            _patch_head(),
            _patch_login(),
        ):
            result = acquire(_OWNER, _SESSION, "o", "r", 1, now=_NOW)
        assert result.action == "ACT"
        assert result.reason == "lease-store-unavailable"

    def test_acquire_uses_zero_sha_when_git_unavailable(self):
        with _patch_list([]), _patch_post(), _patch_head(sha=None), _patch_login():
            result = acquire(_OWNER, _SESSION, "o", "r", 1, now=_NOW)
        assert result.base_sha == "0" * 40


# ===========================================================================
# release use case (idempotent, fail-open)
# ===========================================================================


class TestRelease:
    def test_release_writes_tombstone_and_returns_act(self):
        captured = {}

        def _capture(owner, repo, pr, body):
            captured["body"] = body

        with patch.object(_mod, "post_lease_comment", side_effect=_capture):
            result = release(_OWNER, _SESSION, "o", "r", 1, now=_NOW)
        assert result.action == "ACT"
        assert result.reason == "released"
        parsed = parse_lease_block(captured["body"])
        assert parsed is not None
        assert parsed.owner == TOMBSTONE_OWNER

    def test_release_is_idempotent_on_already_free_lock(self):
        with _patch_post():
            first = release(_OWNER, _SESSION, "o", "r", 1, now=_NOW)
            second = release(_OWNER, _SESSION, "o", "r", 1, now=_NOW)
        assert first.action == "ACT"
        assert second.action == "ACT"

    def test_release_store_error_fails_open_to_act(self):
        with patch.object(_mod, "post_lease_comment", side_effect=LeaseStoreError("boom")):
            result = release(_OWNER, _SESSION, "o", "r", 1, now=_NOW)
        assert result.action == "ACT"
        assert result.reason == "lease-store-unavailable"


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

    def test_status_store_error_fails_open_to_act(self):
        with patch.object(_mod, "list_lease_comments", side_effect=LeaseStoreError("boom")):
            result = status("o", "r", 1, now=_NOW)
        assert result.action == "ACT"
        assert result.reason == "lease-store-unavailable"


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

    def test_store_error_fails_open_exits_zero(self):
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
        assert rc == 0

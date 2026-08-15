"""Tests for sibling-branch session-number allocation (issue #4751).

Session numbers allocated against origin/main alone cannot see numbers a
sibling branch has pushed but not merged, so two concurrent sessions allocate
the same number and produce add/add conflicts. The sibling-ref scan closes
that window; these tests cover the positive (collision with a sibling branch
detected), negative (no false collision when siblings share no numbers), and
edge (probe failure is not absence) requirements.
"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SKILL_DIR = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "session-init"
SCRIPT_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SKILL_DIR))
sys.path.insert(0, str(SCRIPT_DIR))

import new_session_log
from session_init import allocation

MAIN_REF = "refs/remotes/origin/main"
SIBLING_REF = "refs/remotes/origin/fix/pr-tooling-cluster"


def _completed(returncode: int, stdout: str = "") -> MagicMock:
    return MagicMock(returncode=returncode, stdout=stdout)


def _sessions_listing(*numbers: int) -> str:
    return "".join(f".agents/sessions/2026-08-07-session-{n}.json\n" for n in numbers)


def _dispatching_run(listing_result, trees, calls=None):
    """subprocess.run fake dispatched on argv, per testing rule 11.

    ``trees`` maps refname -> CompletedProcess-like for its ls-tree call, or
    an exception instance to raise. Unstubbed commands fail by name instead of
    silently consuming a neighbour's response.
    """

    def run(argv, **kwargs):
        if calls is not None:
            calls.append(list(argv))
        assert argv[0] == "git", f"unexpected program: {argv}"
        if argv[1] == "for-each-ref":
            if isinstance(listing_result, BaseException):
                raise listing_result
            return listing_result
        if argv[1] == "ls-tree":
            ref = argv[3]
            if ref not in trees:
                raise AssertionError(f"no stubbed ls-tree response for ref {ref!r}")
            response = trees[ref]
            if isinstance(response, BaseException):
                raise response
            return response
        raise AssertionError(f"unstubbed git command: {argv}")

    return run


class TestSiblingRefsMaxSession:
    """Unit tests for allocation.sibling_refs_max_session."""

    def test_detects_number_taken_on_unmerged_sibling(self):
        # Positive: origin/main tops out at 10003, but a sibling branch has
        # already pushed 10004. The scan must surface 10004 so the next
        # allocation picks 10005 instead of colliding (issue #4751 shape).
        listing = _completed(0, f"{MAIN_REF} aaa111\n{SIBLING_REF} bbb222\n")
        trees = {
            MAIN_REF: _completed(0, _sessions_listing(10002, 10003)),
            SIBLING_REF: _completed(0, _sessions_listing(10003, 10004)),
        }
        with patch.object(allocation.subprocess, "run", _dispatching_run(listing, trees)):
            assert allocation.sibling_refs_max_session("/repo") == 10004

    def test_no_false_collision_when_siblings_share_no_numbers(self):
        # Negative: siblings only carry numbers at or below main's max; the
        # scan reports exactly that max, inventing nothing higher.
        listing = _completed(0, f"{MAIN_REF} aaa111\n{SIBLING_REF} bbb222\n")
        trees = {
            MAIN_REF: _completed(0, _sessions_listing(10003)),
            SIBLING_REF: _completed(0, _sessions_listing(9990)),
        }
        with patch.object(allocation.subprocess, "run", _dispatching_run(listing, trees)):
            assert allocation.sibling_refs_max_session("/repo") == 10003

    def test_complete_scan_with_no_sessions_returns_zero_not_none(self):
        # A scan that ran to completion and found nothing IS evidence of
        # absence: it must return 0 (int), never None.
        listing = _completed(0, f"{MAIN_REF} aaa111\n")
        trees = {MAIN_REF: _completed(0, "")}
        with patch.object(allocation.subprocess, "run", _dispatching_run(listing, trees)):
            result = allocation.sibling_refs_max_session("/repo")
        assert result == 0
        assert result is not None

    def test_ref_enumeration_failure_returns_none_not_zero(self):
        # Edge: a failed probe must be distinguishable from absence. A
        # reading that cannot separate the two is not evidence.
        with patch.object(allocation.subprocess, "run", _dispatching_run(_completed(128), {})):
            assert allocation.sibling_refs_max_session("/repo") is None

    def test_ref_enumeration_oserror_returns_none(self):
        with patch.object(
            allocation.subprocess, "run", _dispatching_run(OSError("git missing"), {})
        ):
            assert allocation.sibling_refs_max_session("/repo") is None

    def test_ref_enumeration_timeout_returns_none(self):
        timeout = subprocess.TimeoutExpired(cmd="git", timeout=10)
        with patch.object(allocation.subprocess, "run", _dispatching_run(timeout, {})):
            assert allocation.sibling_refs_max_session("/repo") is None

    def test_single_ref_read_failure_poisons_the_whole_reading(self):
        # Edge: one unreadable ref makes the reading incomplete; the numbers
        # seen on other refs must not be passed off as a complete scan.
        listing = _completed(0, f"{MAIN_REF} aaa111\n{SIBLING_REF} bbb222\n")
        trees = {
            MAIN_REF: _completed(0, _sessions_listing(10003)),
            SIBLING_REF: _completed(128, ""),
        }
        with patch.object(allocation.subprocess, "run", _dispatching_run(listing, trees)):
            assert allocation.sibling_refs_max_session("/repo") is None

    def test_single_ref_timeout_poisons_the_whole_reading(self):
        listing = _completed(0, f"{MAIN_REF} aaa111\n{SIBLING_REF} bbb222\n")
        trees = {
            MAIN_REF: _completed(0, _sessions_listing(10003)),
            SIBLING_REF: subprocess.TimeoutExpired(cmd="git", timeout=10),
        }
        with patch.object(allocation.subprocess, "run", _dispatching_run(listing, trees)):
            assert allocation.sibling_refs_max_session("/repo") is None

    def test_expired_budget_aborts_as_probe_failure(self, monkeypatch):
        # Edge: a scan cut short by the budget is incomplete, so it reports
        # failure (None), not a partial number.
        monkeypatch.setattr(allocation, "SIBLING_SCAN_BUDGET_SECONDS", -1.0)
        listing = _completed(0, f"{MAIN_REF} aaa111\n")
        trees = {MAIN_REF: _completed(0, _sessions_listing(10003))}
        with patch.object(allocation.subprocess, "run", _dispatching_run(listing, trees)):
            assert allocation.sibling_refs_max_session("/repo") is None

    def test_refs_at_the_same_commit_are_read_once(self):
        # origin/HEAD duplicates origin/main at the same commit; identical
        # commits share the same sessions tree, so one ls-tree covers both.
        listing = _completed(
            0,
            f"refs/remotes/origin/HEAD aaa111\n{MAIN_REF} aaa111\n{SIBLING_REF} bbb222\n",
        )
        trees = {
            "refs/remotes/origin/HEAD": _completed(0, _sessions_listing(10003)),
            SIBLING_REF: _completed(0, _sessions_listing(10004)),
        }
        calls: list[list[str]] = []
        with patch.object(allocation.subprocess, "run", _dispatching_run(listing, trees, calls)):
            assert allocation.sibling_refs_max_session("/repo") == 10004
        ls_tree_calls = [c for c in calls if c[1] == "ls-tree"]
        assert len(ls_tree_calls) == 2  # HEAD/main deduped to one read


class TestRemoteMaxSessionPolicy:
    """allocation.remote_max_session: fallback fires on failure, not absence."""

    def test_probe_failure_falls_back_to_origin_main_with_warning(self, capsys):
        fallback = MagicMock(return_value=10003)
        result = allocation.remote_max_session(
            "/repo", sibling_scan=lambda root: None, origin_scan=fallback
        )
        assert result == 10003
        fallback.assert_called_once_with("/repo")
        err = capsys.readouterr().err
        assert "sibling-branch session scan failed" in err
        assert "4751" in err

    def test_absence_is_evidence_and_does_not_fall_back(self, capsys):
        fallback = MagicMock(return_value=10003)
        result = allocation.remote_max_session(
            "/repo", sibling_scan=lambda root: 0, origin_scan=fallback
        )
        assert result == 0
        fallback.assert_not_called()
        assert capsys.readouterr().err == ""

    def test_successful_scan_value_wins(self):
        fallback = MagicMock(return_value=1)
        result = allocation.remote_max_session(
            "/repo", sibling_scan=lambda root: 10004, origin_scan=fallback
        )
        assert result == 10004
        fallback.assert_not_called()


class TestNewSessionLogWiring:
    """new_session_log routes allocation through the sibling-aware policy."""

    def test_remote_max_prefers_sibling_scan(self):
        with (
            patch.object(new_session_log, "_sibling_refs_max_session", return_value=10004),
            patch.object(new_session_log, "_origin_main_max_session") as mock_origin,
        ):
            assert new_session_log._remote_max_session("/repo") == 10004
        mock_origin.assert_not_called()

    def test_remote_max_falls_back_to_origin_main_on_probe_failure(self):
        with (
            patch.object(new_session_log, "_sibling_refs_max_session", return_value=None),
            patch.object(new_session_log, "_origin_main_max_session", return_value=10003),
        ):
            assert new_session_log._remote_max_session("/repo") == 10003

    def test_auto_detect_avoids_sibling_number(self, tmp_path):
        # End-to-end through _auto_detect_session_number: local tree knows 5,
        # a sibling pushed 10004; next allocation must be 10005.
        (tmp_path / "2026-08-07-session-5.json").write_text("{}")
        with (
            patch.object(new_session_log, "_sibling_refs_max_session", return_value=10004),
            patch.object(new_session_log, "_origin_main_max_session") as mock_origin,
        ):
            assert new_session_log._auto_detect_session_number(str(tmp_path)) == 10005
        mock_origin.assert_not_called()


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=True,
    )


def _git_available() -> bool:
    try:
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


@pytest.mark.skipif(not _git_available(), reason="git not available")
class TestSiblingBranchCollisionIntegration:
    """End-to-end with real refs: an unmerged sibling's number is not reused.

    Reproduces the #4751 collision shape: origin/main tops out at 2335, a
    sibling branch has pushed session 2340 without merging. An allocator that
    reads origin/main alone re-picks 2336..2340 and collides; reading every
    remote-tracking ref forces 2341.
    """

    def _make_origin_with_sibling(self, tmp_path: Path) -> Path:
        origin = tmp_path / "origin.git"
        seed = tmp_path / "seed"
        seed.mkdir()
        _git(seed, "init", "-q", "-b", "main")
        _git(seed, "config", "user.email", "t@e.com")
        _git(seed, "config", "user.name", "T")
        sessions = seed / ".agents" / "sessions"
        sessions.mkdir(parents=True)
        (sessions / "2026-06-04-session-2335.json").write_text("{}")
        _git(seed, "add", "-A")
        _git(seed, "commit", "-q", "-m", "seed with session 2335")
        # Sibling branch pushes 2340 without merging to main.
        _git(seed, "checkout", "-q", "-b", "fix/unmerged-sibling")
        (sessions / "2026-06-05-session-2340.json").write_text("{}")
        _git(seed, "add", "-A")
        _git(seed, "commit", "-q", "-m", "sibling with session 2340")
        _git(seed, "checkout", "-q", "main")
        _git(seed, "clone", "-q", "--bare", str(seed), str(origin))

        clone = tmp_path / "clone"
        _git(tmp_path, "clone", "-q", str(origin), str(clone))
        return clone

    def test_unmerged_sibling_number_is_not_reused(self, tmp_path, monkeypatch):
        clone = self._make_origin_with_sibling(tmp_path)
        _git(clone, "checkout", "-q", "-b", "fix/parallel")
        local_sessions = clone / ".agents" / "sessions"
        monkeypatch.chdir(clone)

        # origin/main alone reports 2335; the sibling scan sees 2340.
        assert allocation.origin_main_max_session() == 2335
        assert allocation.sibling_refs_max_session() == 2340
        assert new_session_log._auto_detect_session_number(str(local_sessions)) == 2341

    def test_no_false_collision_when_sibling_adds_nothing(self, tmp_path, monkeypatch):
        clone = self._make_origin_with_sibling(tmp_path)
        monkeypatch.chdir(clone)
        # Drop the sibling ref: only main remains, so the scan must agree
        # with the origin/main reading instead of inventing a higher number.
        _git(clone, "update-ref", "-d", "refs/remotes/origin/fix/unmerged-sibling")
        assert allocation.sibling_refs_max_session() == 2335
        local_sessions = clone / ".agents" / "sessions"
        assert new_session_log._auto_detect_session_number(str(local_sessions)) == 2336

    def test_outside_any_repo_is_probe_failure_not_absence(self, tmp_path, monkeypatch):
        # Edge: no repo means the scan cannot run. That is a failed probe
        # (None), not evidence that siblings hold no sessions (0).
        monkeypatch.chdir(tmp_path)
        assert allocation.sibling_refs_max_session() is None
        # And the origin-only reading stays the best-effort 0 it always was.
        assert allocation.origin_main_max_session() == 0

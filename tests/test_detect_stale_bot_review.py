"""Tests for detect_stale_bot_review.py skill script (issue #5950)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1] / ".claude" / "skills" / "github" / "scripts" / "pr"
)
_MODULE = "detect_stale_bot_review"


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script(_MODULE)
classify = _mod.classify
main = _mod.main
build_parser = _mod.build_parser
build_dismissal_command = _mod.build_dismissal_command

HEAD = "h" * 40
OLD = "o" * 40
CODERABBIT = "coderabbitai[bot]"


def _review(
    review_id: int,
    login: str,
    state: str,
    commit: str,
    submitted: str,
    canonical: str | None = None,
    author_type: str | None = None,
) -> dict[str, Any]:
    return {
        "id": review_id,
        "author": login,
        "author_observed": login,
        "author_canonical": canonical or login,
        "author_type": author_type,
        "state": state,
        "commit_id": commit,
        "submittedAt": submitted,
        "url": f"https://github.com/o/r/pull/7#pullrequestreview-{review_id}",
    }


def _pr(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "head_sha": HEAD,
        "merge_state_status": "BLOCKED",
        "review_thread_unresolved_count": 0,
        "review_thread_counts_complete": True,
    }
    base.update(overrides)
    return base


def _classify(reviews, pr=None, ci_state="green") -> dict[str, Any]:
    return classify(
        owner="o",
        repo="r",
        pr_number=7,
        pr=pr if pr is not None else _pr(),
        ci_state=ci_state,
        reviews=reviews,
    )


def _stale_cr(login: str = CODERABBIT, review_id: int = 100, canonical: str | None = None):
    return _review(review_id, login, "CHANGES_REQUESTED", OLD, "2026-09-01T00:00:00Z", canonical)


class TestStaleClassification:
    def test_stale_coderabbit_review_requests_rereview_first(self):
        out = _classify([_stale_cr()])
        assert out["verdict"] == "REQUEST_REREVIEW"
        assert out["bots"][0]["rereview_trigger"] == "@coderabbitai review"
        assert out["bots"][0]["review_id"] == 100
        assert out["handoff"] is None

    def test_commented_rereview_at_head_does_not_supersede(self):
        rereview = _review(101, CODERABBIT, "COMMENTED", HEAD, "2026-09-02T00:00:00Z")
        out = _classify([_stale_cr(), rereview])
        assert out["verdict"] == "DISMISSAL_HANDOFF"
        assert out["bots"][0]["action"] == "DISMISSAL_HANDOFF"

    def test_handoff_names_review_commit_command_and_safety_reason(self):
        rereview = _review(101, CODERABBIT, "COMMENTED", HEAD, "2026-09-02T00:00:00Z")
        handoff = _classify([_stale_cr(), rereview])["handoff"]
        assert "review 100" in handoff
        assert f"commit {OLD}" in handoff
        assert "gh api -X PUT repos/o/r/pulls/7/reviews/100/dismissals" in handoff
        assert "-f event=DISMISS" in handoff
        assert "Every review thread is resolved and required CI checks pass" in handoff
        assert "does not check that the later commits fixed each finding" in handoff
        assert "The agent does not dismiss reviews" in handoff

    def test_approved_rereview_at_head_clears_the_block(self):
        approval = _review(101, CODERABBIT, "APPROVED", HEAD, "2026-09-02T00:00:00Z")
        out = _classify([_stale_cr(), approval])
        assert out["verdict"] == "NO_BOT_CHANGES_REQUESTED"
        assert out["bots"] == []

    def test_dismissed_review_clears_the_block(self):
        dismissed = _review(100, CODERABBIT, "DISMISSED", OLD, "2026-09-03T00:00:00Z")
        assert _classify([_stale_cr(), dismissed])["verdict"] == "NO_BOT_CHANGES_REQUESTED"

    def test_bot_without_known_trigger_goes_straight_to_handoff(self):
        review = _stale_cr(
            login="copilot-pull-request-reviewer[bot]", canonical="github-copilot[bot]"
        )
        out = _classify([review])
        assert out["verdict"] == "DISMISSAL_HANDOFF"
        assert out["bots"][0]["rereview_trigger"] is None
        assert "reviews/100/dismissals" in out["handoff"]

    def test_copilot_aliases_collapse_to_one_reviewer(self):
        old = _stale_cr(login="Copilot", review_id=100, canonical="github-copilot[bot]")
        newer = _review(
            101,
            "copilot-pull-request-reviewer[bot]",
            "COMMENTED",
            HEAD,
            "2026-09-02T00:00:00Z",
            "github-copilot[bot]",
        )
        out = _classify([old, newer])
        assert [b["review_id"] for b in out["bots"]] == [100]
        assert out["verdict"] == "DISMISSAL_HANDOFF"


class TestFreshAndAbsent:
    def test_change_request_on_head_is_fresh(self):
        review = _review(100, CODERABBIT, "CHANGES_REQUESTED", HEAD, "2026-09-01T00:00:00Z")
        out = _classify([review])
        assert out["verdict"] == "FRESH_CHANGES_REQUESTED"
        assert out["handoff"] is None

    def test_new_change_request_at_head_replaces_stale_one(self):
        newer = _review(101, CODERABBIT, "CHANGES_REQUESTED", HEAD, "2026-09-02T00:00:00Z")
        out = _classify([_stale_cr(), newer])
        assert out["verdict"] == "FRESH_CHANGES_REQUESTED"
        assert [b["review_id"] for b in out["bots"]] == [101]

    def test_no_reviews(self):
        out = _classify([])
        assert out["verdict"] == "NO_BOT_CHANGES_REQUESTED"
        assert out["handoff"] is None

    def test_commented_only_bot_is_not_a_blocker(self):
        review = _review(100, CODERABBIT, "COMMENTED", OLD, "2026-09-01T00:00:00Z")
        assert _classify([review])["verdict"] == "NO_BOT_CHANGES_REQUESTED"

    def test_pending_review_is_ignored(self):
        pending = _review(101, CODERABBIT, "PENDING", HEAD, "")
        assert _classify([_stale_cr(), pending])["verdict"] == "REQUEST_REREVIEW"

    def test_human_change_request_is_never_a_bot_blocker(self):
        human = _review(100, "alice", "CHANGES_REQUESTED", OLD, "2026-09-01T00:00:00Z")
        out = _classify([human])
        assert out["verdict"] == "NO_BOT_CHANGES_REQUESTED"
        assert out["human_changes_requested"] == ["alice"]

    def test_handoff_warns_when_a_human_change_request_also_stands(self):
        human = _review(99, "alice", "CHANGES_REQUESTED", OLD, "2026-09-01T00:00:00Z")
        rereview = _review(101, CODERABBIT, "COMMENTED", HEAD, "2026-09-02T00:00:00Z")
        handoff = _classify([human, _stale_cr(), rereview])["handoff"]
        assert "alice" in handoff
        assert "will not unblock" in handoff


class TestNotReady:
    @pytest.mark.parametrize(
        ("pr", "ci_state", "reason"),
        [
            (_pr(review_thread_unresolved_count=2), "green", "2 review thread(s) unresolved"),
            (_pr(review_thread_counts_complete=False), "green", "thread count is incomplete"),
            (_pr(review_thread_unresolved_count=None), "green", "thread count is incomplete"),
            (_pr(), "failing", "CI is not passing"),
            (_pr(), "unknown", "CI state is unknown"),
            (_pr(), "bogus", "CI state is unknown"),
            (_pr(merge_state_status="BEHIND"), "green", "merge state is BEHIND"),
            (_pr(merge_state_status="DIRTY"), "green", "merge state is DIRTY"),
            (_pr(merge_state_status="UNKNOWN"), "green", "merge state is UNKNOWN"),
            (_pr(merge_state_status=None), "green", "merge state is unknown"),
            (_pr(merge_state_status=""), "green", "merge state is unknown"),
            (_pr(head_sha=""), "green", "head SHA is unknown"),
        ],
    )
    def test_open_work_blocks_the_stale_review_path(self, pr, ci_state, reason):
        out = _classify([_stale_cr()], pr=pr, ci_state=ci_state)
        assert out["verdict"] == "NOT_READY"
        assert any(reason in r for r in out["reasons"])
        assert out["handoff"] is None

    @pytest.mark.parametrize("state", ["BLOCKED", "CLEAN", "UNSTABLE", "HAS_HOOKS"])
    def test_states_that_do_not_need_branch_work_stay_ready(self, state):
        """BLOCKED must pass: a stale CHANGES_REQUESTED review is what blocks the PR."""
        out = _classify([_stale_cr()], pr=_pr(merge_state_status=state))
        assert out["verdict"] == "REQUEST_REREVIEW"
        assert out["reasons"] == []

    def test_readiness_is_not_checked_when_no_bot_blocks(self):
        out = _classify([], pr=_pr(review_thread_unresolved_count=5), ci_state="failing")
        assert out["verdict"] == "NO_BOT_CHANGES_REQUESTED"
        assert out["reasons"] == []


class TestBotIdentity:
    """The API account type outranks the -bot naming guess (issue #6506)."""

    def test_user_account_ending_in_bot_is_a_human_blocker(self):
        review = _review(
            100,
            "robot-fan-bot",
            "CHANGES_REQUESTED",
            OLD,
            "2026-09-01T00:00:00Z",
            author_type="User",
        )
        out = _classify([review])
        assert out["verdict"] == "NO_BOT_CHANGES_REQUESTED"
        assert out["human_changes_requested"] == ["robot-fan-bot"]

    def test_same_login_without_a_type_keeps_the_naming_guess(self):
        review = _review(100, "robot-fan-bot", "CHANGES_REQUESTED", OLD, "2026-09-01T00:00:00Z")
        assert _classify([review])["verdict"] == "DISMISSAL_HANDOFF"

    def test_user_account_listed_in_bot_authors_is_still_a_bot(self):
        review = _review(
            100,
            "rjmurillo-bot",
            "CHANGES_REQUESTED",
            OLD,
            "2026-09-01T00:00:00Z",
            author_type="User",
        )
        assert _classify([review])["verdict"] == "DISMISSAL_HANDOFF"

    def test_bot_type_counts_without_a_bot_suffix(self):
        review = _review(
            100,
            "some-review-app",
            "CHANGES_REQUESTED",
            OLD,
            "2026-09-01T00:00:00Z",
            author_type="Bot",
        )
        assert _classify([review])["verdict"] == "DISMISSAL_HANDOFF"

    def test_non_string_type_is_ignored(self):
        review = _review(100, "x[bot]", "CHANGES_REQUESTED", OLD, "2026-09-01T00:00:00Z")
        review["author_type"] = 7
        assert _classify([review])["verdict"] == "DISMISSAL_HANDOFF"


class TestMixedBots:
    def test_fresh_request_outranks_stale_handoff(self):
        copilot = _stale_cr(
            login="copilot-pull-request-reviewer[bot]",
            review_id=200,
            canonical="github-copilot[bot]",
        )
        fresh = _review(
            300, "github-actions[bot]", "CHANGES_REQUESTED", HEAD, "2026-09-02T00:00:00Z"
        )
        assert _classify([copilot, fresh])["verdict"] == "FRESH_CHANGES_REQUESTED"

    def test_rereview_outranks_handoff(self):
        copilot = _stale_cr(
            login="copilot-pull-request-reviewer[bot]",
            review_id=200,
            canonical="github-copilot[bot]",
        )
        assert _classify([_stale_cr(), copilot])["verdict"] == "REQUEST_REREVIEW"

    def test_handoff_lists_only_bots_that_need_dismissal(self):
        copilot = _stale_cr(
            login="copilot-pull-request-reviewer[bot]",
            review_id=200,
            canonical="github-copilot[bot]",
        )
        rereview = _review(101, CODERABBIT, "COMMENTED", HEAD, "2026-09-02T00:00:00Z")
        out = _classify([_stale_cr(), rereview, copilot])
        assert out["verdict"] == "DISMISSAL_HANDOFF"
        assert "reviews/100/dismissals" in out["handoff"]
        assert "reviews/200/dismissals" in out["handoff"]


def test_dismissal_command_is_a_single_put_to_the_dismissals_endpoint():
    command = build_dismissal_command("o", "r", 7, 100)
    assert command.startswith("gh api -X PUT repos/o/r/pulls/7/reviews/100/dismissals")

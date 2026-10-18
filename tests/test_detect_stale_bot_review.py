"""Tests for detect_stale_bot_review.py skill script (issue #5950)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

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
) -> dict[str, Any]:
    return {
        "id": review_id,
        "author": login,
        "author_observed": login,
        "author_canonical": canonical or login,
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
            (_pr(head_sha=""), "green", "head SHA is unknown"),
        ],
    )
    def test_open_work_blocks_the_stale_review_path(self, pr, ci_state, reason):
        out = _classify([_stale_cr()], pr=pr, ci_state=ci_state)
        assert out["verdict"] == "NOT_READY"
        assert any(reason in r for r in out["reasons"])
        assert out["handoff"] is None

    def test_readiness_is_not_checked_when_no_bot_blocks(self):
        out = _classify([], pr=_pr(review_thread_unresolved_count=5), ci_state="failing")
        assert out["verdict"] == "NO_BOT_CHANGES_REQUESTED"
        assert out["reasons"] == []


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


# --- main() wiring -------------------------------------------------------


def _checks(
    required_state: str = "SUCCESS",
    all_passing: bool = True,
    merge_ref_usable: bool | None = True,
    required_rows: bool = True,
) -> dict[str, Any]:
    """Build a get_pr_checks.py Data payload.

    A None merge_ref_usable omits the key. required_rows False emits one optional
    row only, the shape of a repo that requires reviews but no status checks.
    """
    data: dict[str, Any] = {
        "RequiredState": required_state,
        "AllPassing": all_passing,
        "Checks": [{"Name": "build", "IsRequired": required_rows}],
    }
    if merge_ref_usable is not None:
        data["MergeRefUsable"] = merge_ref_usable
    return data


def _siblings(context, checks, reviews, calls):
    def fake(script, args):
        calls.append(script)
        return {
            "get_pr_context.py": (0, context),
            "get_pr_checks.py": checks,
            "get_pr_reviews.py": (0, {"reviews": reviews} if reviews is not None else None),
        }[script]

    return fake


def _fake_repo():
    return type("R", (), {"owner": "o", "repo": "r"})()


def _run_main(fake, argv=None):
    with (
        patch(f"{_MODULE}.assert_gh_authenticated"),
        patch(f"{_MODULE}.resolve_repo_params", return_value=_fake_repo()),
        patch(f"{_MODULE}._run_sibling", side_effect=fake),
    ):
        return main(argv or ["--pull-request", "7", "--output-format", "json"])


class TestMain:
    def test_emits_handoff_envelope_and_only_reads(self, capsys):
        calls: list[str] = []
        rereview = _review(101, CODERABBIT, "COMMENTED", HEAD, "2026-09-02T00:00:00Z")
        fake = _siblings(_pr(), (0, _checks()), [_stale_cr(), rereview], calls)

        assert _run_main(fake) == 0

        envelope = json.loads(capsys.readouterr().out)
        assert envelope["Success"] is True
        assert envelope["Data"]["verdict"] == "DISMISSAL_HANDOFF"
        assert "reviews/100/dismissals" in envelope["Data"]["handoff"]
        assert sorted(calls) == ["get_pr_checks.py", "get_pr_context.py", "get_pr_reviews.py"]

    @pytest.mark.parametrize("exit_code", [0, 1], ids=["pending_optional", "failing_optional"])
    def test_optional_checks_do_not_block_the_handoff(self, exit_code, capsys):
        # Issue #6632: PR #6431 had 9/9 required checks green and 7 optional checks
        # in WAITING. AllPassing was False, RequiredState was SUCCESS.
        rereview = _review(101, CODERABBIT, "COMMENTED", HEAD, "2026-09-02T00:00:00Z")
        checks = (exit_code, _checks("SUCCESS", all_passing=False))
        fake = _siblings(_pr(), checks, [_stale_cr(), rereview], [])
        assert _run_main(fake) == 0
        data = json.loads(capsys.readouterr().out)["Data"]
        assert data["verdict"] == "DISMISSAL_HANDOFF"
        assert "reviews/100/dismissals" in data["handoff"]
        assert "required CI checks pass" in data["handoff"]
        assert "CI is green" not in data["handoff"]

    def test_failing_optional_check_with_no_required_checks_reports_not_ready(self, capsys):
        # A repo can require reviews but no status checks. RequiredState is then
        # SUCCESS vacuously, so AllPassing must decide.
        fake = _siblings(
            _pr(),
            (1, _checks("SUCCESS", all_passing=False, required_rows=False)),
            [_stale_cr()],
            [],
        )
        assert _run_main(fake) == 0
        data = json.loads(capsys.readouterr().out)["Data"]
        assert data["verdict"] == "NOT_READY"
        assert "CI is not passing" in data["reasons"]

    def test_passing_checks_with_no_required_checks_reach_the_handoff(self, capsys):
        rereview = _review(101, CODERABBIT, "COMMENTED", HEAD, "2026-09-02T00:00:00Z")
        fake = _siblings(
            _pr(),
            (0, _checks("SUCCESS", all_passing=True, required_rows=False)),
            [_stale_cr(), rereview],
            [],
        )
        assert _run_main(fake) == 0
        assert json.loads(capsys.readouterr().out)["Data"]["verdict"] == "DISMISSAL_HANDOFF"

    @pytest.mark.parametrize(
        ("exit_code", "checks", "reason"),
        [
            (1, _checks("FAILURE", False), "CI is not passing"),
            (0, _checks("PENDING"), "CI is not passing"),
            (0, _checks("SUCCESS", merge_ref_usable=False), "CI is not passing"),
            (0, _checks("UNKNOWN"), "CI state is unknown"),
            # Issue #6632 shape over REST: required row passed, optional row WAITING.
            # REST cannot prove the required set, so a driver must re-run, not fix CI.
            (0, _checks("UNKNOWN", all_passing=False), "CI state is unknown"),
            # REST with an empty ruleset marks no row required and reports UNKNOWN
            # even when every check passes. Classic branch protection may still
            # require a check, so AllPassing alone must not reach the handoff.
            (0, _checks("UNKNOWN", required_rows=False), "CI state is unknown"),
            (0, _checks("PENDING", required_rows=False), "CI state is unknown"),
            (7, _checks("UNKNOWN", False), "CI state is unknown"),
            # build_output always emits these keys, so a missing one is malformed.
            (0, _checks("SUCCESS", merge_ref_usable=None), "CI state is unknown"),
            (
                0,
                {"AllPassing": True, "MergeRefUsable": True, "Checks": [{"IsRequired": True}]},
                "CI state is unknown",
            ),
        ],
        ids=[
            "failing_required",
            "pending_required",
            "unusable_merge_ref",
            "unknown_required",
            "rest_optional_pending",
            "no_required_rows_unknown",
            "no_required_rows_pending",
            "incomplete_exit_7",
            "merge_ref_key_missing",
            "required_state_key_missing",
        ],
    )
    def test_ci_not_proven_green_reports_not_ready(self, exit_code, checks, reason, capsys):
        # AllPassing True never rescues a required set that is failing or unproven.
        fake = _siblings(_pr(), (exit_code, checks), [_stale_cr()], [])
        assert _run_main(fake) == 0
        data = json.loads(capsys.readouterr().out)["Data"]
        assert data["verdict"] == "NOT_READY"
        assert data["reasons"] == [reason]
        assert data["handoff"] is None

    def test_checks_call_does_not_pass_required_only(self):
        # --required-only exits 3 on the REST fallback with no ruleset contexts,
        # which _fetch_inputs rejects. Read RequiredState from the unflagged call.
        seen: list[list[str]] = []

        def fake(script, args):
            if script == "get_pr_checks.py":
                seen.append(args)
            return _siblings(_pr(), (0, _checks()), [_stale_cr()], [])(script, args)

        assert _run_main(fake) == 0
        assert seen
        assert all("--required-only" not in a for a in seen)

    def test_context_failure_exits_3(self, capsys):
        fake = _siblings(None, (0, _checks()), [], [])
        assert _run_main(fake) == 3
        assert json.loads(capsys.readouterr().out)["Success"] is False

    def test_checks_error_envelope_exits_3(self, capsys):
        fake = _siblings(_pr(), (3, {"Number": 7}), [_stale_cr()], [])
        assert _run_main(fake) == 3
        assert json.loads(capsys.readouterr().out)["Success"] is False

    def test_unreadable_checks_exits_3(self):
        fake = _siblings(_pr(), (3, None), [], [])
        assert _run_main(fake) == 3

    def test_review_fetch_failure_exits_3(self):
        fake = _siblings(_pr(), (0, _checks()), None, [])
        assert _run_main(fake) == 3

    def test_sibling_timeout_exits_3(self):
        def fake(script, args):
            raise subprocess.TimeoutExpired(cmd=script, timeout=1)

        assert _run_main(fake) == 3

    def test_human_format_prints_the_handoff(self, capsys):
        rereview = _review(101, CODERABBIT, "COMMENTED", HEAD, "2026-09-02T00:00:00Z")
        fake = _siblings(_pr(), (0, _checks()), [_stale_cr(), rereview], [])
        assert _run_main(fake, ["--pull-request", "7", "--output-format", "human"]) == 0
        assert "gh api -X PUT" in capsys.readouterr().out


class TestRunSibling:
    def _completed(self, stdout: str, rc: int = 0):
        return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr="")

    def test_returns_data_from_envelope(self):
        payload = json.dumps({"Success": True, "Data": {"a": 1}})
        with patch(f"{_MODULE}.subprocess.run", return_value=self._completed(payload)) as run:
            code, data = _mod._run_sibling("get_pr_checks.py", ["--pull-request", "7"])
        assert (code, data) == (0, {"a": 1})
        cmd = run.call_args.args[0]
        assert cmd[0] == sys.executable
        assert cmd[1].endswith("get_pr_checks.py")
        assert cmd[-2:] == ["--output-format", "json"]

    def test_keeps_nonzero_exit_code_with_data(self):
        payload = json.dumps({"Success": True, "Data": {"AllPassing": False}})
        with patch(f"{_MODULE}.subprocess.run", return_value=self._completed(payload, 1)):
            assert _mod._run_sibling("x.py", []) == (1, {"AllPassing": False})

    def test_unparsable_output_yields_none(self):
        with patch(f"{_MODULE}.subprocess.run", return_value=self._completed("oops", 3)):
            assert _mod._run_sibling("x.py", []) == (3, None)

    def test_non_object_envelope_yields_none(self):
        with patch(f"{_MODULE}.subprocess.run", return_value=self._completed("[1]")):
            assert _mod._run_sibling("x.py", []) == (0, None)

    def test_envelope_without_object_data_yields_none(self):
        payload = json.dumps({"Success": False, "Data": None})
        with patch(f"{_MODULE}.subprocess.run", return_value=self._completed(payload, 3)):
            assert _mod._run_sibling("x.py", []) == (3, None)


class TestBuildParser:
    def test_pull_request_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_defaults(self):
        args = build_parser().parse_args(["--pull-request", "99"])
        assert args.pull_request == 99
        assert args.owner == ""
        assert args.repo == ""

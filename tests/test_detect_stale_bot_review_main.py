"""main() wiring, sibling-script runner, and parser tests for detect_stale_bot_review.py.

Split from test_detect_stale_bot_review.py to keep each file under the 500 line taste limit.
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any
from unittest.mock import patch

import pytest

from tests.test_detect_stale_bot_review import (
    _MODULE,
    CODERABBIT,
    HEAD,
    _mod,
    _pr,
    _review,
    _stale_cr,
    build_parser,
    main,
)

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
        assert sorted(calls) == [
            "get_pr_checks.py",
            "get_pr_context.py",
            "get_pr_context.py",
            "get_pr_reviews.py",
        ]

    def test_head_moved_while_fetching_exits_3(self, capsys):
        """A push between the first context read and the last call voids every input."""
        contexts = [_pr(), _pr(head_sha="n" * 40)]

        def fake(script, args):
            return {
                "get_pr_context.py": lambda: (0, contexts.pop(0)),
                "get_pr_checks.py": lambda: (0, _checks()),
                "get_pr_reviews.py": lambda: (0, {"reviews": [_stale_cr()]}),
            }[script]()

        assert _run_main(fake) == 3
        envelope = json.loads(capsys.readouterr().out)
        assert envelope["Success"] is False
        assert "head moved" in envelope["Error"]["Message"]

    def test_thread_opened_during_fetch_blocks_the_handoff(self, capsys):
        """A thread opened without a push must show in the verdict, not the first read."""
        contexts = [_pr(), _pr(review_thread_unresolved_count=1)]

        def fake(script, args):
            return {
                "get_pr_context.py": lambda: (0, contexts.pop(0)),
                "get_pr_checks.py": lambda: (0, _checks()),
                "get_pr_reviews.py": lambda: (0, {"reviews": [_stale_cr()]}),
            }[script]()

        assert _run_main(fake) == 0
        data = json.loads(capsys.readouterr().out)["Data"]
        assert data["verdict"] == "NOT_READY"
        assert data["handoff"] is None
        assert data["reasons"] == ["1 review thread(s) unresolved"]

    def test_merge_state_lost_during_fetch_blocks_the_handoff(self, capsys):
        contexts = [_pr(), _pr(merge_state_status="UNKNOWN")]

        def fake(script, args):
            return {
                "get_pr_context.py": lambda: (0, contexts.pop(0)),
                "get_pr_checks.py": lambda: (0, _checks()),
                "get_pr_reviews.py": lambda: (0, {"reviews": [_stale_cr()]}),
            }[script]()

        assert _run_main(fake) == 0
        data = json.loads(capsys.readouterr().out)["Data"]
        assert data["verdict"] == "NOT_READY"
        assert data["reasons"] == ["merge state is UNKNOWN"]

    def test_head_recheck_failure_exits_3(self, capsys):
        contexts = [(0, _pr()), (3, None)]

        def fake(script, args):
            if script == "get_pr_context.py":
                return contexts.pop(0)
            return {
                "get_pr_checks.py": (0, _checks()),
                "get_pr_reviews.py": (0, {"reviews": [_stale_cr()]}),
            }[script]

        assert _run_main(fake) == 3
        assert "recheck failed" in json.loads(capsys.readouterr().out)["Error"]["Message"]

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
            # RequiredState PENDING or FAILURE is proven required even with no row
            # marked required (a ruleset context that never reported).
            (0, _checks("PENDING", required_rows=False), "CI is not passing"),
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

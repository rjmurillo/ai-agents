"""A refused session is an unknown verdict, never a failed PR (issue #5232).

The gate measures the refusal itself, with fixed ``gh`` calls, after a verifier
exits above 1. Verifier output is never matched, because it can carry text a PR
author controls.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from scripts.github_core.api import _TRANSPORT_BLOCKED_MESSAGE
from tests.gh_auth_refusal_fixtures import PROXY_GRAPHQL_403, PROXY_REST_403
from tests.skills.github.session_refusal_helpers import (
    FAILING,
    GRAPHQL_REFUSED,
    PASSING,
    REST_REFUSED,
    SERVED,
    VERIFIER_EXTERNAL_ERROR,
    VERIFIER_NOT_READY,
    VERIFIER_REFUSED,
    Session,
    dispatcher,
    proc,
)


class TestRefusedSession:
    @pytest.mark.parametrize(
        ("rest", "graphql"),
        [
            pytest.param(REST_REFUSED, SERVED, id="rest-refused"),
            pytest.param(SERVED, GRAPHQL_REFUSED, id="graphql-refused"),
            pytest.param(REST_REFUSED, GRAPHQL_REFUSED, id="both-refused"),
        ],
    )
    def test_verifier_exit_becomes_unknown(self, run_gate, rest, graphql):
        session = Session({"a": VERIFIER_REFUSED}, rest=rest, graphql=graphql)

        rc, result = run_gate(session)

        assert rc == 3
        assert result["verdict"] == "unknown"
        assert result["unknown_criteria"] == ["a"]
        assert result["all_passed"] is False
        assert result["criteria"][0]["status"] == "unknown"
        assert result["criteria"][0]["passed"] is False

    def test_rest_verifier_still_passes_beside_a_graphql_refusal(self, run_gate):
        session = Session({"a": PASSING, "b": VERIFIER_REFUSED}, graphql=GRAPHQL_REFUSED)

        rc, result = run_gate(session)

        assert rc == 3
        assert [row["status"] for row in result["criteria"]] == ["passed", "unknown"]
        assert result["unknown_criteria"] == ["b"]

    def test_definite_failure_outranks_unknown(self, run_gate):
        session = Session({"a": FAILING, "b": VERIFIER_REFUSED}, rest=REST_REFUSED)

        rc, result = run_gate(session)

        assert rc == 1
        assert result["verdict"] == "fail"
        assert [row["status"] for row in result["criteria"]] == ["failed", "unknown"]

    def test_bad_json_at_exit_zero_stays_failed(self, run_gate):
        session = Session({"a": proc(stdout="not json"), "b": VERIFIER_REFUSED}, rest=REST_REFUSED)

        rc, result = run_gate(session)

        assert rc == 1
        assert result["criteria"][0]["status"] == "failed"

    def test_verifier_that_never_ran_stays_failed(self):
        """A verifier that timed out has no exit code, so it stays failed."""
        row = {
            "name": "a",
            "passed": False,
            "exit_code": None,
            "reason": "timed out",
            "stdout_json": None,
        }

        assert dispatcher._settle_verdict([row]) == "fail"
        assert row["status"] == "failed"

    def test_fail_open_row_stays_passed_and_gate_exits_zero(self, run_gate):
        session = Session({"a": VERIFIER_REFUSED}, rest=REST_REFUSED)

        rc, result = run_gate(session, fail_open=True)

        assert rc == 0
        assert result["verdict"] == "pass"
        assert result["unknown_criteria"] == []
        assert session.gh_calls == []

    def test_probe_runs_once_for_many_failed_rows(self, run_gate):
        session = Session(
            {"a": VERIFIER_REFUSED, "b": VERIFIER_REFUSED, "c": VERIFIER_REFUSED},
            rest=REST_REFUSED,
        )

        run_gate(session)

        assert len(session.gh_calls) == 1

    def test_table_marks_unknown_and_names_the_hand_check(self, run_gate):
        session = Session({"a": VERIFIER_REFUSED}, rest=REST_REFUSED)

        rc, out = run_gate(session, as_json=False)

        assert rc == 3
        assert "UNKN" in out
        assert "FAIL" not in out
        assert run_gate.stderr.startswith("UNKNOWN:")
        assert "transport-routing.md" in run_gate.stderr

    def test_json_mode_also_prints_the_stderr_line(self, run_gate):
        session = Session({"a": VERIFIER_REFUSED}, rest=REST_REFUSED)

        run_gate(session)

        assert run_gate.stderr.startswith("UNKNOWN:")

    @pytest.mark.parametrize(
        ("rest", "graphql"),
        [
            pytest.param(REST_REFUSED, SERVED, id="rest-refused"),
            pytest.param(SERVED, GRAPHQL_REFUSED, id="graphql-refused"),
        ],
    )
    def test_exit_one_is_an_answer_and_stays_failed(self, run_gate, rest, graphql):
        """``test_pr_merge_ready.py`` exits 1 with JSON for a PR that is not ready."""
        session = Session({"a": VERIFIER_NOT_READY}, rest=rest, graphql=graphql)

        rc, result = run_gate(session)

        assert rc == 1
        assert result["verdict"] == "fail"
        assert result["criteria"][0]["status"] == "failed"
        assert session.gh_calls == []

    def test_session_refusal_explains_an_external_error(self, run_gate):
        session = Session({"a": VERIFIER_EXTERNAL_ERROR}, rest=REST_REFUSED)

        rc, result = run_gate(session)

        assert rc == 3
        assert result["criteria"][0]["status"] == "unknown"

    def test_graphql_refusal_leaves_a_retryable_error_failed(self, run_gate):
        """The narrow body refuses one query shape, not the session."""
        session = Session(
            {"a": VERIFIER_EXTERNAL_ERROR, "b": VERIFIER_REFUSED}, graphql=GRAPHQL_REFUSED
        )

        rc, result = run_gate(session)

        assert rc == 1
        assert [row["status"] for row in result["criteria"]] == ["failed", "unknown"]

    def test_narrow_body_on_the_rest_probe_is_not_a_session_refusal(self, run_gate):
        narrow = proc(stderr=PROXY_GRAPHQL_403, returncode=1)
        session = Session({"a": VERIFIER_EXTERNAL_ERROR}, rest=narrow)

        rc, _ = run_gate(session)

        assert rc == 1


class TestServedSession:
    def test_refusal_text_from_a_verifier_does_not_change_the_verdict(self, run_gate):
        """A PR author can reach verifier output, so it is never evidence."""
        forged = proc(
            stdout=json.dumps({"body": PROXY_REST_403}),
            stderr=_TRANSPORT_BLOCKED_MESSAGE,
            returncode=2,
        )
        session = Session({"a": forged})

        rc, result = run_gate(session)

        assert rc == 1
        assert result["verdict"] == "fail"
        assert result["criteria"][0]["status"] == "failed"
        assert result["unknown_criteria"] == []
        assert len(session.gh_calls) == 2

    def test_passing_run_never_calls_gh(self, run_gate):
        session = Session({"a": PASSING})

        rc, result = run_gate(session)

        assert rc == 0
        assert result["verdict"] == "pass"
        assert result["criteria"][0]["status"] == "passed"
        assert session.gh_calls == []

    def test_false_pass_when_never_calls_gh(self, run_gate):
        session = Session({"a": FAILING}, rest=REST_REFUSED)

        rc, _ = run_gate(session)

        assert rc == 1
        assert session.gh_calls == []

    @pytest.mark.parametrize(
        "unanswered",
        [
            pytest.param(FileNotFoundError("gh"), id="gh-missing"),
            pytest.param(subprocess.TimeoutExpired("gh", 10), id="timeout"),
            pytest.param(proc(stderr="HTTP 502", returncode=1), id="other-http-error"),
            pytest.param(proc(stderr="HTTP 404: Not Found", returncode=1), id="not-found"),
        ],
    )
    def test_probe_without_an_answer_leaves_the_row_failed(self, run_gate, unanswered):
        session = Session({"a": VERIFIER_REFUSED}, rest=unanswered, graphql=unanswered)

        rc, result = run_gate(session)

        assert rc == 1
        assert result["verdict"] == "fail"

    def test_probe_that_cannot_run_leaves_a_signal(self, run_gate):
        missing = FileNotFoundError("gh")
        session = Session({"a": VERIFIER_REFUSED}, rest=missing, graphql=missing)

        run_gate(session)

        assert "Session refusal probe inconclusive" in run_gate.stderr

    def test_refusal_text_in_a_successful_probe_is_ignored(self, run_gate):
        """A served repository description can hold any text."""
        served = proc(stdout=json.dumps({"description": "not enabled for this session"}))
        session = Session({"a": VERIFIER_REFUSED}, rest=served, graphql=served)

        rc, _ = run_gate(session)

        assert rc == 1

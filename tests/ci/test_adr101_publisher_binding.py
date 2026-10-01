"""Binding, tamper and API-failure cases for the ADR-101 publisher (issue #5245)."""

from __future__ import annotations

from dataclasses import asdict

import pytest

from scripts.ci import adr101_publisher as pub
from scripts.ci.adr101_publisher_github import ApiError, CheckRunState, PullState, RunState
from scripts.ci.adr101_publisher_inputs import CHECK_NAME, PublisherEnv, exit_code, revision_digest
from scripts.validation.evidence import EvidenceState
from tests.ci.adr101_publisher_helpers import (
    APP_ID,
    BASE,
    HEAD,
    FakeApi,
    make_env,
    refuse_api,
    run_publish,
)


class TestTamperedEvidence:
    @pytest.mark.parametrize(
        "bad_sha",
        ["", "abc", "A" * 40, "g" * 40, "a" * 39, "a" * 41, "a" * 40 + "\n$(id)", "a" * 64],
    )
    def test_a_malformed_head_sha_is_fail_and_makes_no_call(self, bad_sha: str) -> None:
        env = PublisherEnv.from_environ(make_env(ADR101_HEAD_SHA=bad_sha))

        outcome = pub.publish(env, refuse_api)

        assert outcome.state is EvidenceState.FAIL
        assert outcome.reason == "input.invalid"

    @pytest.mark.parametrize(
        "override",
        [
            {"ADR101_REPOSITORY": "../etc/passwd"},
            {"ADR101_REPOSITORY": "owner/name/extra"},
            {"ADR101_REPOSITORY": "a b/c"},
            {"ADR101_TRIGGER_RUN_ID": "12;id"},
            {"ADR101_TRIGGER_RUN_ID": ""},
            {"ADR101_PULL_NUMBER": "4 2"},
            {"ADR101_EXECUTE_RESULT": "ok"},
            {"ADR101_EXECUTE_RESULT": ""},
        ],
    )
    def test_any_malformed_event_value_is_fail_before_any_call(
        self, override: dict[str, str]
    ) -> None:
        env = PublisherEnv.from_environ(make_env(**override))

        outcome = pub.publish(env, refuse_api)

        assert outcome.state is EvidenceState.FAIL
        assert outcome.reason == "input.invalid"
        assert exit_code(outcome) == 1

    def test_a_pull_head_that_is_not_the_event_sha_is_fail_and_publishes_nothing(self) -> None:
        api = FakeApi(pull=PullState(head_sha="c" * 40, base_sha=BASE))

        outcome = run_publish(api)

        assert outcome.state is EvidenceState.FAIL
        assert outcome.reason == "revision.moved"
        assert api.created == []

    def test_a_head_that_moves_between_the_two_reads_publishes_nothing(self) -> None:
        api = FakeApi(pull_after=PullState(head_sha="c" * 40, base_sha=BASE))

        outcome = run_publish(api)

        assert outcome.state is EvidenceState.FAIL
        assert outcome.reason == "revision.moved"
        assert api.created == []

    def test_a_base_that_moves_between_the_two_reads_publishes_nothing(self) -> None:
        api = FakeApi(pull_after=PullState(head_sha=HEAD, base_sha="d" * 40))

        outcome = run_publish(api)

        assert outcome.reason == "revision.moved"
        assert api.created == []

    def test_a_workflow_run_with_another_head_sha_is_fail(self) -> None:
        api = FakeApi(run=RunState(head_sha="c" * 40, status="completed"))

        outcome = run_publish(api)

        assert outcome.state is EvidenceState.FAIL
        assert outcome.reason == "evidence.mismatch"
        assert api.created == []

    def test_a_workflow_run_not_completed_is_fail(self) -> None:
        api = FakeApi(run=RunState(head_sha=HEAD, status="in_progress"))

        assert run_publish(api).state is EvidenceState.FAIL

    @pytest.mark.parametrize(
        "field_name, value",
        [
            ("app_id", "999"),
            ("head_sha", "c" * 40),
            ("name", "Run Python Tests"),
            ("conclusion", "neutral"),
            ("external_id", "tampered"),
        ],
    )
    def test_a_read_back_that_differs_is_fail_and_is_retracted(
        self, field_name: str, value: str
    ) -> None:
        good = CheckRunState(777, CHECK_NAME, HEAD, "success", revision_digest(HEAD, BASE), APP_ID)
        api = FakeApi(read_back=CheckRunState(**{**asdict(good), field_name: value}))

        outcome = run_publish(api)

        assert outcome.state is EvidenceState.FAIL
        assert outcome.reason == "evidence.mismatch"
        assert api.conclusions == [(777, "failure")]
        assert exit_code(outcome) == 1

    def test_a_read_back_that_cannot_be_read_is_unknown_and_retracted(self) -> None:
        api = FakeApi(fail_on={"get_check_run": ApiError(500, "http error")})

        outcome = run_publish(api)

        assert outcome.state is EvidenceState.UNKNOWN
        assert api.conclusions == [(777, "failure")]

    def test_a_failed_retraction_still_reports_the_failure(self) -> None:
        api = FakeApi(
            fail_on={"get_check_run": ApiError(500, "x"), "set_conclusion": ApiError(500, "x")}
        )

        assert run_publish(api).state is EvidenceState.UNKNOWN


class TestExecuteConclusion:
    @pytest.mark.parametrize("result", ["failure", "cancelled", "skipped"])
    def test_a_non_success_execute_publishes_failure_not_nothing(self, result: str) -> None:
        api = FakeApi()

        outcome = run_publish(api, ADR101_EXECUTE_RESULT=result)

        assert outcome.state is EvidenceState.FAIL
        assert outcome.reason == "execution.failed"
        assert [c["conclusion"] for c in api.created] == ["failure"]
        assert result in api.created[0]["summary"]

    def test_no_state_ever_publishes_skipped_or_neutral(self) -> None:
        conclusions = set()
        for result in ("success", "failure", "cancelled", "skipped"):
            api = FakeApi()
            run_publish(api, ADR101_EXECUTE_RESULT=result)
            conclusions |= {c["conclusion"] for c in api.created}

        assert conclusions == {"success", "failure"}

    def test_a_failure_that_cannot_be_published_keeps_the_original_outcome(self) -> None:
        api = FakeApi(fail_on={"create_check_run": ApiError(500, "http error")})

        outcome = run_publish(api, ADR101_EXECUTE_RESULT="failure")

        assert outcome.state is EvidenceState.FAIL
        assert "could not be published" in outcome.detail

    def test_a_head_that_moved_before_the_failure_run_publishes_nothing(self) -> None:
        api = FakeApi(pull_after=PullState(head_sha="c" * 40, base_sha=BASE))

        outcome = run_publish(api, ADR101_EXECUTE_RESULT="failure")

        assert outcome.reason == "revision.moved"
        assert api.created == []

    def test_no_pull_request_is_unknown_and_publishes_nothing(self) -> None:
        api = FakeApi()

        outcome = run_publish(api, ADR101_PULL_NUMBER="")

        assert outcome.state is EvidenceState.UNKNOWN
        assert outcome.reason == "pr.unresolved"
        assert api.created == []
        assert api.calls == []

    def test_a_failed_retraction_says_a_success_run_remains(self) -> None:
        good = CheckRunState(777, CHECK_NAME, HEAD, "success", revision_digest(HEAD, BASE), APP_ID)
        api = FakeApi(
            read_back=CheckRunState(**{**asdict(good), "app_id": "999"}),
            fail_on={"set_conclusion": ApiError(500, "http error")},
        )

        outcome = run_publish(api)

        assert outcome.state is EvidenceState.FAIL
        assert "success check run remains" in outcome.detail

    def test_an_unreadable_read_back_with_a_failed_retraction_says_so(self) -> None:
        api = FakeApi(
            fail_on={"get_check_run": ApiError(500, "x"), "set_conclusion": ApiError(500, "x")}
        )

        outcome = run_publish(api)

        assert outcome.state is EvidenceState.UNKNOWN
        assert "success check run remains" in outcome.detail


class TestApiFailures:
    @pytest.mark.parametrize("status", [401, 403])
    def test_a_refused_token_is_blocked_on_auth(self, status: int) -> None:
        api = FakeApi(fail_on={"get_pull": ApiError(status, "http error")})

        outcome = run_publish(api)

        assert outcome.state is EvidenceState.BLOCKED
        assert exit_code(outcome) == 4
        assert api.created == []

    @pytest.mark.parametrize("status", [0, 404, 500])
    def test_any_other_failure_is_blocked_external(self, status: int) -> None:
        api = FakeApi(fail_on={"get_run": ApiError(status, "transport error")})

        outcome = run_publish(api)

        assert outcome.state is EvidenceState.BLOCKED
        assert outcome.reason == "lookup.failed"
        assert exit_code(outcome) == 3

    def test_a_failed_create_blocks_and_publishes_nothing(self) -> None:
        api = FakeApi(fail_on={"create_check_run": ApiError(500, "http error")})

        outcome = run_publish(api)

        assert outcome.state is EvidenceState.BLOCKED
        assert "nothing was published" in outcome.detail

    def test_no_output_carries_a_token(self, capsys: pytest.CaptureFixture[str]) -> None:
        api = FakeApi(fail_on={"get_pull": ApiError(403, "http error")})
        outcome = run_publish(api)

        pub.report(outcome, make_env())

        out = capsys.readouterr().out
        assert "ghs_installation_token" not in out
        assert "ghs_read_token" not in out

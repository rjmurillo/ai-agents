"""Tests for scripts/ci/adr101_publisher.py (ADR-101 requirement 2a, issue #5245).

The four states the owner asked for each have a test that drives ``main``, so
the exit code a workflow step reads is what is asserted:

  flag off              -> SKIP, exit 0, nothing published
  flag on, no secrets   -> BLOCKED, exit 4, nothing published
  mocked valid token    -> PASS, one check run, read back
  tampered SHA/evidence -> FAIL, exit 1

The API is a recording fake. No test reaches the network.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest

from scripts.ci import adr101_publisher as pub
from scripts.ci.adr101_publisher_github import (
    ApiError,
    CheckRunState,
    PullState,
    RunState,
)
from scripts.ci.adr101_publisher_inputs import (
    CHECK_NAME,
    PUBLISHED_LABEL,
    PublisherEnv,
    exit_code,
    revision_digest,
)
from scripts.validation.evidence import CheckOutcome, EvidenceState

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ci" / "adr101_publisher.py"
HEAD = "a" * 40
BASE = "b" * 40
APP_ID = "123456"


def make_env(**overrides: str) -> dict[str, str]:
    """A fully valid, enabled environment. Override one field to break it."""
    values = {
        "ADR101_PUBLISHER_ENABLED": "true",
        "ADR101_PUBLISHER_APP_ID": APP_ID,
        "ADR101_HAS_KEY": "true",
        "ADR101_APP_TOKEN": "ghs_installation_token",
        "ADR101_APP_TOKEN_OUTCOME": "success",
        "ADR101_READ_TOKEN": "ghs_read_token",
        "ADR101_REPOSITORY": "rjmurillo/ai-agents",
        "ADR101_HEAD_SHA": HEAD,
        "ADR101_PULL_NUMBER": "42",
        "ADR101_TRIGGER_RUN_ID": "9001",
        "ADR101_TRIGGER_EVENT": "pull_request",
        "ADR101_EXECUTE_RESULT": "success",
    }
    values.update(overrides)
    return values


@dataclass
class FakeApi:
    """Records every call. Each field is the value the matching call returns."""

    pull: PullState = PullState(head_sha=HEAD, base_sha=BASE)
    pull_after: PullState | None = None
    run: RunState = RunState(head_sha=HEAD, status="completed")
    read_back: CheckRunState | None = None
    fail_on: dict[str, ApiError] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)
    created: list[dict[str, str]] = field(default_factory=list)
    conclusions: list[tuple[int, str]] = field(default_factory=list)
    _pull_reads: int = 0

    def _maybe_fail(self, name: str) -> None:
        self.calls.append(name)
        if name in self.fail_on:
            raise self.fail_on[name]

    def get_pull(self, number: str) -> PullState:
        self._maybe_fail("get_pull")
        self._pull_reads += 1
        if self._pull_reads > 1 and self.pull_after is not None:
            return self.pull_after
        return self.pull

    def get_run(self, run_id: str) -> RunState:
        self._maybe_fail("get_run")
        return self.run

    def create_check_run(
        self, head_sha: str, conclusion: str, external_id: str, title: str, summary: str
    ) -> int:
        self._maybe_fail("create_check_run")
        self.created.append(
            {
                "head_sha": head_sha,
                "conclusion": conclusion,
                "external_id": external_id,
                "title": title,
                "summary": summary,
            }
        )
        return 777

    def get_check_run(self, check_id: int) -> CheckRunState:
        self._maybe_fail("get_check_run")
        if self.read_back is not None:
            return self.read_back
        last = self.created[-1]
        return CheckRunState(
            check_id=check_id,
            name=CHECK_NAME,
            head_sha=last["head_sha"],
            conclusion=last["conclusion"],
            external_id=last["external_id"],
            app_id=APP_ID,
        )

    def set_conclusion(self, check_id: int, conclusion: str, summary: str) -> None:
        self._maybe_fail("set_conclusion")
        self.conclusions.append((check_id, conclusion))


def run_publish(api: FakeApi, **overrides: str) -> CheckOutcome:
    return pub.publish(PublisherEnv.from_environ(make_env(**overrides)), lambda env: api)


def refuse_api(_env: PublisherEnv) -> FakeApi:
    raise AssertionError("the API must not be built for a state that publishes nothing")


class TestFlagOff:
    @pytest.mark.parametrize("value", ["", "false", "TRUE", "1", "yes", " off "])
    def test_anything_but_exact_true_is_skip_and_publishes_nothing(self, value: str) -> None:
        env = PublisherEnv.from_environ(make_env(ADR101_PUBLISHER_ENABLED=value))

        outcome = pub.publish(env, refuse_api)

        assert outcome.state is EvidenceState.SKIP
        assert outcome.reason == "publisher.disabled"

    def test_unset_variable_is_skip(self) -> None:
        outcome = pub.publish(PublisherEnv.from_environ({}), refuse_api)

        assert outcome.state is EvidenceState.SKIP

    def test_unrecognized_value_is_named_in_the_detail(self) -> None:
        env = PublisherEnv.from_environ(make_env(ADR101_PUBLISHER_ENABLED="yes"))

        outcome = pub.publish(env, refuse_api)

        assert "unrecognized" in outcome.detail

    def test_main_exits_zero_and_prints_a_typed_skip(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = pub.main(["publish"], make_env(ADR101_PUBLISHER_ENABLED="false"))

        out = capsys.readouterr().out
        assert rc == 0
        assert "[SKIP]" in out
        assert "publisher.disabled" in out
        assert "[PASS]" not in out

    def test_a_skip_never_reads_as_verified(self, capsys: pytest.CaptureFixture[str]) -> None:
        pub.main(["publish"], make_env(ADR101_PUBLISHER_ENABLED="false"))

        assert "verified" not in capsys.readouterr().out.lower()

    def test_other_event_is_skip_and_publishes_nothing(self) -> None:
        env = PublisherEnv.from_environ(make_env(ADR101_TRIGGER_EVENT="push"))

        outcome = pub.publish(env, refuse_api)

        assert outcome.state is EvidenceState.SKIP
        assert outcome.reason == "event.not_served"


class TestSecretsAbsent:
    @pytest.mark.parametrize(
        "override",
        [
            {"ADR101_HAS_KEY": "false"},
            {"ADR101_HAS_KEY": ""},
            {"ADR101_PUBLISHER_APP_ID": ""},
            {"ADR101_PUBLISHER_APP_ID": "not-a-number"},
        ],
    )
    def test_flag_on_without_the_key_or_id_is_blocked(self, override: dict[str, str]) -> None:
        env = PublisherEnv.from_environ(make_env(**override))

        outcome = pub.publish(env, refuse_api)

        assert outcome.state is EvidenceState.BLOCKED
        assert outcome.reason == "auth.unavailable"

    def test_main_exits_four_not_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = pub.main(["publish"], make_env(ADR101_HAS_KEY="false"))

        assert rc == 4
        assert "[BLOCKED]" in capsys.readouterr().out

    @pytest.mark.parametrize(
        "override",
        [
            {"ADR101_APP_TOKEN_OUTCOME": "failure"},
            {"ADR101_APP_TOKEN_OUTCOME": ""},
            {"ADR101_APP_TOKEN": ""},
        ],
    )
    def test_token_not_minted_is_blocked(self, override: dict[str, str]) -> None:
        env = PublisherEnv.from_environ(make_env(**override))

        outcome = pub.publish(env, refuse_api)

        assert outcome.state is EvidenceState.BLOCKED
        assert exit_code(outcome) == 4


class TestValidPublish:
    def test_mocked_valid_token_publishes_one_success_run_and_passes(self) -> None:
        api = FakeApi()

        outcome = run_publish(api)

        assert outcome.state is EvidenceState.PASS
        assert [c["conclusion"] for c in api.created] == ["success"]
        assert api.created[0]["head_sha"] == HEAD
        assert api.created[0]["external_id"] == revision_digest(HEAD, BASE)
        assert api.created[0]["title"] == CHECK_NAME
        assert api.conclusions == []

    def test_pass_binds_the_result_to_head_and_base(self) -> None:
        outcome = run_publish(FakeApi())

        assert outcome.revision == f"{HEAD}+{BASE}"

    def test_the_label_is_bounded_and_never_says_verified(self) -> None:
        api = FakeApi()

        outcome = run_publish(api)

        assert api.created[0]["summary"] == PUBLISHED_LABEL
        assert "requirement 2b" in PUBLISHED_LABEL
        assert "verified" not in PUBLISHED_LABEL.lower()
        assert "verified" not in outcome.detail.lower()

    def test_main_exits_zero_on_pass_and_prints_a_pass_line(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        api = FakeApi()

        rc = pub.main(["publish"], make_env(), lambda env: api)

        assert rc == 0
        assert "[PASS]" in capsys.readouterr().out
        assert len(api.created) == 1

    def test_main_exits_one_when_the_evidence_is_tampered(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        api = FakeApi(run=RunState(head_sha="c" * 40, status="completed"))

        rc = pub.main(["publish"], make_env(), lambda env: api)

        assert rc == 1
        assert "[FAIL]" in capsys.readouterr().out

    def test_head_and_base_are_re_read_immediately_before_publishing(self) -> None:
        api = FakeApi()

        run_publish(api)

        assert api.calls.count("get_pull") == 2
        assert api.calls.index("create_check_run") > api.calls.index("get_run")


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
        api = FakeApi(read_back=replace(good, **{field_name: value}))

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

    def test_no_pull_request_is_unknown_and_publishes_failure(self) -> None:
        api = FakeApi()

        outcome = run_publish(api, ADR101_PULL_NUMBER="")

        assert outcome.state is EvidenceState.UNKNOWN
        assert outcome.reason == "pr.unresolved"
        assert [c["conclusion"] for c in api.created] == ["failure"]


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


class TestGateAndPreflight:
    def test_gate_writes_enabled_true_and_prints_nothing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        output = tmp_path / "out"
        rc = pub.main(["gate"], make_env(GITHUB_OUTPUT=str(output)))

        assert rc == 0
        assert output.read_text(encoding="utf-8") == "enabled=true\n"
        assert capsys.readouterr().out == ""

    def test_gate_writes_enabled_false_and_prints_skip_when_off(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        output = tmp_path / "out"
        rc = pub.main(["gate"], make_env(ADR101_PUBLISHER_ENABLED="", GITHUB_OUTPUT=str(output)))

        assert rc == 0
        assert output.read_text(encoding="utf-8") == "enabled=false\n"
        assert "[SKIP]" in capsys.readouterr().out

    def test_gate_is_false_for_an_unserved_event(self, tmp_path: Path) -> None:
        output = tmp_path / "out"

        pub.main(["gate"], make_env(ADR101_TRIGGER_EVENT="merge_group", GITHUB_OUTPUT=str(output)))

        assert output.read_text(encoding="utf-8") == "enabled=false\n"

    @pytest.mark.parametrize(
        "override, expected",
        [
            ({}, "mint=true\n"),
            ({"ADR101_HAS_KEY": "false"}, "mint=false\n"),
            ({"ADR101_PUBLISHER_APP_ID": ""}, "mint=false\n"),
            ({"ADR101_PUBLISHER_ENABLED": "false"}, "mint=false\n"),
        ],
    )
    def test_preflight_mints_only_with_flag_id_and_key(
        self, tmp_path: Path, override: dict[str, str], expected: str
    ) -> None:
        output = tmp_path / "out"

        rc = pub.main(["preflight"], make_env(GITHUB_OUTPUT=str(output), **override))

        assert rc == 0
        assert output.read_text(encoding="utf-8") == expected

    def test_an_output_is_not_written_without_github_output(self) -> None:
        assert pub.main(["gate"], make_env()) == 0

    def test_a_multiline_output_value_is_refused(self, tmp_path: Path) -> None:
        from scripts.ci.adr101_publisher_inputs import write_output

        with pytest.raises(ValueError):
            write_output("k", "a\nb", {"GITHUB_OUTPUT": str(tmp_path / "o")})

    def test_the_step_summary_receives_the_typed_line(self, tmp_path: Path) -> None:
        summary = tmp_path / "summary.md"

        pub.main(["publish"], make_env(ADR101_HAS_KEY="false", GITHUB_STEP_SUMMARY=str(summary)))

        assert "[BLOCKED]" in summary.read_text(encoding="utf-8")


class TestDispatch:
    def test_execute_with_the_flag_off_exits_zero_with_a_skip(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = pub.main(["execute"], make_env(ADR101_PUBLISHER_ENABLED="false"))

        assert rc == 0
        assert "[SKIP]" in capsys.readouterr().out

    def test_the_default_api_factory_builds_the_real_client_without_a_request(self) -> None:
        from scripts.ci.adr101_publisher_github import GitHubApi

        api = pub._real_api(PublisherEnv.from_environ(make_env()))

        assert isinstance(api, GitHubApi)


class TestExitCodes:
    @pytest.mark.parametrize(
        "outcome, expected",
        [
            (CheckOutcome.passed("v", revision="r", scope="s"), 0),
            (CheckOutcome.skipped("v", reason="publisher.disabled"), 0),
            (CheckOutcome.failed("v", reason="x.y"), 1),
            (CheckOutcome.unknown("v", reason="x.y"), 1),
            (CheckOutcome.blocked("v", reason="lookup.failed"), 3),
            (CheckOutcome.blocked("v", reason="auth.unavailable"), 4),
        ],
    )
    def test_each_state_maps_to_its_documented_code(
        self, outcome: CheckOutcome, expected: int
    ) -> None:
        assert exit_code(outcome) == expected


class TestRealProcess:
    """Drive the script as the workflow step does, with a scrubbed environment."""

    def _run(self, command: str, **overrides: str) -> subprocess.CompletedProcess[str]:
        env = {"PATH": "/usr/bin:/bin", **make_env(**overrides)}
        return subprocess.run(
            [sys.executable, str(SCRIPT), command],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            check=False,
            timeout=60,
        )

    def test_flag_off_exits_zero_with_a_skip_line(self) -> None:
        result = self._run("publish", ADR101_PUBLISHER_ENABLED="false")

        assert result.returncode == 0
        assert "[SKIP]" in result.stdout

    def test_flag_on_without_secrets_exits_four(self) -> None:
        result = self._run("publish", ADR101_HAS_KEY="false")

        assert result.returncode == 4
        assert "[BLOCKED]" in result.stdout

    def test_an_unknown_command_exits_two(self) -> None:
        result = self._run("nonsense")

        assert result.returncode == 2

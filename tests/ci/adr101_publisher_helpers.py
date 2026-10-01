"""Shared fakes for the ADR-101 publisher tests."""

from __future__ import annotations

from dataclasses import dataclass, field

from scripts.ci import adr101_publisher as pub
from scripts.ci.adr101_publisher_github import ApiError, CheckRunState, PullState, RunState
from scripts.ci.adr101_publisher_inputs import CHECK_NAME, PublisherEnv
from scripts.validation.evidence import CheckOutcome

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

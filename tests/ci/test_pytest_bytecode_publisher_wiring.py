"""Wiring tests for the isolated bytecode publisher job in pytest.yml (WS6B F2, F3).

Only `publish-bytecode-cache` may save the bytecode cache. These tests read the
real workflow and pin: the job's dependency on the aggregate `test-result` job,
its per-event condition (a truth table over every trigger the workflow declares),
a runner separate from the test legs, the artifact identity and cache path it
shares with the restore step, and the step order that keeps candidate bytes
away from any interpreter until they are verified and saved.
"""

from __future__ import annotations

import fnmatch
import itertools
from typing import Any

import pytest
import yaml

from tests.ci.pytest_split_workflow_helpers import WORKFLOW, steps_using, workflow_jobs

PUBLISHER = "publish-bytecode-cache"
AGGREGATE = "test-result"
CACHE_SAVE_SHA = "55cc8345863c7cc4c66a329aec7e433d2d1c52a9"
DOWNLOAD_SHA = "9000827ccba6bdab643e8b6fd33ac0654aef8333"
CANDIDATE_PREFIX = "pytest-bytecode-candidate-"
STEP_ORDER = [
    "Harden Runner",
    None,  # actions/checkout has no name
    "Setup code environment",
    "Fingerprint pytest bytecode cache configuration",
    "Download pytest bytecode candidate",
    "Verify pytest bytecode candidate",
    "Save pytest bytecode cache",
]
ALLOWED_TERMS = {
    "!cancelled()",
    "needs.test-result.result == 'success'",
    "github.event_name == 'push'",
    "github.ref == 'refs/heads/main'",
}
RESULTS = ("success", "failure", "cancelled", "skipped")
MAIN_REF = "refs/heads/main"


def _job() -> dict[str, Any]:
    return workflow_jobs()[PUBLISHER]


def _steps() -> list[dict[str, Any]]:
    return _job()["steps"]


def _step(name: str) -> dict[str, Any]:
    return next(step for step in _steps() if step.get("name") == name)


def _needs(job: dict[str, Any]) -> list[str]:
    needs = job.get("needs", [])
    return [needs] if isinstance(needs, str) else list(needs)


def _triggers() -> dict[str, Any]:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    # PyYAML reads the bare key `on` as the boolean True.
    return document.get("on", document.get(True))


def _terms(condition: str) -> list[str]:
    return [term.strip() for term in " ".join(str(condition).split()).split(" && ")]


def _publishes(condition: str, *, event: str, ref: str, aggregate: str) -> bool:
    """Evaluate the publisher condition. Only conjunctions of the allowed terms are understood."""
    context = {
        "!cancelled()": True,  # a cancelled run is not a context this table evaluates
        "needs.test-result.result == 'success'": aggregate == "success",
        "github.event_name == 'push'": event == "push",
        "github.ref == 'refs/heads/main'": ref == MAIN_REF,
    }
    terms = _terms(condition)
    unknown = [term for term in terms if term not in context]
    assert not unknown, f"unsupported term in the publisher condition: {unknown}"
    return all(context[term] for term in terms)


def _all_contexts() -> list[tuple[str, str, str]]:
    events = list(_triggers())
    refs = [
        MAIN_REF,
        "refs/pull/1/merge",
        "refs/heads/feature",
        "refs/heads/gh-readonly-queue/main/x",
    ]
    return list(itertools.product(events, refs, RESULTS))


class TestAggregateDependency:
    def test_the_publisher_needs_the_aggregate_required_job(self) -> None:
        assert _needs(_job()) == [AGGREGATE]

    def test_the_aggregate_job_is_the_required_context(self) -> None:
        assert workflow_jobs()[AGGREGATE]["name"] == "Run Python Tests"

    def test_the_aggregate_waits_for_every_test_leg_coverage_and_guard(self) -> None:
        needed = set(_needs(workflow_jobs()[AGGREGATE]))
        assert {"test", "coverage", "zero-collection-guard", "line-endings-guard"} <= needed
        assert {"context-output-guard", "count-ratchet-guard", "mutation-harness-guard"} <= needed

    def test_the_aggregate_requires_success_of_the_legs_and_coverage(self) -> None:
        steps = workflow_jobs()[AGGREGATE]["steps"]
        command = " ".join(
            " ".join(str(step.get("run", "")).split()) for step in steps if "run" in step
        )
        assert "--check TEST_RESULT success" in command
        assert "--check COVERAGE_RESULT success" in command

    def test_the_publisher_is_not_part_of_the_aggregate_verdict(self) -> None:
        """A slow or failed publish must never change the required context."""
        assert PUBLISHER not in _needs(workflow_jobs()[AGGREGATE])
        assert PUBLISHER not in _needs(workflow_jobs()["main-failure-alert"])

    def test_the_test_job_keeps_adr101_no_needs_and_no_job_condition(self) -> None:
        test_job = workflow_jobs()["test"]
        assert "needs" not in test_job
        assert "if" not in test_job

    def test_the_condition_is_a_plain_conjunction_with_no_status_override(self) -> None:
        condition = " ".join(str(_job()["if"]).split())
        for banned in ("||", "always()", "failure()", "success()"):
            assert banned not in condition
        assert condition.count("cancelled()") == 1
        assert set(_terms(condition)) == ALLOWED_TERMS


class TestPerEventCondition:
    def test_the_workflow_declares_the_events_the_table_covers(self) -> None:
        events = set(_triggers())
        assert events == {"push", "pull_request", "merge_group", "workflow_dispatch"}

    def test_no_privileged_or_cross_workflow_trigger_exists(self) -> None:
        events = set(_triggers())
        assert not events & {"pull_request_target", "workflow_run", "issue_comment", "schedule"}

    def test_only_a_main_push_after_aggregate_success_publishes(self) -> None:
        condition = str(_job()["if"])
        allowed = [
            (event, ref, result)
            for event, ref, result in _all_contexts()
            if _publishes(condition, event=event, ref=ref, aggregate=result)
        ]
        assert allowed == [("push", MAIN_REF, "success")]

    @pytest.mark.parametrize("event", ["pull_request", "merge_group", "workflow_dispatch"])
    @pytest.mark.parametrize("result", RESULTS)
    def test_other_events_never_publish_whatever_the_ref_or_result(
        self, event: str, result: str
    ) -> None:
        for ref in (MAIN_REF, "refs/pull/1/merge", "refs/heads/feature"):
            assert not _publishes(str(_job()["if"]), event=event, ref=ref, aggregate=result)

    @pytest.mark.parametrize("result", ["failure", "cancelled", "skipped"])
    def test_a_main_push_without_aggregate_success_does_not_publish(self, result: str) -> None:
        assert not _publishes(str(_job()["if"]), event="push", ref=MAIN_REF, aggregate=result)

    def test_a_push_to_another_branch_does_not_publish(self) -> None:
        condition = str(_job()["if"])
        assert not _publishes(
            condition, event="push", ref="refs/heads/feature", aggregate="success"
        )

    @pytest.mark.parametrize(
        "mutated",
        [
            "github.event_name == 'push' && github.ref == 'refs/heads/main'",
            "needs.test-result.result == 'success' && github.ref == 'refs/heads/main'",
            "needs.test-result.result == 'success' && github.event_name == 'push'",
        ],
    )
    def test_the_truth_table_catches_a_dropped_term(self, mutated: str) -> None:
        """Negative control: removing any one term lets a context publish that must not."""
        leaked = [context for context in _all_contexts() if _publishes_loose(mutated, *context)]
        assert leaked != [("push", MAIN_REF, "success")]


def _publishes_loose(condition: str, event: str, ref: str, aggregate: str) -> bool:
    """Like _publishes, but each term is evaluated only when the condition names it."""
    terms = _terms(condition)
    checks = {
        "!cancelled()": True,
        "needs.test-result.result == 'success'": aggregate == "success",
        "github.event_name == 'push'": event == "push",
        "github.ref == 'refs/heads/main'": ref == MAIN_REF,
    }
    return all(checks[term] for term in terms)


class TestSeparateIsolatedRunner:
    def test_the_publisher_has_its_own_runner_equal_to_the_test_legs(self) -> None:
        """Same runner image keeps the workspace and temp paths, and so the cache version, equal."""
        assert _job()["runs-on"] == workflow_jobs()["test"]["runs-on"]
        assert str(_job()["runs-on"]).startswith("ubuntu-")

    def test_the_publisher_has_read_only_contents_and_no_other_permission(self) -> None:
        assert _job()["permissions"] == {"contents": "read"}

    def test_no_test_leg_is_the_publisher(self) -> None:
        assert PUBLISHER != "test"
        assert "strategy" not in _job()

    def test_no_step_restores_or_sets_a_bytecode_prefix(self) -> None:
        text = yaml.safe_dump(_job())
        assert "PYTHONPYCACHEPREFIX" not in text
        assert "actions/cache/restore" not in text
        assert "env" not in _job()

    def test_no_step_ignores_failure_or_carries_its_own_condition(self) -> None:
        for step in _steps():
            assert "continue-on-error" not in step
            assert "if" not in step

    def test_the_checkout_does_not_persist_credentials(self) -> None:
        checkout = next(step for step in _steps() if "actions/checkout" in str(step.get("uses")))
        assert checkout["with"]["persist-credentials"] is False

    def test_the_step_order_keeps_candidate_bytes_away_from_every_other_step(self) -> None:
        assert [step.get("name") for step in _steps()] == STEP_ORDER

    def test_download_verify_and_save_are_adjacent_and_save_is_last(self) -> None:
        names = [step.get("name") for step in _steps()]
        assert names[-3:] == [
            "Download pytest bytecode candidate",
            "Verify pytest bytecode candidate",
            "Save pytest bytecode cache",
        ]


class TestArtifactAndCacheIdentity:
    @staticmethod
    def _upload() -> dict[str, Any]:
        (step,) = [
            s
            for s in steps_using("test", "actions/upload-artifact")
            if str(s["with"]["name"]).startswith(CANDIDATE_PREFIX)
        ]
        return step

    @staticmethod
    def _restore() -> dict[str, Any]:
        (step,) = [
            s
            for s in steps_using("test", "actions/cache/restore")
            if s["with"]["key"].startswith("pytest-bytecode-")
        ]
        return step

    def test_upload_and_download_name_the_same_artifact(self) -> None:
        download = _step("Download pytest bytecode candidate")
        assert download["with"]["name"] == self._upload()["with"]["name"]
        assert "pattern" not in download["with"]
        assert "run-id" not in download["with"]
        assert "github-token" not in download["with"]

    def test_the_download_uses_the_action_pin_the_workflow_already_has(self) -> None:
        assert _step("Download pytest bytecode candidate")["uses"] == (
            f"actions/download-artifact@{DOWNLOAD_SHA}"
        )
        assert _step("Save pytest bytecode cache")["uses"] == f"actions/cache/save@{CACHE_SAVE_SHA}"

    def test_the_artifact_name_recomputes_from_the_publishers_own_fingerprint(self) -> None:
        name = _step("Download pytest bytecode candidate")["with"]["name"]
        assert "steps.pytest-bytecode-config.outputs.fingerprint" in name
        assert "steps.pytest-bytecode-config.outputs.python-runtime" in name
        fingerprint = _step("Fingerprint pytest bytecode cache configuration")
        leg_fingerprint = next(
            s
            for s in workflow_jobs()["test"]["steps"]
            if s.get("name") == "Fingerprint pytest bytecode cache configuration"
        )
        assert fingerprint["id"] == leg_fingerprint["id"] == "pytest-bytecode-config"
        assert fingerprint["run"] == leg_fingerprint["run"]

    def test_download_verify_save_and_restore_share_one_path(self) -> None:
        restore_path = self._restore()["with"]["path"]
        assert _step("Download pytest bytecode candidate")["with"]["path"] == restore_path
        assert _step("Save pytest bytecode cache")["with"]["path"] == restore_path
        assert self._upload()["with"]["path"] == restore_path
        command = " ".join(str(_step("Verify pytest bytecode candidate")["run"]).split())
        assert f'--cache-root "{restore_path}"' in command
        assert '--workspace "${{ github.workspace }}"' in command

    def test_the_saved_key_equals_the_restore_key_exactly(self) -> None:
        assert _step("Save pytest bytecode cache")["with"]["key"] == self._restore()["with"]["key"]

    def test_the_key_names_the_runtime_arch_and_run_attempt(self) -> None:
        key = _step("Save pytest bytecode cache")["with"]["key"]
        for token in (
            "runner.os",
            "runner.arch",
            "python-runtime",
            "fingerprint",
            "github.run_id",
            "github.run_attempt",
        ):
            assert token in key

    def test_the_verify_step_is_the_read_only_mode_of_the_prune_script(self) -> None:
        command = " ".join(str(_step("Verify pytest bytecode candidate")["run"]).split())
        assert command.startswith(
            "uv run --frozen python scripts/ci/prune_bytecode_cache.py --verify-only "
        )

    def test_the_candidate_name_matches_no_download_pattern_in_the_workflow(self) -> None:
        candidate = str(self._upload()["with"]["name"])
        for job in workflow_jobs():
            for step in steps_using(job, "actions/download-artifact"):
                pattern = step["with"].get("pattern")
                if pattern:
                    assert not fnmatch.fnmatchcase(candidate, pattern)

    def test_no_other_job_saves_bytecode(self) -> None:
        """No job other than the publisher may save, whatever its condition."""
        for job in workflow_jobs():
            if job == PUBLISHER:
                continue
            for step in steps_using(job, "actions/cache/save"):
                assert not str(step["with"]["key"]).startswith("pytest-bytecode-")

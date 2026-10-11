"""Contract test: Validate Spec Coverage holds no model, secret, or environment.

Issue #6182. The check's verdict comes from scripts/ci/spec_coverage_verdict.py.
The model review lives in ai-spec-review.yml and only comments.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

_WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"
_VALIDATION = _WORKFLOWS / "ai-spec-validation.yml"
_REVIEW = _WORKFLOWS / "ai-spec-review.yml"
_AI_REVIEW_ACTION = "./.github/actions/ai-review"
_DISPOSITIONS = (
    Path(__file__).resolve().parents[2] / ".project-toolkit" / "pr-checks" / "dispositions.json"
)


def _load(path: Path) -> dict[Any, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def validate_job() -> dict[str, Any]:
    return _load(_VALIDATION)["jobs"]["validate-spec"]


@pytest.fixture(scope="module")
def review_job() -> dict[str, Any]:
    return _load(_REVIEW)["jobs"]["review-spec"]


def _verdict_step(job: dict[str, Any]) -> dict[str, Any]:
    return next(s for s in job["steps"] if "spec_coverage_verdict" in str(s.get("run")))


class TestValidateSpecIsDeterministic:
    def test_job_keeps_the_check_name(self, validate_job: dict[str, Any]) -> None:
        assert validate_job["name"] == "Validate Spec Coverage"

    def test_job_declares_no_environment(self, validate_job: dict[str, Any]) -> None:
        assert "environment" not in validate_job

    def test_workflow_references_no_secret(self) -> None:
        text = _VALIDATION.read_text(encoding="utf-8")
        assert "secrets." not in text

    def test_workflow_uses_no_ai_review_action(self) -> None:
        text = _VALIDATION.read_text(encoding="utf-8")
        assert _AI_REVIEW_ACTION not in text

    def test_no_step_uses_continue_on_error(self, validate_job: dict[str, Any]) -> None:
        for step in validate_job["steps"]:
            assert not step.get("continue-on-error"), step.get("name")

    def test_verdict_step_runs_the_script_with_bare_python(
        self, validate_job: dict[str, Any]
    ) -> None:
        step = _verdict_step(validate_job)

        assert step["run"].strip() == "python3 scripts/ci/spec_coverage_verdict.py"
        assert "continue-on-error" not in step

    def test_verdict_step_passes_the_body_through_env_only(
        self, validate_job: dict[str, Any]
    ) -> None:
        step = _verdict_step(validate_job)

        assert step["env"]["PR_BODY"] == "${{ github.event.pull_request.body }}"
        assert step["env"]["HAS_SPECS"] == "${{ steps.spec-ref.outputs.has_specs }}"
        assert "${{" not in step["run"]

    def test_verdict_step_is_gated_only_on_scope(self, validate_job: dict[str, Any]) -> None:
        step = _verdict_step(validate_job)

        assert step["if"] == "steps.should-run.outputs.skip != 'true'"


class TestReviewSpecIsAdvisory:
    def test_job_runs_behind_the_claude_environment(self, review_job: dict[str, Any]) -> None:
        assert review_job["environment"] == "agent-claude"

    def test_both_model_steps_swallow_failures(self, review_job: dict[str, Any]) -> None:
        model_steps = [
            s for s in review_job["steps"] if s.get("uses") == _AI_REVIEW_ACTION
        ]

        assert {s["id"] for s in model_steps} == {"trace", "completeness"}
        assert all(s["continue-on-error"] is True for s in model_steps)

    def test_no_step_fails_the_job_on_a_verdict(self, review_job: dict[str, Any]) -> None:
        text = _REVIEW.read_text(encoding="utf-8")
        assert "check_spec_failures" not in text
        assert "Check for Failures" not in text

    def test_run_is_cancelled_by_a_newer_run_for_the_same_pr(self) -> None:
        concurrency = _load(_REVIEW)["concurrency"]

        assert concurrency["cancel-in-progress"] is True
        assert "pull_request.number" in concurrency["group"]

    def test_review_types_are_the_validation_types_minus_edited(self) -> None:
        """`edited` is dropped from the review: each body edit would queue another
        agent-claude approval prompt. Reviewers can use workflow_dispatch instead."""
        review = _load(_REVIEW)[True]["pull_request"]
        validation = _load(_VALIDATION)[True]["pull_request"]

        assert "edited" in validation["types"]
        assert "edited" not in review["types"]
        assert review["types"] == [t for t in validation["types"] if t != "edited"]
        assert review["branches"] == validation["branches"]

    def test_workflow_triggers_include_dispatch_and_no_merge_group(self) -> None:
        review = _load(_REVIEW)[True]

        assert "pr_number" in review["workflow_dispatch"]["inputs"]
        assert "merge_group" not in review


def test_dispositions_waiver_for_the_check_is_gone() -> None:
    dispositions = json.loads(_DISPOSITIONS.read_text(encoding="utf-8"))

    assert "Validate Spec Coverage" not in dispositions


def test_validation_workflow_requests_read_only_pull_request_scope() -> None:
    permissions = _load(_VALIDATION)["permissions"]

    assert permissions == {"contents": "read", "pull-requests": "read"}


def test_debounce_job_declares_no_environment() -> None:
    assert "environment" not in _load(_VALIDATION)["jobs"]["debounce"]

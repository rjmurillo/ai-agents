"""Contract test: Validate Spec Coverage holds no model, secret, or environment.

Issue #6182. The check's verdict comes from scripts/ci/spec_coverage_verdict.py.
The model review lives in ai-spec-review.yml and only comments.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

_WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"
_VALIDATION = _WORKFLOWS / "ai-spec-validation.yml"
_REVIEW = _WORKFLOWS / "ai-spec-review.yml"
_AI_REVIEW_ACTION = "./.github/actions/ai-review"


def _load(path: Path) -> dict[str, Any]:
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

    def test_workflow_triggers_match_the_validation_workflow(self) -> None:
        review = _load(_REVIEW)[True]
        validation = _load(_VALIDATION)[True]

        assert review["pull_request"] == validation["pull_request"]
        assert "pr_number" in review["workflow_dispatch"]["inputs"]
        assert "merge_group" not in review

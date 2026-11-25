"""Contract test: Validate Spec Coverage holds no model, secret, or environment.

Issue #6182. The check's verdict comes from scripts/ci/spec_coverage_verdict.py.
The model review workflow (ai-spec-review.yml) was deleted.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

_WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"
_VALIDATION = _WORKFLOWS / "ai-spec-validation.yml"
_AI_REVIEW_ACTION = "./.github/actions/ai-review"
_DISPOSITIONS = (
    Path(__file__).resolve().parents[2] / ".project-toolkit" / "pr-checks" / "dispositions.json"
)


def _load(path: Path) -> dict[Any, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def validate_job() -> dict[str, Any]:
    return _load(_VALIDATION)["jobs"]["validate-spec"]


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

        assert step["run"].strip() == "python3 trusted-base/scripts/ci/spec_coverage_verdict.py"
        assert "continue-on-error" not in step

    def test_verdict_step_passes_the_body_through_env_only(
        self, validate_job: dict[str, Any]
    ) -> None:
        step = _verdict_step(validate_job)

        assert step["env"]["PR_BODY"] == "${{ github.event.pull_request.body }}"
        assert step["env"]["HAS_SPECS"] == "${{ steps.spec-ref.outputs.has_specs }}"
        assert "${{" not in step["run"]

    def test_verdict_step_reads_the_body_the_extract_step_saved(
        self, validate_job: dict[str, Any]
    ) -> None:
        """One body for both steps: a second fetch on dispatch could differ."""
        step = _verdict_step(validate_job)
        extract = next(s for s in validate_job["steps"] if s.get("id") == "spec-ref")

        assert step["env"]["PR_BODY_FILE"] == "${{ steps.spec-ref.outputs.pr_body_file }}"
        assert "spec_extract_refs" in extract["run"]

    def test_verdict_step_is_gated_only_on_scope(self, validate_job: dict[str, Any]) -> None:
        step = _verdict_step(validate_job)

        assert step["if"] == "steps.should-run.outputs.skip != 'true'"


def test_dispositions_waiver_for_the_check_is_gone() -> None:
    dispositions = json.loads(_DISPOSITIONS.read_text(encoding="utf-8"))

    assert "Validate Spec Coverage" not in dispositions


def test_validation_workflow_requests_read_only_pull_request_scope() -> None:
    permissions = _load(_VALIDATION)["permissions"]

    assert permissions == {"contents": "read", "pull-requests": "read"}


def test_debounce_job_declares_no_environment() -> None:
    assert "environment" not in _load(_VALIDATION)["jobs"]["debounce"]

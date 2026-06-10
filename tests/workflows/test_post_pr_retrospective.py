"""Tests for the Post-PR Retrospective workflow failure isolation (Issue #2015).

The retrospective workflow is async, best-effort, and never blocks merge. Its
agent step depends on the CLAUDE_CODE_OAUTH_TOKEN secret and the Anthropic API.
When the token is expired or the API is unavailable, the action returns a hard
error (observed root cause for #2015: "401 Invalid authentication credentials").

Without continue-on-error on the agent step, that one failure paints the
"Run retrospective agent" check red on every PR. These tests pin the contract
that the agent step is failure-isolated so a credential or API outage degrades
to a step annotation, not a red check.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW_PATH = _REPO_ROOT / ".github" / "workflows" / "post-pr-retrospective.yml"

_AGENT_STEP_NAME = "Run retrospective via Claude Code"
_ACTION_PATH = "anthropics/claude-code-action"
# Assert the pin's SHAPE (exact action path + 40-hex SHA), not an exact SHA.
# Renovate owns the SHA and bumps it in the workflow; duplicating the literal
# here re-broke main on every bump (Issue #2348, recurrence 2026-06-09 after
# the v1.0.140/141/142 bumps in #2486/#2506/#2516).
_SHA_PINNED_ACTION_RE = re.compile(rf"^{re.escape(_ACTION_PATH)}@[0-9a-f]{{40}}$")
# Synthetic, valid-shape ref for in-memory negative-control workflows.
_FAKE_ACTION_REF = f"{_ACTION_PATH}@{'0' * 40}"
_OAUTH_TOKEN_EXPR = "${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}"


def _load_workflow() -> dict[str, Any]:
    """Parse the workflow YAML into a dict."""
    with _WORKFLOW_PATH.open(encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(
            f"Expected {_WORKFLOW_PATH} to parse as a mapping, "
            f"got {type(loaded).__name__}"
        )
    return loaded


def _find_step(workflow: dict[str, Any], step_name: str) -> dict[str, Any] | None:
    """Return the first step matching step_name across all jobs, or None."""
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict):
        return None
    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        steps = job.get("steps")
        if not isinstance(steps, list):
            continue
        for step in steps:
            if isinstance(step, dict) and step.get("name") == step_name:
                return step
    return None


class TestWorkflowFile:
    def test_workflow_file_exists(self) -> None:
        # Arrange / Act / Assert
        assert _WORKFLOW_PATH.is_file()

    def test_workflow_parses_as_yaml(self) -> None:
        # Arrange / Act
        workflow = _load_workflow()
        # Assert
        assert isinstance(workflow, dict)
        assert "jobs" in workflow


class TestAgentStepFailureIsolation:
    def test_agent_step_is_present(self) -> None:
        # Arrange
        workflow = _load_workflow()
        # Act
        step = _find_step(workflow, _AGENT_STEP_NAME)
        # Assert
        assert step is not None, f"missing agent step named {_AGENT_STEP_NAME!r}"

    def test_agent_step_is_failure_isolated(self) -> None:
        # Arrange
        workflow = _load_workflow()
        step = _find_step(workflow, _AGENT_STEP_NAME)
        assert step is not None
        # Act
        continue_on_error = step.get("continue-on-error")
        # Assert: best-effort async step must not fail the check (Issue #2015)
        assert continue_on_error is True

    def test_agent_step_keeps_sha_pinned_action(self) -> None:
        # Arrange
        workflow = _load_workflow()
        step = _find_step(workflow, _AGENT_STEP_NAME)
        assert step is not None
        # Act
        uses = step.get("uses", "")
        # Assert: the action path is exact (a repo/owner/path change is caught)
        # and the ref is a full 40-hex commit SHA (a floating tag is caught).
        # The specific SHA is owned by the workflow + Renovate, not this test.
        assert _SHA_PINNED_ACTION_RE.fullmatch(uses), (
            f"agent step 'uses' is {uses!r}; expected "
            f"'{_ACTION_PATH}@<40-hex-sha>'"
        )

    def test_agent_step_still_wires_oauth_token(self) -> None:
        # Arrange
        workflow = _load_workflow()
        step = _find_step(workflow, _AGENT_STEP_NAME)
        assert step is not None
        # Act
        step_with = step.get("with")
        # Assert: the token wiring is unchanged by the isolation fix
        assert isinstance(step_with, dict)
        token = step_with.get("claude_code_oauth_token", "")
        assert token == _OAUTH_TOKEN_EXPR


class TestFailureIsolationDetectionNegative:
    """Negative coverage: the assertion catches a non-isolated step.

    Builds an in-memory workflow whose agent step lacks continue-on-error and
    confirms the failure-isolation predicate the real test relies on would flag
    it. This guards against the predicate silently passing on a regression.
    """

    def test_missing_continue_on_error_is_detected(self) -> None:
        # Arrange: a workflow shaped like the real one but without isolation
        workflow: dict[str, Any] = {
            "jobs": {
                "retrospective": {
                    "steps": [
                        {"name": _AGENT_STEP_NAME, "uses": _FAKE_ACTION_REF},
                    ]
                }
            }
        }
        step = _find_step(workflow, _AGENT_STEP_NAME)
        assert step is not None
        # Act
        continue_on_error = step.get("continue-on-error")
        # Assert: predicate correctly reports the step is NOT isolated
        assert continue_on_error is not True

    def test_explicit_false_continue_on_error_is_detected(self) -> None:
        # Arrange: continue-on-error present but set to False
        workflow: dict[str, Any] = {
            "jobs": {
                "retrospective": {
                    "steps": [
                        {
                            "name": _AGENT_STEP_NAME,
                            "uses": _FAKE_ACTION_REF,
                            "continue-on-error": False,
                        },
                    ]
                }
            }
        }
        step = _find_step(workflow, _AGENT_STEP_NAME)
        assert step is not None
        # Act
        continue_on_error = step.get("continue-on-error")
        # Assert
        assert continue_on_error is not True


class TestShaPinPredicateNegative:
    """Negative coverage: the pin-shape predicate rejects bad refs.

    The positive test asserts shape, not an exact SHA. These controls prove
    the relaxation did not open the door to floating tags, short SHAs, or a
    hijacked action path.
    """

    def test_floating_tag_is_rejected(self) -> None:
        # Arrange / Act / Assert
        assert _SHA_PINNED_ACTION_RE.fullmatch(f"{_ACTION_PATH}@v1") is None

    def test_short_sha_is_rejected(self) -> None:
        # Arrange / Act / Assert
        assert _SHA_PINNED_ACTION_RE.fullmatch(f"{_ACTION_PATH}@{'a' * 12}") is None

    def test_wrong_owner_is_rejected(self) -> None:
        # Arrange
        hijacked = f"evil/claude-code-action@{'0' * 40}"
        # Act / Assert
        assert _SHA_PINNED_ACTION_RE.fullmatch(hijacked) is None

    def test_subpath_suffix_is_rejected(self) -> None:
        # Arrange: a path change after the action name must be caught
        suffixed = f"{_ACTION_PATH}/subdir@{'0' * 40}"
        # Act / Assert
        assert _SHA_PINNED_ACTION_RE.fullmatch(suffixed) is None

    def test_uppercase_hex_is_rejected(self) -> None:
        # Arrange: GitHub SHAs are lowercase; uppercase signals a hand edit
        # Act / Assert
        assert _SHA_PINNED_ACTION_RE.fullmatch(f"{_ACTION_PATH}@{'A' * 40}") is None

    def test_valid_shape_is_accepted(self) -> None:
        # Arrange / Act / Assert: the synthetic ref used by negative-control
        # workflows passes, proving those fixtures stay representative
        assert _SHA_PINNED_ACTION_RE.fullmatch(_FAKE_ACTION_REF) is not None


class TestStepLookupEdgeCases:
    def test_find_step_returns_none_when_absent(self) -> None:
        # Arrange
        workflow: dict[str, Any] = {
            "jobs": {"only": {"steps": [{"name": "something else"}]}}
        }
        # Act
        step = _find_step(workflow, _AGENT_STEP_NAME)
        # Assert
        assert step is None

    def test_find_step_handles_job_with_no_steps(self) -> None:
        # Arrange: a job missing the steps key must not raise
        workflow: dict[str, Any] = {"jobs": {"empty": {}}}
        # Act
        step = _find_step(workflow, _AGENT_STEP_NAME)
        # Assert
        assert step is None

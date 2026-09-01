"""`PR_BODY` reaches the spec-context builder through the workflow (issue #5366).

`scripts/ci/spec_prepare_context.py` reads the PR body from the environment and
renders a `## Non-Executable Criteria Declaration` from it. Nothing else in the
repository sets that variable for the real run: the existing tests in
`tests/ci/test_spec_prepare_context.py` inject `PR_BODY` directly into
`monkeypatch.setenv`, which exercises the builder and bypasses the wiring.

Delete the `env:` entry from the workflow step and every one of those tests
stays green, while production silently sees an empty body forever. The builder
degrades quietly by design (`find_nonexecutable_criteria` returns `[]` for a
falsy body), so the failure has no symptom: the declaration simply never
appears and the gate goes back to failing closed on command-execution criteria,
which is the bug issue #5366 exists to fix.

Asserted against the parsed object graph, never a substring of the YAML text,
per `.claude/rules/testing.md` MUST-9, quoted verbatim:

    Assert on parsed structure, never on a substring of a structured file. A
    test that checks wiring in YAML, JSON, or TOML MUST parse the document and
    assert against the resulting object graph.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "ai-spec-validation.yml"

_JOB = "validate-spec"
_STEP_NAME = "Prepare Spec Context"
_BUILDER = "scripts/ci/spec_prepare_context.py"

# The expression the step must pass through. Author-controlled, so it belongs in
# `env:` and never inside a `run:` body (CWE-78). The External-signal gate step
# in the same workflow already reads the same expression the same way.
_PR_BODY_EXPRESSION = "${{ github.event.pull_request.body }}"


@pytest.fixture(scope="module")
def prepare_context_step() -> dict[str, Any]:
    """The parsed step that runs the spec-context builder."""
    workflow = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"][_JOB]["steps"]
    matches = [step for step in steps if isinstance(step, dict) and step.get("name") == _STEP_NAME]

    assert len(matches) == 1, (
        f"Expected exactly one {_STEP_NAME!r} step in job {_JOB!r}, found "
        f"{len(matches)} across {len(steps)} steps. Every assertion below "
        f"would be about the wrong step."
    )
    return matches[0]


class TestPrBodyIsWiredToTheContextBuilder:
    def test_the_step_runs_the_context_builder(self, prepare_context_step: dict[str, Any]) -> None:
        """Control: the env assertions below are about the right step.

        Without this, the step could be renamed onto some other command and
        the `PR_BODY` assertion would still pass while the builder ran
        somewhere else, or nowhere.
        """
        assert _BUILDER in str(prepare_context_step.get("run", "")), (
            f"The {_STEP_NAME!r} step does not run {_BUILDER}. Its run body is "
            f"{prepare_context_step.get('run')!r}."
        )

    def test_pr_body_is_passed_through_env(self, prepare_context_step: dict[str, Any]) -> None:
        env = prepare_context_step.get("env") or {}

        assert env.get("PR_BODY") == _PR_BODY_EXPRESSION, (
            "The spec-context step does not pass the PR body through env. "
            f"Expected PR_BODY == {_PR_BODY_EXPRESSION!r}, got "
            f"{env.get('PR_BODY')!r}. Without it the builder sees an empty "
            "body, the Non-Executable Criteria Declaration is never rendered, "
            "and the gate fails closed on command-execution criteria again "
            "(issue #5366). Env keys present: " + ", ".join(sorted(env))
        )

    def test_pr_body_is_not_interpolated_into_the_run_body(
        self, prepare_context_step: dict[str, Any]
    ) -> None:
        """The value is author-controlled, so it must never reach the shell.

        `.github/workflows` steps that inline `${{ github.event... }}` into a
        `run:` body are the CWE-78 shape this passes through `env:` to avoid.
        """
        run_body = str(prepare_context_step.get("run", ""))

        assert "github.event.pull_request.body" not in run_body, (
            "The PR body is interpolated into the step's run body, which is "
            f"the command-injection shape env: exists to avoid. run: {run_body!r}"
        )

    def test_the_sibling_env_entries_survive(self, prepare_context_step: dict[str, Any]) -> None:
        """Control: deleting the whole `env:` block fails here too.

        Without this, an assertion that only names `PR_BODY` cannot tell a
        targeted deletion from the block going missing wholesale, and the
        error message would point at the wrong cause.
        """
        env = prepare_context_step.get("env") or {}

        assert "SPEC_FILE" in env
        assert "INCREMENTAL_SCOPE" in env

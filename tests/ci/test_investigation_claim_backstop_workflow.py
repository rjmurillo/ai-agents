"""Pins the Issue #5210 decision for investigation-claim-backstop.yml.

Issue #5210 found that pr-validation.yml called post_issue_comment.py without
--update-if-exists, so a fixed PR kept showing its first failing verdict
forever. The issue named a second caller of the same script,
investigation-claim-backstop.yml, and required it be "explicitly decided,
either flagged as intentionally write-once with a comment saying so, or given
the flag" rather than silently left ambiguous.

This repo decided write-once is correct there: unlike pr-validation.yml,
the "Post Warning on Violations" step only runs `if: failure()` and never
re-posts once the PR is fixed, so there is no stale-PASS-shown-as-FAIL
failure mode to correct. These tests pin that decision so a future edit
cannot silently drop the explanation or add the flag without updating this
test to match.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "investigation-claim-backstop.yml"


def _post_warning_step() -> dict:
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = data["jobs"]["validate-claims"]["steps"]
    matching = [step for step in steps if step.get("name") == "Post Warning on Violations"]
    assert len(matching) == 1, "expected exactly one 'Post Warning on Violations' step"
    return matching[0]


def test_the_write_once_decision_is_intentional_not_an_oversight() -> None:
    """Positive: the step must not silently gain --update-if-exists.

    If a future change adds the flag here, it should be a deliberate
    decision (with this test updated to match), not a drive-by copy from
    pr-validation.yml's fix.
    """
    run = _post_warning_step().get("run", "")
    assert "post_issue_comment.py" in run
    assert "--marker \"INVESTIGATION-CLAIM-BACKSTOP\"" in run
    assert "--update-if-exists" not in run


def test_the_decision_is_documented_next_to_the_step() -> None:
    """Positive: the rationale must be readable at the call site, not only
    in the issue tracker, per Issue #5210's acceptance criteria.
    """
    workflow_text = WORKFLOW.read_text(encoding="utf-8")
    assert "Intentionally write-once" in workflow_text
    assert "#5210" in workflow_text


def test_the_step_only_fires_on_failure() -> None:
    """Edge: the decision's justification depends on this condition holding.

    Write-once is safe here only because the step never re-posts on a
    passing re-run. If this step ever stops being failure-gated, it inherits
    the same stale-verdict bug pr-validation.yml had, and the write-once
    decision above must be revisited.
    """
    assert _post_warning_step().get("if") == "failure()"

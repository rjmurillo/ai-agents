"""Regression tests for .github/workflows/ai-session-protocol.yml.

Issue #2384: The legacy-markdown branch invoked ./scripts/Convert-SessionToJson.ps1,
a script removed during the PowerShell-to-Python migration (PR #1063/#1064) and
whose wrapper was sunset in PR #2359. Any markdown session log routed through that
branch failed with "Migration failed". These tests pin the fix in place.
"""

from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOW = (
    Path(__file__).resolve().parent.parent
    / ".github"
    / "workflows"
    / "ai-session-protocol.yml"
)


def _validate_step_run() -> str:
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    jobs = doc["jobs"]
    validate_job = jobs["validate"]
    for step in validate_job["steps"]:
        if step.get("id") == "validate":
            return step["run"]
    raise AssertionError("validate step not found in ai-session-protocol.yml")


def test_workflow_does_not_call_phantom_convert_script() -> None:
    """Issue #2384: phantom Convert-SessionToJson.ps1 must not be invoked."""
    body = WORKFLOW.read_text(encoding="utf-8")
    assert "Convert-SessionToJson.ps1" not in body, (
        "ai-session-protocol.yml still references the removed "
        "Convert-SessionToJson.ps1 script (issue #2384)."
    )


def test_workflow_does_not_claim_legacy_markdown_migration() -> None:
    """The dead 'migrate to JSON first' branch must be gone."""
    run = _validate_step_run()
    assert "Migration failed - could not convert markdown to JSON" not in run
    assert "Legacy markdown detected - migrating to JSON" not in run


def test_markdown_branch_fails_fast_with_actionable_message() -> None:
    """Markdown session logs should now fail fast with guidance, not silently retry."""
    run = _validate_step_run()
    assert "Markdown session logs are no longer supported." in run
    assert "session-init now emits JSON" in run
    # Branch must still set a non-zero exit so CI surfaces the failure.
    assert "$exitCode = 1" in run


def test_json_branch_still_calls_python_validator() -> None:
    """JSON path is the supported branch; keep its validator wired up."""
    run = _validate_step_run()
    assert "python3 ./scripts/validate_session_json.py $sessionFile" in run

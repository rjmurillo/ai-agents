"""Result-job tests for the CLI smoke workflow.

``CLI Smoke Result`` is the one required check. It always runs, waits for every
other job, and names the fork when the trust gate denies.
"""

from __future__ import annotations

from typing import Any

from tests.lib.cli_smoke_workflow import (
    REPO_ROOT,
    _step_by_name,
)

pytest_plugins = ["tests.lib.cli_smoke_fixtures"]


def test_result_job_always_runs_and_waits_for_every_other_job(
    workflow_doc: dict[Any, Any],
) -> None:
    result = workflow_doc["jobs"]["smoke-result"]

    assert result["name"] == "CLI Smoke Result"
    assert result["if"] == "${{ !cancelled() }}"
    assert set(result["needs"]) == {"changes", "authorize", "smoke", "smoke-codex"}
    assert "environment" not in result


def test_result_job_checks_every_leg_and_names_the_fork(workflow_doc: dict[Any, Any]) -> None:
    """REQ-047 AC6, AC12: any skipped, cancelled, or failed leg turns the gate red."""
    report = _step_by_name(workflow_doc["jobs"]["smoke-result"], "Report")
    env = report["env"]

    for variable, job in [
        ("CHANGES_RESULT", "changes"),
        ("AUTHORIZE_RESULT", "authorize"),
        ("SMOKE_RESULT", "smoke"),
        ("CODEX_RESULT", "smoke-codex"),
    ]:
        assert env[variable] == f"${{{{ needs.{job}.result }}}}"
        assert f"{variable} success" in report["run"]
    assert env["TRUSTED"] == "${{ needs.authorize.outputs.trusted }}"
    assert env["RUN"] == "${{ needs.changes.outputs.run }}"
    assert "--skip-when RUN false" in report["run"]
    assert "TRUSTED true" in report["run"]
    assert "fork pull request" in report["run"]
    assert "smoke_result.py" in report["run"]


def test_result_job_filter_failure_is_not_skippable(workflow_doc: dict[Any, Any]) -> None:
    """Negative: a broken path filter must fail the gate, not read as 'nothing to run'."""
    run = _step_by_name(workflow_doc["jobs"]["smoke-result"], "Report")["run"]

    assert "--check CHANGES_RESULT success" in " ".join(run.split())


def test_nightly_workflow_is_removed() -> None:
    assert not (REPO_ROOT / ".github" / "workflows" / "nightly-cli-smoke.yml").exists()

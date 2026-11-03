"""Pin the wiring of .github/workflows/check-ruleset-drift.yml on parsed YAML."""

from pathlib import Path

import yaml

WORKFLOW_PATH = (
    Path(__file__).resolve().parents[2] / ".github" / "workflows" / "check-ruleset-drift.yml"
)


def test_run_step_alerts_and_token_can_write_issues() -> None:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    triggers = workflow.get(True, workflow.get("on"))
    job = workflow["jobs"]["drift-check"]

    assert triggers["schedule"] == [{"cron": "0 6 * * *"}]
    assert "workflow_dispatch" in triggers
    assert workflow["permissions"] == {"contents": "read"}
    assert job["permissions"] == {"contents": "read", "issues": "write"}
    assert job["timeout-minutes"] == 5
    assert any(
        step.get("run") == "python3 scripts/validation/check_ruleset_params_drift.py --alert"
        for step in job["steps"]
    )
    assert job["steps"][0]["with"] == {"persist-credentials": False}

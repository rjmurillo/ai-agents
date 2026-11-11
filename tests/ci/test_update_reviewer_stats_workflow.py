"""Wiring tests for .github/workflows/update-reviewer-stats.yml (issue #7287).

The workflow splits into an unprivileged aggregation job and a publish job that
alone holds write scopes. These tests parse the YAML and assert on the object
graph, so a deleted step or a widened scope fails by name.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_REPO = Path(__file__).resolve().parents[2]


def _workflow_jobs() -> dict[str, dict]:
    doc = yaml.safe_load(
        (_REPO / ".github" / "workflows" / "update-reviewer-stats.yml").read_text(encoding="utf-8")
    )
    return doc["jobs"]


def test_workflow_gives_write_scopes_only_to_the_publish_job() -> None:
    jobs = _workflow_jobs()
    assert jobs["update-stats"]["permissions"] == {"contents": "read", "pull-requests": "read"}
    assert jobs["publish-stats"]["permissions"] == {
        "contents": "write",
        "pull-requests": "write",
    }
    assert jobs["publish-stats"]["needs"] == "update-stats"


def test_publish_job_runs_the_script_and_the_aggregation_job_does_not() -> None:
    jobs = _workflow_jobs()
    runs = {
        name: [s.get("run", "") for s in job["steps"] if "run" in s] for name, job in jobs.items()
    }
    assert any(
        "open_bot_pr.py" in r and "--branch automation/reviewer-stats" in r
        for r in runs["publish-stats"]
    )
    assert not any("open_bot_pr.py" in r for r in runs["update-stats"])
    assert not any("uv run" in r for r in runs["publish-stats"])


def test_artifact_hands_both_report_files_from_the_first_job_to_the_second() -> None:
    jobs = _workflow_jobs()
    (up,) = [s for s in jobs["update-stats"]["steps"] if "upload-artifact" in s.get("uses", "")]
    (down,) = [
        s for s in jobs["publish-stats"]["steps"] if "download-artifact" in s.get("uses", "")
    ]
    files = [
        ".serena/memories/pr-review/pr-comment-responder-skills.md",
        ".project-toolkit/metrics/agent-pr-intervention.md",
    ]
    assert up["with"]["name"] == down["with"]["name"]
    assert up["with"]["path"].split() == files
    # Two paths make the repository root the artifact root, so it extracts there.
    assert down["with"]["path"] == "."
    assert up["with"]["if-no-files-found"] == "error"
    assert up["with"]["include-hidden-files"] is True
    (publish,) = [s for s in jobs["publish-stats"]["steps"] if "open_bot_pr.py" in s.get("run", "")]
    for file in files:
        assert f"--path {file}" in publish["run"]


def test_the_upload_and_the_publish_job_run_even_when_the_stats_step_fails() -> None:
    jobs = _workflow_jobs()
    steps = {s.get("name"): s for s in jobs["update-stats"]["steps"]}
    assert steps["Build agent PR intervention report"]["if"] == "${{ !cancelled() }}"
    assert steps["Upload updated stats"]["if"] == "${{ !cancelled() }}"
    assert "!cancelled()" in jobs["publish-stats"]["if"]
    assert "needs.update-stats.result != 'skipped'" in jobs["publish-stats"]["if"]


def test_neither_job_persists_checkout_credentials() -> None:
    for job in _workflow_jobs().values():
        (checkout,) = [s for s in job["steps"] if "actions/checkout" in s.get("uses", "")]
        assert checkout["with"]["persist-credentials"] is False


def test_the_publish_step_sets_the_token_and_git_credential_helper() -> None:
    steps = _workflow_jobs()["publish-stats"]["steps"]
    (publish,) = [s for s in steps if "open_bot_pr.py" in s.get("run", "")]
    assert publish["env"]["GH_TOKEN"] == "${{ github.token }}"
    assert "gh auth setup-git" in publish["run"]

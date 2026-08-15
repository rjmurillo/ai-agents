"""Tests for scheduled required-context drift detection."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml


def _capture(target: list[str], item: str) -> int:
    target.append(item)
    return 0

from scripts.ci import ruleset_context_drift as drift  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = (
    REPO_ROOT / ".github" / "workflows" / "ruleset-context-drift.yml"
)


def test_matching_contexts_return_zero_without_publishing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        drift,
        "query_live_contexts",
        lambda: set(drift.REQUIRED_CONTEXTS),
    )
    monkeypatch.setattr(
        drift,
        "publish_alert",
        lambda _body: pytest.fail("matching contexts must not publish an alert"),
    )

    assert drift.main([]) == drift.EXIT_OK


def test_wrong_pinned_contexts_return_one_and_name_the_difference(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(drift, "REQUIRED_CONTEXTS", frozenset({"shared", "pinned-only"}))
    monkeypatch.setattr(
        drift,
        "query_live_contexts",
        lambda: {"shared", "live-only"},
    )

    assert drift.main([]) == drift.EXIT_DRIFT

    output = capsys.readouterr().out
    assert "`live-only`" in output
    assert "`pinned-only`" in output
    assert "### Live contexts (2)" in output
    assert "### Pinned contexts (2)" in output
    assert drift.REFRESH_COMMAND in output


def test_alert_is_published_before_drift_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published: list[str] = []
    monkeypatch.setattr(drift, "REQUIRED_CONTEXTS", frozenset({"pinned"}))
    monkeypatch.setattr(drift, "query_live_contexts", lambda: {"live"})
    monkeypatch.setattr(
        drift,
        "publish_alert",
        lambda body: _capture(published, body),
    )

    assert drift.main(["--alert"]) == drift.EXIT_DRIFT
    assert len(published) == 1
    assert "`live`" in published[0]
    assert "`pinned`" in published[0]


def test_github_query_failure_returns_external_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_query() -> set[str]:
        raise RuntimeError("rules endpoint unavailable")

    monkeypatch.setattr(drift, "query_live_contexts", fail_query)

    assert drift.main([]) == drift.EXIT_EXTERNAL


def test_live_query_uses_the_effective_main_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[tuple[str, str, str]] = []

    def fetch(owner: str, repo: str, branch: str) -> list[str]:
        captured.append((owner, repo, branch))
        return ["context-b", "context-a"]

    monkeypatch.setattr(drift, "fetch_ruleset_required_contexts", fetch)

    assert drift.query_live_contexts() == {"context-a", "context-b"}
    assert captured == [("rjmurillo", "ai-agents", "main")]


def test_issue_skill_parses_success_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=json.dumps({"Success": True, "Data": {"count": 0}}),
        stderr="",
    )
    monkeypatch.setattr(drift.subprocess, "run", lambda *args, **kwargs: result)

    assert drift._run_issue_skill("list_issues.py", []) == (
        drift.EXIT_OK,
        {"count": 0},
    )


@pytest.mark.parametrize(
    ("returncode", "stdout", "expected"),
    [
        (4, "", 4),
        (0, "not json", drift.EXIT_EXTERNAL),
    ],
)
def test_issue_skill_rejects_failed_or_invalid_output(
    returncode: int,
    stdout: str,
    expected: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=stdout,
        stderr="failure",
    )
    monkeypatch.setattr(drift.subprocess, "run", lambda *args, **kwargs: result)

    rc, data = drift._run_issue_skill("list_issues.py", [])

    assert rc == expected
    assert data == {}


def test_publish_alert_requires_runner_temp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RUNNER_TEMP", raising=False)

    assert drift.publish_alert("body") == drift.EXIT_CONFIG


def test_bare_python_entrypoint_loads_with_workflow_pythonpath() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/ci/ruleset_context_drift.py", "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
        check=False,
    )

    assert result.returncode == drift.EXIT_OK
    assert "Detect drift in the required status check contexts." in result.stdout


def test_publish_alert_creates_issue_with_github_skills(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, list[str]]] = []

    def run_skill(
        script_name: str,
        arguments: list[str],
    ) -> tuple[int, dict[str, Any]]:
        calls.append((script_name, arguments))
        if script_name == "list_issues.py":
            return drift.EXIT_OK, {"issues": [], "count": 0}
        return drift.EXIT_OK, {"number": 1}

    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setattr(drift, "_run_issue_skill", run_skill)

    assert drift.publish_alert("alert body") == drift.EXIT_OK
    assert [name for name, _ in calls] == ["list_issues.py", "new_issue.py"]
    assert "--body-file" in calls[1][1]
    assert "--labels" in calls[1][1]


def test_publish_alert_updates_existing_issue_with_github_skills(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, list[str]]] = []

    def run_skill(
        script_name: str,
        arguments: list[str],
    ) -> tuple[int, dict[str, Any]]:
        calls.append((script_name, arguments))
        if script_name == "list_issues.py":
            return drift.EXIT_OK, {"issues": [{"number": 42}], "count": 1}
        return drift.EXIT_OK, {"issue": 42}

    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setattr(drift, "_run_issue_skill", run_skill)

    assert drift.publish_alert("updated body") == drift.EXIT_OK
    assert [name for name, _ in calls] == [
        "list_issues.py",
        "post_issue_comment.py",
    ]
    issue_index = calls[1][1].index("--issue")
    assert calls[1][1][issue_index : issue_index + 2] == ["--issue", "42"]
    assert "--update-if-exists" in calls[1][1]


def test_workflow_runs_the_detector_on_schedule_and_manual_dispatch() -> None:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    triggers = workflow.get(True, workflow.get("on"))
    job = workflow["jobs"]["detect-drift"]
    steps = job["steps"]

    assert triggers["schedule"] == [{"cron": "0 7 * * 2,5"}]
    assert triggers["workflow_dispatch"] is None
    assert workflow["concurrency"] == {
        "group": "ruleset-context-drift",
        "cancel-in-progress": False,
    }
    assert job["permissions"] == {"contents": "read", "issues": "write"}
    assert job["runs-on"] == "ubuntu-24.04-arm"
    assert drift._format_contexts(()) == "- None"
    assert any(
        step.get("run")
        == "PYTHONPATH=. python3 scripts/ci/ruleset_context_drift.py --alert"
        for step in steps
    )

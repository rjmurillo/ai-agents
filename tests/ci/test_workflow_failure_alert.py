"""Tests for the unattended-workflow failure alert."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.ci import workflow_failure_alert as alert

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
ALERT_WORKFLOW = WORKFLOWS / "workflow-failure-alert.yml"
SCRIPT = REPO_ROOT / "scripts" / "ci" / "workflow_failure_alert.py"
ISSUE_PROVENANCE = REPO_ROOT / ".claude" / "skills" / "github" / "scripts" / "issue"


def _payload(**overrides: Any) -> dict[str, Any]:
    run: dict[str, Any] = {
        "name": "Agent Metrics",
        "conclusion": "failure",
        "event": "schedule",
        "head_branch": "main",
        "html_url": "https://github.com/rjmurillo/ai-agents/actions/runs/1",
        "head_sha": "abcdef1234567890",
        "run_attempt": 2,
    }
    run.update(overrides)
    return {"workflow_run": run}


def _load_yaml(path: Path) -> dict[Any, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _triggers(doc: dict[Any, Any]) -> dict[str, Any]:
    # PyYAML reads the bare key `on` as boolean True.
    return doc.get("on") or doc[True]


def test_failed_watched_run_is_parsed() -> None:
    parsed = alert.parse_event(_payload())

    assert isinstance(parsed, alert.FailedRun)
    assert parsed.head_sha == "abcdef123456"
    assert parsed.attempt == 2


@pytest.mark.parametrize("conclusion", ["failure", "timed_out", "startup_failure"])
def test_failing_conclusions_alert(conclusion: str) -> None:
    assert isinstance(alert.parse_event(_payload(conclusion=conclusion)), alert.FailedRun)


@pytest.mark.parametrize(
    "conclusion", ["success", "cancelled", "skipped", "neutral", "action_required", None]
)
def test_non_failing_conclusions_do_not_alert(conclusion: str | None) -> None:
    assert isinstance(alert.parse_event(_payload(conclusion=conclusion)), str)


def test_unwatched_workflow_does_not_alert() -> None:
    assert "not watched" in str(alert.parse_event(_payload(name="Pull Request Check")))


def test_non_string_workflow_name_does_not_alert() -> None:
    assert isinstance(alert.parse_event(_payload(name=["Agent Metrics"])), str)


def test_publish_tag_push_does_not_alert_but_dispatch_does() -> None:
    assert isinstance(alert.parse_event(_payload(name="npm Publish", event="push")), str)
    assert isinstance(
        alert.parse_event(_payload(name="npm Publish", event="workflow_dispatch")),
        alert.FailedRun,
    )


def test_other_branch_does_not_alert() -> None:
    assert "not main" in str(alert.parse_event(_payload(head_branch="feature/x")))


@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        "http://example.com/run",
        5,
        "https://example.com/run",
        "https://github.com/other/repo/actions/runs/1",
        "https://github.com/rjmurillo/ai-agents/actions/runs/1\n@someone",
    ],
)
def test_run_without_https_url_does_not_alert(url: object) -> None:
    assert isinstance(alert.parse_event(_payload(html_url=url)), str)


@pytest.mark.parametrize(
    "overrides",
    [{"conclusion": []}, {"event": {}}, {"head_sha": "| @someone\n", "run_attempt": True}],
)
def test_malformed_metadata_cannot_inject_issue_content(overrides):
    parsed = alert.parse_event(_payload(**overrides))
    if isinstance(parsed, alert.FailedRun):
        assert parsed.head_sha == "unknown"
        assert parsed.attempt == 1
    else:
        assert isinstance(parsed, str)


@pytest.mark.parametrize("payload", [None, [], "x", {}, {"workflow_run": "x"}])
def test_malformed_payload_does_not_alert(payload: object) -> None:
    assert isinstance(alert.parse_event(payload), str)


def test_missing_sha_and_attempt_use_safe_defaults() -> None:
    parsed = alert.parse_event(_payload(head_sha=None, run_attempt="two"))

    assert isinstance(parsed, alert.FailedRun)
    assert (parsed.head_sha, parsed.attempt) == ("unknown", 1)


def test_marker_and_title_are_stable_per_workflow() -> None:
    assert alert.alert_title("Agent-Skill Discriminator Check") == (
        "Workflow failed: Agent-Skill Discriminator Check"
    )
    assert alert.alert_marker("Agent-Skill Discriminator Check") == (
        "WORKFLOW-FAILURE-AGENT-SKILL-DISCRIMINATOR-CHECK"
    )


def test_body_carries_marker_run_url_and_runbook_and_no_log_text() -> None:
    parsed = alert.parse_event(_payload())
    assert isinstance(parsed, alert.FailedRun)

    body = alert.render_body(parsed)

    assert body.startswith("<!-- WORKFLOW-FAILURE-AGENT-METRICS -->")
    assert parsed.url in body
    assert "docs/runbooks/workflow-failure-alert.md" in body
    assert (REPO_ROOT / alert.RUNBOOK_PATH).is_file()


def test_step0_evidence_passes_the_issue_hedge_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(ISSUE_PROVENANCE))
    import issue_provenance

    for name in alert.WATCHED:
        parsed = alert.parse_event(
            _payload(name=name, event=sorted(alert.WATCHED[name])[0]),
        )
        assert isinstance(parsed, alert.FailedRun)
        blocked_by, signal = alert.step0_evidence(parsed)
        assert issue_provenance.hedge_match(blocked_by) is None
        assert issue_provenance.hedge_match(signal) is None


def test_run_publishes_with_derived_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(alert, "publish_issue_alert", lambda **kw: calls.append(kw) or 0)

    rc = alert.run(_payload())

    assert rc == 0
    assert calls[0]["title"] == "Workflow failed: Agent Metrics"
    assert calls[0]["marker"] == "WORKFLOW-FAILURE-AGENT-METRICS"
    assert calls[0]["labels"] == alert.ALERT_LABELS


def test_run_skips_publish_when_nothing_to_alert(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(alert, "publish_issue_alert", lambda **kw: calls.append(kw) or 0)

    assert alert.run(_payload(conclusion="success")) == 0
    assert calls == []


def test_run_returns_publish_failure_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(alert, "publish_issue_alert", lambda **kw: 3)

    assert alert.run(_payload()) == 3


def test_main_exits_config_without_event_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)

    assert alert.main([]) == alert.EXIT_CONFIG


def test_main_exits_config_on_unparseable_event(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    event = tmp_path / "event.json"
    event.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))

    assert alert.main([]) == alert.EXIT_CONFIG


def test_main_exits_config_on_arguments() -> None:
    assert alert.main(["--surprise"]) == alert.EXIT_CONFIG


def test_main_publishes_from_event_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    event = tmp_path / "event.json"
    event.write_text(json.dumps(_payload()), encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    seen: list[str] = []
    monkeypatch.setattr(alert, "publish_issue_alert", lambda **kw: seen.append(kw["title"]) or 3)

    assert alert.main([]) == 3
    assert seen == ["Workflow failed: Agent Metrics"]


def test_cli_nonzero_when_event_path_missing(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={"PATH": "/usr/bin:/bin", "GITHUB_EVENT_PATH": str(tmp_path / "absent.json")},
        check=False,
    )

    assert result.returncode == alert.EXIT_CONFIG


def test_workflow_lists_exactly_the_watched_names() -> None:
    listed = _triggers(_load_yaml(ALERT_WORKFLOW))["workflow_run"]["workflows"]

    assert sorted(listed) == sorted(alert.WATCHED)


def test_every_scheduled_workflow_is_watched_or_self_alerting() -> None:
    scheduled: set[str] = set()
    for path in WORKFLOWS.glob("*.yml"):
        doc = _load_yaml(path)
        if isinstance(doc, dict) and "schedule" in (_triggers(doc) or {}):
            scheduled.add(doc["name"])

    assert scheduled, "no scheduled workflows found; the scan is broken"
    unaccounted = scheduled - set(alert.WATCHED) - alert.SELF_ALERTING
    assert not unaccounted, f"decide watch or self-alerting for: {sorted(unaccounted)}"
    assert not set(alert.WATCHED) & alert.SELF_ALERTING


def test_watched_and_self_alerting_names_exist_as_workflows() -> None:
    names = {_load_yaml(p)["name"] for p in WORKFLOWS.glob("*.yml")}

    assert (set(alert.WATCHED) | alert.SELF_ALERTING) <= names


def test_alert_workflow_is_least_privilege_and_pinned() -> None:
    doc = _load_yaml(ALERT_WORKFLOW)

    assert doc["permissions"] == {}
    assert doc["concurrency"]["cancel-in-progress"] is True
    assert "github.event.workflow_run.name" in doc["concurrency"]["group"]
    job = doc["jobs"]["alert"]
    assert job["permissions"] == {"contents": "read", "issues": "write"}
    actions = [step for step in job["steps"] if "uses" in step]
    for step in actions:
        assert re.search(r"@[0-9a-f]{40}$", step["uses"]), step["uses"]
    checkout = next(step for step in actions if step["uses"].startswith("actions/checkout@"))
    assert "ref" not in checkout["with"], "must check out the default branch"
    assert checkout["with"]["persist-credentials"] is False
    run_blocks = [s["run"] for s in job["steps"] if "run" in s]
    assert all("${{" not in block for block in run_blocks)

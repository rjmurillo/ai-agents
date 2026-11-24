"""Tests for the unattended-workflow failure alert."""

from __future__ import annotations

import json
import os
import random
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import Mock

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
    publisher = Mock(return_value=0)
    monkeypatch.setattr(alert, "publish_issue_alert", publisher)

    rc = alert.run(_payload())

    assert rc == 0
    publisher.assert_called_once()
    assert publisher.call_args.kwargs["title"] == "Workflow failed: Agent Metrics"
    assert publisher.call_args.kwargs["marker"] == "WORKFLOW-FAILURE-AGENT-METRICS"
    assert publisher.call_args.kwargs["labels"] == alert.ALERT_LABELS


def test_run_skips_publish_when_nothing_to_alert(monkeypatch: pytest.MonkeyPatch) -> None:
    publisher = Mock(return_value=0)
    monkeypatch.setattr(alert, "publish_issue_alert", publisher)

    assert alert.run(_payload(conclusion="success")) == 0
    publisher.assert_not_called()


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
    publisher = Mock(return_value=3)
    monkeypatch.setattr(alert, "publish_issue_alert", publisher)

    assert alert.main([]) == 3
    publisher.assert_called_once()
    assert publisher.call_args.kwargs["title"] == "Workflow failed: Agent Metrics"


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
    assert "concurrency" not in doc
    job = doc["jobs"]["alert"]
    assert job["concurrency"]["cancel-in-progress"] is True
    assert "github.event.workflow_run.name" in job["concurrency"]["group"]
    assert job["permissions"] == {"contents": "read", "issues": "write"}
    actions = [step for step in job["steps"] if "uses" in step]
    for step in actions:
        assert re.search(r"@[0-9a-f]{40}$", step["uses"]), step["uses"]
    checkout = next(step for step in actions if step["uses"].startswith("actions/checkout@"))
    assert "ref" not in checkout["with"], "must check out the default branch"
    assert checkout["with"]["persist-credentials"] is False
    run_blocks = [s["run"] for s in job["steps"] if "run" in s]
    assert all("${{" not in block for block in run_blocks)


def _workflow_eligibility(payload: object, tmp_path: Path) -> bool:
    """Execute the parsed workflow adapter, not a second eligibility policy."""
    job = _load_yaml(ALERT_WORKFLOW)["jobs"]["eligibility"]
    step = next(s for s in job["steps"] if s.get("id") == "classify")
    event = tmp_path / "event.json"
    output = tmp_path / "output"
    event.write_text(json.dumps(payload), encoding="utf-8")
    output.write_text("", encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith("GITHUB_") and k != "CI"}
    env.update(GITHUB_EVENT_PATH=str(event), GITHUB_OUTPUT=str(output))
    result = subprocess.run(
        ["bash", "-e", "-c", step["run"]],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    value = output.read_text(encoding="utf-8").strip()
    assert value in {"eligible=true", "eligible=false"}
    return value == "eligible=true"


def test_alert_concurrency_is_behind_canonical_eligibility() -> None:
    """AC1: Only the canonical classifier can admit the publishing job."""
    doc = _load_yaml(ALERT_WORKFLOW)
    assert "concurrency" not in doc
    classifier = doc["jobs"]["eligibility"]
    assert "concurrency" not in classifier
    assert classifier["permissions"] == {"contents": "read"}
    assert classifier["outputs"] == {"eligible": "${{ steps.classify.outputs.eligible }}"}
    job = doc["jobs"]["alert"]
    assert job["needs"] == "eligibility"
    classify_step = next(s for s in classifier["steps"] if s.get("id") == "classify")
    assert classify_step["run"] == "python3 scripts/ci/workflow_failure_alert.py --classify"
    assert job["if"] == "${{ needs.eligibility.outputs.eligible == 'true' }}"
    assert job["concurrency"] == {
        "group": "workflow-failure-alert-${{ github.event.workflow_run.name }}",
        "cancel-in-progress": True,
    }
    for candidate in (classifier, job):
        checkout = next(
            s for s in candidate["steps"] if s.get("uses", "").startswith("actions/checkout@")
        )
        assert checkout["with"] == {"persist-credentials": False}
        assert all(
            re.search(r"@[0-9a-f]{40}$", s["uses"]) for s in candidate["steps"] if "uses" in s
        )


@pytest.mark.parametrize(
    "overrides",
    [
        *[
            {"conclusion": c}
            for c in ("success", "cancelled", "skipped", "neutral", "action_required", None)
        ],
        *[
            {"event": e}
            for e in (
                "pull_request",
                "pull_request_target",
                "push",
                "release",
                "workflow_run",
                None,
            )
        ],
        {"name": "CodeQL Analysis", "event": "workflow_dispatch"},
        {"name": "npm Publish", "event": "schedule"},
        *[{"head_branch": b} for b in ("feature/x", "MAIN", "", None)],
        {"name": "not watched"},
        {"html_url": "https://example.com/run"},
    ],
)
def test_ignored_completions_cannot_enter_alert_concurrency(overrides, tmp_path) -> None:
    """AC1: Ignored failures, successes, branches, and triggers never acquire a group."""
    assert not _workflow_eligibility(_payload(**overrides), tmp_path)


def test_repeated_overlaps_keep_only_eligible_same_workflow_keys(tmp_path) -> None:
    """AC1: Local admission/key model, not execution of GitHub's scheduler."""
    events = [
        _payload(name=name, event=event, conclusion=conclusion)
        for name, triggers in alert.WATCHED.items()
        for event in triggers
        for conclusion in alert.FAILING_CONCLUSIONS
    ]
    random.Random(os.environ.get("PYTHONHASHSEED", "0")).shuffle(events)
    active: dict[str, int] = {}
    for sequence, event in enumerate(events):
        assert _workflow_eligibility(event, tmp_path)
        name = event["workflow_run"]["name"]
        active[name.casefold()] = sequence
        assert not _workflow_eligibility(
            {
                **event,
                "workflow_run": {
                    **event["workflow_run"],
                    "conclusion": "success",
                },
            },
            tmp_path,
        )
        assert active[name.casefold()] == sequence
    assert len(active) == len(alert.WATCHED)


def _classify(payload: object, tmp_path: Path) -> tuple[int, str, str]:
    event = tmp_path / "event.json"
    output = tmp_path / "output"
    event.write_text(json.dumps(payload), encoding="utf-8")
    output.write_text("", encoding="utf-8")
    env = {"PATH": "/usr/bin:/bin", "GITHUB_EVENT_PATH": str(event), "GITHUB_OUTPUT": str(output)}
    result = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), "--classify"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    return result.returncode, result.stdout, output.read_text(encoding="utf-8")


def test_classify_eligible_run_prints_reason_and_writes_output(tmp_path: Path) -> None:
    rc, stdout, written = _classify(_payload(), tmp_path)

    assert rc == 0
    assert stdout.startswith("Eligible: Agent Metrics ended failure on schedule: https://")
    assert written == "eligible=true\n"


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"conclusion": "success"}, "conclusion 'success' does not raise an alert"),
        ({"name": "not watched"}, "workflow 'not watched' is not watched"),
        ({"event": "push"}, "trigger 'push' does not raise an alert for Agent Metrics"),
        ({"head_branch": "feature/x"}, "run was on branch 'feature/x', not"),
        ({"html_url": "https://example.com/run"}, "run has no valid repository run URL"),
    ],
)
def test_classify_skip_prints_reason_and_writes_false(
    overrides: dict[str, Any], reason: str, tmp_path: Path
) -> None:
    rc, stdout, written = _classify(_payload(**overrides), tmp_path)

    assert rc == 0
    assert stdout.startswith("Skip: ")
    assert reason in stdout
    assert written == "eligible=false\n"


def test_classify_skip_when_payload_has_no_workflow_run(tmp_path: Path) -> None:
    rc, stdout, written = _classify({}, tmp_path)

    assert rc == 0
    assert "Skip: payload has no workflow_run object." in stdout
    assert written == "eligible=false\n"


def test_classify_appends_to_existing_github_output(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.write_text("other=1\n", encoding="utf-8")

    rc = alert.classify(_payload(), {"GITHUB_OUTPUT": str(output)})

    assert rc == 0
    assert output.read_text(encoding="utf-8") == "other=1\neligible=true\n"


def test_classify_exits_config_without_github_output() -> None:
    assert alert.classify(_payload(), {}) == alert.EXIT_CONFIG


def test_classify_exits_config_when_output_unwritable(tmp_path: Path) -> None:
    missing = tmp_path / "no-such-dir" / "output"

    assert alert.classify(_payload(), {"GITHUB_OUTPUT": str(missing)}) == alert.EXIT_CONFIG


def test_main_classify_never_publishes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    event = tmp_path / "event.json"
    output = tmp_path / "output"
    event.write_text(json.dumps(_payload()), encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    publisher = Mock(return_value=3)
    monkeypatch.setattr(alert, "publish_issue_alert", publisher)

    assert alert.main(["--classify"]) == 0
    publisher.assert_not_called()
    assert output.read_text(encoding="utf-8") == "eligible=true\n"


def test_main_classify_exits_config_without_event_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)

    assert alert.main(["--classify"]) == alert.EXIT_CONFIG

"""End to end: gate, resolve, overlap, write from the skeleton, verify."""

from __future__ import annotations

import json
from pathlib import Path

import skillify
from skill_fixtures import SKILL_DIR

TRIGGER = "triage a flaky test"
SKELETON = """---
name: flaky-test-triage
description: Triage a flaky test by rerunning it. Use when you say `triage a flaky test`.
---

# Flaky Test Triage

Find the cause of a test that fails at random.

## Triggers

`triage a flaky test`

## Contract

The cause is named and a rerun count is recorded.

## Procedure

1. Rerun the test 20 times and record the failures.
2. If the failure rate is above 0, bisect by disabling shared fixtures.
3. Optional recovery: when reruns never fail, capture the CI environment.
4. Ask for approval before opening an issue on the public tracker.

## Anti-patterns

- Marking the test skipped with no cause.
- Opening a public issue without approval.

## Pitfalls

- Parallel workers share a temp directory.
- Retries hide the failure rate.

## Verification

- [ ] The rerun count and cause are recorded.
"""


def run_cli(capsys, *argv):
    code = skillify.main(list(argv))
    return code, json.loads(capsys.readouterr().out)


def test_full_flow_from_an_unrelated_directory(tmp_path, capsys):
    repo = tmp_path / "other repo"
    (repo / ".git").mkdir(parents=True)
    (repo / ".claude" / "skills").mkdir(parents=True)
    audit = {
        "tool_call_count": 8,
        "reusable_class": True,
        "decision_points": 2,
        "gotchas": ["shared temp dir"],
        "trigger_phrase": TRIGGER,
        "external_actions": True,
        "recovery_paths": True,
    }
    audit_file = tmp_path / "audit.json"
    audit_file.write_text(json.dumps(audit), encoding="utf-8")

    code, gate = run_cli(capsys, "gate", "--audit", str(audit_file))
    assert (code, gate["status"]) == (0, "PROCEED")

    code, dest = run_cli(capsys, "resolve", "--cwd", str(repo))
    assert (code, dest["source"], dest["harness"]) == (0, "cwd", "claude-code")

    workflow = {
        "actions": ["rerun failing test", "bisect shared fixtures", "capture environment"],
        "trigger_phrase": TRIGGER,
    }
    workflow_file = tmp_path / "workflow.json"
    workflow_file.write_text(json.dumps(workflow), encoding="utf-8")
    code, overlap = run_cli(
        capsys, "overlap", "--workflow", str(workflow_file), "--root", dest["path"]
    )
    assert (code, overlap["status"]) == (0, "CREATE")

    target = Path(dest["path"]) / "flaky-test-triage"
    target.mkdir()
    (target / "SKILL.md").write_text(SKELETON, encoding="utf-8")

    code, verdict = run_cli(capsys, "verify", "--skill", str(target), "--audit", str(audit_file))
    assert (code, verdict["status"], verdict["failures"]) == (0, "PASS", [])
    assert verdict["trigger"] == TRIGGER

    code, again = run_cli(
        capsys, "overlap", "--workflow", str(workflow_file), "--root", dest["path"]
    )
    assert (again["status"], again["skill"]) == ("PATCH", "flaky-test-triage")


def test_skeleton_in_reference_lists_the_checked_sections():
    text = (SKILL_DIR / "references" / "skill-skeleton.md").read_text(encoding="utf-8")
    for heading in (
        "Triggers",
        "Contract",
        "Procedure",
        "Anti-patterns",
        "Pitfalls",
        "Verification",
    ):
        assert heading.lower() in text.lower()

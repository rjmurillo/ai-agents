"""Wiring tests for .github/workflows/enforcement-closure.yml (ADR-101 Phase 1).

The workflow's whole value is that a pull request cannot rewrite the job that
reports on it and that the pull request head is read as data. Those are
properties of the YAML, so each is pinned by parsing it.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/enforcement-closure.yml"
_SHA_PIN = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


@pytest.fixture(scope="module")
def document() -> dict[Any, Any]:
    loaded = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _triggers(document: dict[Any, Any]) -> dict[str, Any]:
    """The trigger block. YAML 1.1 files a bare `on` key under True."""
    triggers = document["on"] if "on" in document else document[True]
    assert isinstance(triggers, dict)
    return triggers


def _jobs(document: dict[Any, Any]) -> dict[str, dict[str, Any]]:
    return document["jobs"]


def _steps(document: dict[Any, Any], job: str) -> list[dict[str, Any]]:
    return _jobs(document)[job]["steps"]


class TestTriggers:
    def test_the_workflow_runs_from_the_base_on_every_trigger(
        self, document: dict[Any, Any]
    ) -> None:
        # YAML 1.1 files a bare `on` key under True.
        triggers = _triggers(document)

        assert set(triggers) == {"schedule", "workflow_dispatch", "pull_request_target"}

    def test_no_trigger_runs_the_head_definition_of_the_workflow(
        self, document: dict[Any, Any]
    ) -> None:
        triggers = _triggers(document)

        assert "pull_request" not in triggers
        assert "push" not in triggers

    def test_the_two_jobs_split_by_event(self, document: dict[Any, Any]) -> None:
        jobs = _jobs(document)

        assert jobs["closure-manifest"]["if"] == "github.event_name != 'pull_request_target'"
        assert jobs["dispatch-closure"]["if"] == "github.event_name == 'pull_request_target'"


class TestPrivilege:
    def test_the_workflow_and_every_job_hold_only_contents_read(
        self, document: dict[Any, Any]
    ) -> None:
        assert document["permissions"] == {"contents": "read"}
        for name, job in _jobs(document).items():
            assert job["permissions"] == {"contents": "read"}, name

    def test_no_step_reads_a_secret_except_the_default_token_for_the_setup_action(
        self, document: dict[Any, Any]
    ) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")

        assert set(re.findall(r"secrets\.([A-Za-z_]+)", text)) == {"GITHUB_TOKEN"}

    def test_no_job_uses_an_environment_or_a_token_beyond_the_default(
        self, document: dict[Any, Any]
    ) -> None:
        for job in _jobs(document).values():
            assert "environment" not in job

    def test_every_action_is_pinned_to_a_commit_or_is_local(self, document: dict[Any, Any]) -> None:
        for job, body in _jobs(document).items():
            for step in body["steps"]:
                uses = step.get("uses")
                if uses is None or uses.startswith("./"):
                    continue
                assert _SHA_PIN.match(uses.split(" ")[0]), (job, uses)


class TestHeadIsData:
    def test_no_step_checks_the_pull_request_head_out(self, document: dict[Any, Any]) -> None:
        for job in _jobs(document):
            for step in _steps(document, job):
                if not str(step.get("uses", "")).startswith("actions/checkout@"):
                    continue
                inputs = step.get("with", {})
                assert "ref" not in inputs, (job, step.get("name"))
                assert "repository" not in inputs, (job, step.get("name"))
                assert "path" not in inputs, (job, step.get("name"))

    def test_the_head_is_named_by_the_events_sha_and_number_through_env_not_interpolation(
        self, document: dict[Any, Any]
    ) -> None:
        step = next(
            s
            for s in _steps(document, "dispatch-closure")
            if "verify_dispatch_closure" in str(s.get("run", ""))
        )

        assert step["env"] == {
            "PR_NUMBER": "${{ github.event.pull_request.number }}",
            "HEAD_SHA": "${{ github.event.pull_request.head.sha }}",
        }
        assert "${{" not in step["run"]
        assert '--head-sha "$HEAD_SHA"' in step["run"]
        assert '--pull-number "$PR_NUMBER"' in step["run"]

    def test_neither_checkout_persists_credentials(self, document: dict[Any, Any]) -> None:
        for job in _jobs(document):
            for step in _steps(document, job):
                if str(step.get("uses", "")).startswith("actions/checkout@"):
                    assert step["with"]["persist-credentials"] is False, (job, step.get("name"))

    def test_the_base_is_checked_out_before_the_local_setup_action_runs(
        self, document: dict[Any, Any]
    ) -> None:
        names = [s.get("name") for s in _steps(document, "dispatch-closure")]

        assert names.index("Check out the base") < names.index("Setup code environment")

    def test_no_step_runs_from_a_head_directory_or_sets_defaults(
        self, document: dict[Any, Any]
    ) -> None:
        assert "defaults" not in _jobs(document)["dispatch-closure"]
        for step in _steps(document, "dispatch-closure"):
            assert "working-directory" not in step, step.get("name")

    def test_the_tool_and_the_comparison_ref_are_the_base_checkout(
        self, document: dict[Any, Any]
    ) -> None:
        run = next(
            str(s["run"])
            for s in _steps(document, "dispatch-closure")
            if "verify_dispatch_closure" in str(s.get("run", ""))
        )

        assert "--tool-root ." in run
        assert "--base-ref HEAD" in run
        assert "scripts/ci/verify_dispatch_closure.py" in run


class TestManifestJob:
    def test_it_emits_then_reports_coverage_then_uploads(self, document: dict[Any, Any]) -> None:
        steps = _steps(document, "closure-manifest")
        runs = [str(s.get("run", "")) for s in steps if s.get("run")]

        assert 'closure_manifest.py --output "$RUNNER_TEMP/closure-manifest.json"' in runs[0]
        assert "--check-codeowners --advisory" in runs[1]
        assert steps[-1]["uses"].startswith("actions/upload-artifact@")

    def test_the_emit_step_is_not_advisory_so_an_unresolved_edge_fails_the_job(
        self, document: dict[Any, Any]
    ) -> None:
        steps = _steps(document, "closure-manifest")
        emit = next(s for s in steps if s.get("name") == "Emit the closure manifest")

        assert "--advisory" not in emit["run"]
        assert "continue-on-error" not in emit

    def test_the_coverage_and_upload_steps_survive_a_failed_emit(
        self, document: dict[Any, Any]
    ) -> None:
        steps = _steps(document, "closure-manifest")
        later = [
            s
            for s in steps
            if s.get("name")
            in {
                "Report CODEOWNERS coverage of the closure",
                "Upload the closure manifest",
            }
        ]

        assert len(later) == 2
        assert all("!cancelled()" in str(s["if"]) for s in later)

    def test_no_workflow_step_contains_branching_logic(self, document: dict[Any, Any]) -> None:
        for job in _jobs(document):
            for step in _steps(document, job):
                run = str(step.get("run", ""))
                assert not re.search(r"\b(if|for|while|case)\b", run), (job, step.get("name"))

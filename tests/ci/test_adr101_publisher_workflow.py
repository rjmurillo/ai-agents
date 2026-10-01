"""Structure tests for .github/workflows/adr101-publisher.yml.

The workflow holds the App credential, so its safety is structural. Every test
parses the YAML and asserts on the object graph (``testing.md`` MUST 9), never
on a substring of the text.

The properties, from the spike's "If the owner says go" section and ADR-101
requirement 2:

  * triggers: ``workflow_run`` only, never ``pull_request_target``, ``push`` or
    ``pull_request``;
  * no ``self-hosted`` runner, because a persistent pool carries candidate
    filesystem state into the job that holds the key (ADR-101);
  * the publish job names the environment, carries ``always()``, needs
    ``execute``, checks out no head, restores no cache, and runs no candidate
    code;
  * the execute job names no environment and references no secret;
  * the key reaches exactly one step;
  * no head-controlled string is read, and no event value is interpolated into
    a ``run:`` line;
  * every action is pinned to a 40-hex SHA, and permissions are least privilege;
  * the workflow is in no required context and no ruleset.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.ci.ruleset_required_contexts import REQUIRED_CONTEXTS

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "adr101-publisher.yml"
CODEOWNERS = REPO_ROOT / ".github" / "CODEOWNERS"
KEY = "ADR101_PUBLISHER_APP_PRIVATE_KEY"
ENVIRONMENT = "adr101-publisher"
HEAD_CONTROLLED = (
    "head_ref",
    "head_branch",
    "pull_request.title",
    "pull_request.body",
    "head.ref",
    "head.label",
    "workflow_run.head_commit",
    "workflow_run.display_title",
)
SHA_PIN = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


@pytest.fixture(scope="module")
def workflow() -> dict[Any, Any]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def jobs(workflow: dict[Any, Any]) -> dict[str, dict[str, Any]]:
    return workflow["jobs"]


def triggers(workflow: dict[Any, Any]) -> dict[str, Any]:
    # PyYAML reads the bare key `on` as the boolean True.
    found = workflow.get("on", workflow.get(True))
    assert isinstance(found, dict)
    return found


def steps_of(job: dict[str, Any]) -> list[dict[str, Any]]:
    return job["steps"]


def text_of(node: Any) -> str:
    return json.dumps(node, default=str)


class TestTriggersAndRunners:
    def test_the_only_trigger_is_workflow_run(self, workflow: dict[Any, Any]) -> None:
        assert set(triggers(workflow)) == {"workflow_run"}

    def test_it_follows_the_python_tests_workflow_on_completion(
        self, workflow: dict[Any, Any]
    ) -> None:
        trigger = triggers(workflow)["workflow_run"]

        assert trigger["workflows"] == ["Python Tests"]
        assert trigger["types"] == ["completed"]

    def test_python_tests_is_the_name_of_an_existing_workflow(self) -> None:
        names = {
            yaml.safe_load(path.read_text(encoding="utf-8")).get("name")
            for path in (REPO_ROOT / ".github" / "workflows").glob("*.yml")
        }

        assert "Python Tests" in names

    def test_no_job_uses_a_self_hosted_runner(self, jobs: dict[str, dict[str, Any]]) -> None:
        for name, job in jobs.items():
            labels = job["runs-on"] if isinstance(job["runs-on"], list) else [job["runs-on"]]
            assert "self-hosted" not in labels, name
            assert all(isinstance(label, str) and "$" not in label for label in labels), name

    def test_the_workflow_default_permissions_are_empty(self, workflow: dict[Any, Any]) -> None:
        assert workflow["permissions"] == {}

    def test_there_is_no_concurrency_group_a_fork_could_use_to_cancel_a_run(
        self, workflow: dict[Any, Any]
    ) -> None:
        assert "concurrency" not in workflow

    def test_the_job_set_is_exactly_gate_execute_publish(
        self, jobs: dict[str, dict[str, Any]]
    ) -> None:
        assert set(jobs) == {"gate", "execute", "publish"}


class TestPublishJob:
    def test_it_binds_the_environment_limited_to_main_by_the_owner(
        self, jobs: dict[str, dict[str, Any]]
    ) -> None:
        assert jobs["publish"]["environment"] == ENVIRONMENT

    def test_it_runs_on_every_terminal_state_of_execute(
        self, jobs: dict[str, dict[str, Any]]
    ) -> None:
        job = jobs["publish"]

        assert "execute" in job["needs"]
        assert "always()" in job["if"]

    def test_it_never_checks_out_the_head(self, jobs: dict[str, dict[str, Any]]) -> None:
        checkouts = [
            s
            for s in steps_of(jobs["publish"])
            if s.get("uses", "").startswith("actions/checkout@")
        ]

        assert len(checkouts) == 1
        options = checkouts[0].get("with", {})
        assert "ref" not in options
        assert "repository" not in options
        assert options["persist-credentials"] is False

    def test_it_restores_no_cache(self, jobs: dict[str, dict[str, Any]]) -> None:
        for step in steps_of(jobs["publish"]):
            uses = step.get("uses", "")
            assert not uses.startswith("actions/cache"), step
            assert not uses.startswith("astral-sh/setup-uv"), step
            assert "cache" not in step.get("with", {}), step

    def test_it_runs_only_the_checked_in_script_and_no_candidate_path(
        self, jobs: dict[str, dict[str, Any]]
    ) -> None:
        runs = [s["run"] for s in steps_of(jobs["publish"]) if "run" in s]

        assert runs == [
            "python3 scripts/ci/adr101_publisher.py preflight",
            "python3 scripts/ci/adr101_publisher.py publish",
        ]

    def test_permissions_are_the_least_the_reads_need(
        self, jobs: dict[str, dict[str, Any]]
    ) -> None:
        assert jobs["publish"]["permissions"] == {
            "contents": "read",
            "pull-requests": "read",
            "actions": "read",
        }

    def test_the_app_token_is_narrowed_to_checks_write(
        self, jobs: dict[str, dict[str, Any]]
    ) -> None:
        mint = [s for s in steps_of(jobs["publish"]) if s.get("id") == "app-token"][0]

        assert mint["uses"].startswith("actions/create-github-app-token@")
        assert mint["with"]["permission-checks"] == "write"
        permissions = [k for k in mint["with"] if k.startswith("permission-")]
        assert permissions == ["permission-checks"]
        # No continue-on-error: a refused mint fails the job, which is fail closed,
        # and the bypass allowlist would otherwise need an owner and expiry entry.
        assert "continue-on-error" not in mint

    def test_the_key_is_the_with_input_of_one_step_only(
        self, jobs: dict[str, dict[str, Any]]
    ) -> None:
        holders = []
        for step in steps_of(jobs["publish"]):
            for value in (step.get("with") or {}).values():
                if f"secrets.{KEY}" in str(value):
                    holders.append(step.get("id"))

        assert holders == ["app-token"]

    def test_elsewhere_the_key_appears_only_as_a_boolean_comparison(
        self, jobs: dict[str, dict[str, Any]]
    ) -> None:
        allowed = f"${{{{ secrets.{KEY} != '' }}}}"
        for step in steps_of(jobs["publish"]):
            for name, value in (step.get("env") or {}).items():
                if f"secrets.{KEY}" in str(value):
                    assert name == "ADR101_HAS_KEY"
                    assert str(value) == allowed

    def test_the_publish_step_runs_after_a_refused_mint(
        self, jobs: dict[str, dict[str, Any]]
    ) -> None:
        publish = [s for s in steps_of(jobs["publish"]) if s.get("name") == "Publish"][0]

        assert "always()" in publish["if"]

    def test_the_token_reaches_only_the_publish_step(
        self, jobs: dict[str, dict[str, Any]]
    ) -> None:
        holders = [
            s.get("name")
            for s in steps_of(jobs["publish"])
            if "steps.app-token.outputs.token" in text_of(s.get("env", {}))
        ]

        assert holders == ["Publish"]


class TestExecuteAndGateJobs:
    def test_execute_names_no_environment_and_references_no_secret(
        self, jobs: dict[str, dict[str, Any]]
    ) -> None:
        job = jobs["execute"]

        assert "environment" not in job
        assert "secrets." not in text_of(job)
        assert KEY not in text_of(job)

    def test_gate_references_no_secret_and_has_no_environment(
        self, jobs: dict[str, dict[str, Any]]
    ) -> None:
        assert "environment" not in jobs["gate"]
        assert "secrets." not in text_of(jobs["gate"])

    def test_execute_has_contents_read_and_nothing_else(
        self, jobs: dict[str, dict[str, Any]]
    ) -> None:
        assert jobs["execute"]["permissions"] == {"contents": "read"}

    def test_execute_does_not_persist_credentials_or_restore_a_cache(
        self, jobs: dict[str, dict[str, Any]]
    ) -> None:
        for step in steps_of(jobs["execute"]):
            uses = step.get("uses", "")
            options = step.get("with", {})
            assert not uses.startswith("actions/cache"), step
            if uses.startswith("actions/checkout@"):
                assert options["persist-credentials"] is False
                assert "ref" not in options
            if uses.startswith("astral-sh/setup-uv@"):
                assert options["enable-cache"] is False

    def test_execute_receives_no_token_in_its_environment(
        self, jobs: dict[str, dict[str, Any]]
    ) -> None:
        for step in steps_of(jobs["execute"]):
            for name in step.get("env", {}):
                assert "TOKEN" not in name, name

    def test_execute_starts_only_when_the_gate_says_enabled(
        self, jobs: dict[str, dict[str, Any]]
    ) -> None:
        assert jobs["execute"]["needs"] == "gate"
        assert "needs.gate.outputs.enabled == 'true'" in jobs["execute"]["if"]

    def test_the_gate_is_the_only_reader_of_the_flag_for_job_starts(
        self, jobs: dict[str, dict[str, Any]]
    ) -> None:
        assert jobs["gate"]["outputs"] == {"enabled": "${{ steps.gate.outputs.enabled }}"}
        assert "needs.gate.outputs.enabled == 'true'" in jobs["publish"]["if"]


class TestNoHeadControlledInput:
    def test_no_head_controlled_string_is_read_anywhere(self, workflow: dict[Any, Any]) -> None:
        rendered = text_of(workflow)
        for name in HEAD_CONTROLLED:
            assert name not in rendered, name

    def test_no_run_line_interpolates_an_expression(
        self, jobs: dict[str, dict[str, Any]]
    ) -> None:
        for name, job in jobs.items():
            for step in steps_of(job):
                assert "${{" not in step.get("run", ""), (name, step)

    def test_every_event_value_used_is_a_sha_or_a_numeric_id(
        self, jobs: dict[str, dict[str, Any]]
    ) -> None:
        allowed = {
            "github.event.workflow_run.head_sha",
            "github.event.workflow_run.event",
            "github.event.workflow_run.id",
            "github.event.workflow_run.pull_requests[0].number",
        }
        found = set(re.findall(r"github\.event\.[A-Za-z0-9_.\[\]]+", text_of(jobs)))

        assert found <= allowed, found - allowed

    def test_the_workflow_never_calls_the_fork_or_head_repository(
        self, workflow: dict[Any, Any]
    ) -> None:
        assert "head_repository" not in text_of(workflow)

    def test_every_run_step_calls_the_checked_in_script_and_nothing_else(
        self, jobs: dict[str, dict[str, Any]]
    ) -> None:
        pattern = re.compile(
            r"^python3 scripts/ci/adr101_publisher\.py (gate|preflight|execute|publish)$"
        )
        for job in jobs.values():
            for step in steps_of(job):
                if "run" in step:
                    assert pattern.match(step["run"]), step["run"]


class TestPinningAndScope:
    def test_every_action_is_pinned_to_a_40_hex_sha(self, jobs: dict[str, dict[str, Any]]) -> None:
        uses = [s["uses"] for job in jobs.values() for s in steps_of(job) if "uses" in s]

        assert uses
        for ref in uses:
            assert SHA_PIN.match(ref), ref

    def test_every_pin_carries_a_version_comment(self) -> None:
        for line in WORKFLOW.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith(("uses:", "- uses:")):
                assert re.search(r"@[0-9a-f]{40} # v\d", line), line

    def test_no_local_composite_action_is_used(self, jobs: dict[str, dict[str, Any]]) -> None:
        # A composite under .github/actions/ restores caches. This job holds a key.
        for job in jobs.values():
            for step in steps_of(job):
                assert not step.get("uses", "").startswith("./"), step

    def test_the_check_and_job_names_are_not_required_contexts(
        self, jobs: dict[str, dict[str, Any]]
    ) -> None:
        from scripts.ci.adr101_publisher_inputs import CHECK_NAME

        names = {job["name"] for job in jobs.values()} | {CHECK_NAME}

        assert names.isdisjoint(REQUIRED_CONTEXTS)

    def test_the_workflow_is_not_named_in_the_ruleset_baseline(self) -> None:
        path = REPO_ROOT / "scripts" / "validation" / "ruleset_params_baseline.json"
        baseline = path.read_text(encoding="utf-8")

        assert "ADR-101 Published Result" not in baseline
        assert "adr101" not in baseline.lower()


class TestOwnership:
    @pytest.mark.parametrize(
        "path",
        [
            "/.github/workflows/adr101-publisher.yml",
            "/scripts/ci/adr101_publisher.py",
            "/scripts/ci/adr101_publisher_execute.py",
            "/scripts/ci/adr101_publisher_github.py",
            "/scripts/ci/adr101_publisher_inputs.py",
        ],
    )
    def test_a_code_owner_entry_covers_each_file(self, path: str) -> None:
        entries = {
            line.split()[0]
            for line in CODEOWNERS.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        }

        assert path in entries

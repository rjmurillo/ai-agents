"""Wiring tests for .github/workflows/publish-wiki.yml (issue #7202).

The workflow is a thin caller (ADR-006). These tests parse the YAML and assert on
the object graph, so a deleted step, a floating action tag, or a credential in
the dry-run job fails here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "publish-wiki.yml"
SHA_PIN = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


@pytest.fixture(scope="module")
def doc() -> dict:
    loaded = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    # PyYAML reads the bare key `on` as boolean True.
    loaded["on"] = loaded.pop(True)
    return loaded


@pytest.fixture(scope="module")
def dry(doc: dict) -> dict:
    return doc["jobs"]["dry-run"]


@pytest.fixture(scope="module")
def publish(doc: dict) -> dict:
    return doc["jobs"]["publish"]


def runs(job: dict) -> list[dict]:
    return [s for s in job["steps"] if "run" in s]


def test_only_the_two_expected_jobs_exist(doc: dict) -> None:
    assert sorted(doc["jobs"]) == ["dry-run", "publish"]


def test_runs_on_main_pushes_that_touch_the_training_tree(doc: dict) -> None:
    push = doc["on"]["push"]
    assert push["branches"] == ["main"]
    assert "docs/training/**" in push["paths"]
    assert "scripts/ci/publish_wiki.py" in push["paths"]
    assert "scripts/ci/_wiki_links.py" in push["paths"]


def test_manual_run_defaults_to_dry_run(doc: dict) -> None:
    inputs = doc["on"]["workflow_dispatch"]["inputs"]["dry_run"]
    assert inputs["type"] == "boolean"
    assert inputs["default"] is True


def test_every_action_in_every_job_is_pinned_to_a_full_sha(doc: dict) -> None:
    uses = [s["uses"] for j in doc["jobs"].values() for s in j["steps"] if "uses" in s]
    assert len(uses) == 4
    assert all(SHA_PIN.match(u) for u in uses), uses


def test_no_permissions_at_workflow_level(doc: dict) -> None:
    assert doc["permissions"] == {}


def test_dry_run_job_holds_no_credential_and_no_environment(dry: dict) -> None:
    assert dry["permissions"] == {"contents": "read"}
    assert "environment" not in dry
    for step in dry["steps"]:
        assert "env" not in step
        assert "secrets." not in str(step)


def test_dry_run_job_runs_only_on_a_dry_manual_dispatch(dry: dict) -> None:
    assert dry["if"] == "${{ github.event_name == 'workflow_dispatch' && inputs.dry_run }}"
    assert [s["run"] for s in runs(dry)] == ["python3 scripts/ci/publish_wiki.py --dry-run"]


def test_publish_job_runs_on_push_or_a_non_dry_dispatch_from_main(publish: dict) -> None:
    assert publish["if"] == (
        "${{ github.event_name == 'push' || (!inputs.dry_run && github.ref == 'refs/heads/main') }}"
    )


def test_publish_job_names_the_environment_that_scopes_the_secret(publish: dict) -> None:
    assert publish["environment"] == "wiki-publish"
    assert publish["permissions"] == {"contents": "write"}


def test_publish_step_is_the_only_one_with_the_credential(publish: dict) -> None:
    step = runs(publish)[0]
    assert step["run"] == "python3 scripts/ci/publish_wiki.py"
    assert step["env"] == {"WIKI_TOKEN": "${{ secrets.WIKI_PUSH_TOKEN || github.token }}"}
    assert len(runs(publish)) == 1


def test_checkout_never_persists_credentials(doc: dict) -> None:
    checkouts = [
        s for j in doc["jobs"].values() for s in j["steps"] if "checkout@" in s.get("uses", "")
    ]
    assert len(checkouts) == 2
    assert all(c["with"]["persist-credentials"] is False for c in checkouts)


def test_concurrency_is_per_ref_and_queues(doc: dict) -> None:
    assert doc["concurrency"] == {
        "group": "publish-wiki-${{ github.ref }}",
        "cancel-in-progress": False,
    }

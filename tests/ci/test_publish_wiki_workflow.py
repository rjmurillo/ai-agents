"""Wiring tests for .github/workflows/publish-wiki.yml (issue #7202).

The workflow is a thin caller (ADR-006). These tests parse the YAML and assert on
the object graph, so a deleted step or a floating action tag fails here.
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
def steps(doc: dict) -> list[dict]:
    return doc["jobs"]["publish"]["steps"]


def test_runs_on_main_pushes_that_touch_the_training_tree(doc: dict) -> None:
    push = doc["on"]["push"]
    assert push["branches"] == ["main"]
    assert "docs/training/**" in push["paths"]
    assert "scripts/ci/publish_wiki.py" in push["paths"]


def test_manual_run_defaults_to_dry_run(doc: dict) -> None:
    inputs = doc["on"]["workflow_dispatch"]["inputs"]["dry_run"]
    assert inputs["type"] == "boolean"
    assert inputs["default"] is True


def test_every_action_is_pinned_to_a_full_sha(steps: list[dict]) -> None:
    uses = [s["uses"] for s in steps if "uses" in s]
    assert uses, "expected at least one action step"
    assert all(SHA_PIN.match(u) for u in uses), uses


def test_permissions_are_minimal_and_allow_the_wiki_push(doc: dict) -> None:
    assert doc["permissions"] == {"contents": "write"}


def test_concurrent_publishes_queue_instead_of_cancelling(doc: dict) -> None:
    assert doc["concurrency"] == {"group": "publish-wiki", "cancel-in-progress": False}


def test_single_run_step_calls_the_script_and_holds_no_logic(steps: list[dict]) -> None:
    runs = [s["run"] for s in steps if "run" in s]
    assert runs == ["python3 scripts/ci/publish_wiki.py"]


def test_job_names_the_environment_that_scopes_the_secret(doc: dict) -> None:
    assert doc["jobs"]["publish"]["environment"] == "wiki-publish"


def test_credential_prefers_the_named_secret_then_falls_back(steps: list[dict]) -> None:
    env = next(s["env"] for s in steps if "run" in s)
    assert env["WIKI_TOKEN"] == "${{ secrets.WIKI_PUSH_TOKEN || github.token }}"
    assert "dry_run" in env["WIKI_DRY_RUN"]


def test_checkout_does_not_persist_credentials(steps: list[dict]) -> None:
    checkout = next(s for s in steps if s.get("uses", "").startswith("actions/checkout@"))
    assert checkout["with"]["persist-credentials"] is False

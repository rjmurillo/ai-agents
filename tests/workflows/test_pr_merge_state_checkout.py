"""The pr-merge-state job keeps no git credential in the workspace (issue #6506)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "pr-merge-state.yml"


def _checkout_steps() -> list[dict[str, Any]]:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["pr-merge-state"]["steps"]
    return [s for s in steps if str(s.get("uses", "")).startswith("actions/checkout@")]


def test_the_job_checks_out_the_repository_once() -> None:
    assert len(_checkout_steps()) == 1


def test_every_checkout_drops_the_token_from_git_config() -> None:
    """Branch-controlled code runs after checkout, so it must not find a token."""
    for step in _checkout_steps():
        assert step.get("with", {}).get("persist-credentials") is False, step


def test_the_checkout_stays_pinned_to_a_full_commit_sha() -> None:
    for step in _checkout_steps():
        _, _, ref = step["uses"].partition("@")
        assert len(ref) == 40
        assert all(c in "0123456789abcdef" for c in ref)

"""Contract test: Validate Spec Coverage grades a PR with the base branch's scripts.

Issue #6506, review-gates-14. A PR must not be able to edit the scripts that
grade its own spec, so ai-spec-validation.yml checks the base SHA out into a
separate ``trusted-base`` path and runs every grading script from there.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

_VALIDATION = (
    Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ai-spec-validation.yml"
)
_SCRIPTS = ("spec_coverage_scope", "spec_extract_refs", "spec_coverage_verdict")
_TRUSTED_PATH = "trusted-base"


@pytest.fixture(scope="module")
def steps() -> list[dict[str, Any]]:
    workflow = yaml.safe_load(_VALIDATION.read_text(encoding="utf-8"))
    job_steps: list[dict[str, Any]] = workflow["jobs"]["validate-spec"]["steps"]
    return job_steps


def _is_base_checkout(step: dict[str, Any]) -> bool:
    return bool(step.get("with", {}).get("path") == _TRUSTED_PATH)


@pytest.fixture(scope="module")
def base_checkout(steps: list[dict[str, Any]]) -> dict[str, Any]:
    return next(s for s in steps if _is_base_checkout(s))


def test_base_checkout_is_a_separate_path_pinned_to_the_base_sha(
    base_checkout: dict[str, Any],
) -> None:
    assert base_checkout["with"]["ref"].startswith("${{ github.event.pull_request.base.sha")
    assert base_checkout["with"]["persist-credentials"] is False
    assert "@" in base_checkout["uses"] and len(base_checkout["uses"].split("@")[1]) == 40


def test_base_checkout_runs_before_the_first_grading_script(steps: list[dict[str, Any]]) -> None:
    base = next(i for i, s in enumerate(steps) if _is_base_checkout(s))
    first = next(i for i, s in enumerate(steps) if "scripts/ci/spec_" in str(s.get("run")))

    assert base < first


def test_sparse_checkout_carries_every_dir_the_scripts_import_or_spawn(
    base_checkout: dict[str, Any],
) -> None:
    assert set(base_checkout["with"]["sparse-checkout"].split()) == {
        "scripts/ci",
        "scripts/external_signals",
        ".github/scripts",
    }


@pytest.mark.parametrize("name", _SCRIPTS)
def test_each_grading_script_runs_from_the_trusted_path(
    steps: list[dict[str, Any]], name: str
) -> None:
    runs = [str(s.get("run")) for s in steps if name in str(s.get("run"))]

    assert runs == [f"python3 {_TRUSTED_PATH}/scripts/ci/{name}.py"]


def test_no_step_runs_a_spec_script_from_the_pr_tree() -> None:
    text = _VALIDATION.read_text(encoding="utf-8")

    for name in _SCRIPTS:
        assert f"python3 scripts/ci/{name}.py" not in text

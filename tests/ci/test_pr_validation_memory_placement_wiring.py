"""The memory-placement check is wired into the PR validation workflow.

Issue #5828: the check ran only at pre-commit, so every route that skips local
hooks reached main unchecked. These tests parse the YAML (never substring-match
the file, per .claude/rules/testing.md MUST 9) and fail when the step is
removed, renamed, moved out of ``validate-pr``, gated behind a condition, loses
its base-ref fetch, or stops passing ``--changed-since`` and ``--ci``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pr-validation.yml"
LEFTHOOK = REPO_ROOT / "lefthook.yml"
STEP_NAME = "Run memory-placement check"
PRECEDING_STEP = "Run memory-index token ratchet"
SCRIPT = "scripts/validation/check_memory_placement.py"


@pytest.fixture(scope="module")
def steps() -> list[dict]:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return workflow["jobs"]["validate-pr"]["steps"]


@pytest.fixture(scope="module")
def step(steps: list[dict]) -> dict:
    matches = [s for s in steps if s.get("name") == STEP_NAME]
    assert len(matches) == 1, f"expected exactly one {STEP_NAME!r} step, found {len(matches)}"
    return matches[0]


def _command_lines(step: dict) -> list[str]:
    return [line.strip() for line in step["run"].splitlines() if line.strip()]


def _code_lines(step: dict) -> list[str]:
    return [line for line in _command_lines(step) if not line.startswith("#")]


def test_step_runs_in_the_validate_pr_job(steps):
    assert any(s.get("name") == STEP_NAME for s in steps)


def test_step_follows_the_memory_index_token_ratchet(steps):
    names = [s.get("name") for s in steps]

    assert names.index(STEP_NAME) == names.index(PRECEDING_STEP) + 1


def test_step_is_unconditional(step):
    assert "if" not in step, "a condition lets a PR skip the only server-side leg"
    assert "continue-on-error" not in step


def test_run_block_is_the_fetch_and_the_one_command(step):
    code = _code_lines(step)

    assert len(code) == 2, f"ADR-006: the run block holds a fetch and one command, got {code}"
    assert code[0] == 'git fetch origin "$BASE_REF"'
    assert code[1].startswith("uv run --frozen python3 " + SCRIPT)


def test_command_checks_changes_since_the_fetched_base_and_fails_the_job(step):
    command = _code_lines(step)[1]

    assert re.search(r"(^|\s)--ci(\s|$)", command)
    assert re.search(r"--changed-since FETCH_HEAD(\s|$)", command)


def test_base_ref_comes_from_the_event_with_a_default_branch_fallback(step):
    base_ref = step["env"]["BASE_REF"]

    assert "github.base_ref" in base_ref
    assert "github.event.repository.default_branch" in base_ref


def test_workflow_does_not_interpolate_event_data_into_the_run_block(step):
    assert "${{" not in step["run"]


def test_checked_in_script_exists():
    assert (REPO_ROOT / SCRIPT).is_file()


def test_pre_commit_leg_stays_alongside_the_server_side_leg():
    lefthook = yaml.safe_load(LEFTHOOK.read_text(encoding="utf-8"))
    commands = _collect_run_commands(lefthook)

    assert any(SCRIPT in run and "--staged" in run for run in commands)


def _collect_run_commands(node: object) -> list[str]:
    if isinstance(node, dict):
        found = [node["run"]] if isinstance(node.get("run"), str) else []
        for value in node.values():
            found.extend(_collect_run_commands(value))
        return found
    if isinstance(node, list):
        return [run for item in node for run in _collect_run_commands(item)]
    return []

"""Workflow concurrency must not cancel post-merge validation on main."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"

MAIN_SAFE_CANCEL = "${{ github.ref != 'refs/heads/main' }}"

PROTECTED_WORKFLOWS = frozenset(
    {
        "cli-smoke.yml",
        "codeql-analysis.yml",
        "instruction-budget.yml",
        "passive-context-budget.yml",
        "pytest.yml",
        "skill-passive-compliance.yml",
        "skillbook-validation.yml",
        "validate-generated-agents.yml",
        "yaml-lint.yml",
    }
)


def _workflow_files() -> list[Path]:
    return sorted(WORKFLOW_DIR.glob("*.yml")) + sorted(WORKFLOW_DIR.glob("*.yaml"))


def _load_workflow(path: Path) -> dict[Any, Any] | None:
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:  # pragma: no cover - actionlint owns malformed YAML
        return None
    return loaded if isinstance(loaded, dict) else None


def _triggers_main_push(workflow: dict[Any, Any]) -> bool:
    on = workflow.get(True, workflow.get("on"))
    if isinstance(on, str):
        return on == "push"
    if isinstance(on, list):
        return "push" in on
    if not isinstance(on, dict) or "push" not in on:
        return False

    push = on["push"]
    if not isinstance(push, dict):
        return True
    branches = push.get("branches")
    if branches is None:
        return True
    return isinstance(branches, list) and "main" in branches


def _main_push_cancel_error(name: str, workflow: dict[Any, Any]) -> str | None:
    if not _triggers_main_push(workflow):
        return None
    concurrency = workflow.get("concurrency")
    if not isinstance(concurrency, dict):
        return None
    cancel = concurrency.get("cancel-in-progress")
    if cancel in (None, False):
        return None
    if cancel == MAIN_SAFE_CANCEL:
        return None
    return (
        f"{name} cancels an older main push run. Use {MAIN_SAFE_CANCEL!r} "
        "so post-merge validation cannot be cancelled by the next merge."
    )


def test_push_workflows_do_not_cancel_main_verification() -> None:
    errors: list[str] = []
    for path in _workflow_files():
        workflow = _load_workflow(path)
        if workflow is None:
            pytest.skip(f"{path.name} is not a parseable workflow mapping")
        error = _main_push_cancel_error(path.name, workflow)
        if error:
            errors.append(error)

    assert errors == []


def test_detector_flags_true_cancel_in_progress_on_push() -> None:
    workflow = {
        "on": {"push": {"branches": ["main"]}},
        "concurrency": {"cancel-in-progress": True},
    }

    assert _main_push_cancel_error("bad.yml", workflow) is not None


def test_detector_accepts_main_safe_cancel_expression() -> None:
    workflow = {
        "on": {"push": {"branches": ["main"]}},
        "concurrency": {"cancel-in-progress": MAIN_SAFE_CANCEL},
    }

    assert _main_push_cancel_error("safe.yml", workflow) is None


def test_detector_ignores_pull_request_only_workflow() -> None:
    workflow = {
        "on": {"pull_request": {"branches": ["main"]}},
        "concurrency": {"cancel-in-progress": True},
    }

    assert _main_push_cancel_error("pr-only.yml", workflow) is None


def test_detector_ignores_push_workflow_without_main_branch() -> None:
    workflow = {
        "on": {"push": {"branches": ["release/**"]}},
        "concurrency": {"cancel-in-progress": True},
    }

    assert _main_push_cancel_error("release.yml", workflow) is None


def test_all_known_post_merge_workflows_are_guarded() -> None:
    missing = sorted(
        name for name in PROTECTED_WORKFLOWS if not (WORKFLOW_DIR / name).is_file()
    )
    assert missing == []

    unguarded = []
    for name in PROTECTED_WORKFLOWS:
        workflow = _load_workflow(WORKFLOW_DIR / name)
        assert workflow is not None, name
        concurrency = workflow.get("concurrency")
        assert isinstance(concurrency, dict), name
        if concurrency.get("cancel-in-progress") != MAIN_SAFE_CANCEL:
            unguarded.append(name)

    assert unguarded == []

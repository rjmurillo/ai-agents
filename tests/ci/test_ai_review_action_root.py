"""The ai-review action and its scripts anchor on their own tree, not the workspace.

Counterpart of ``test_pr_maintenance_trusted_code.py``: that module pins the
workflow wiring, this one pins the action and script behavior that makes a
``.trusted-helper`` caller safe.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ACTION_DIR = REPO_ROOT / ".github" / "actions" / "ai-review"
ACTION = ACTION_DIR / "action.yml"


def _load_action() -> dict[str, Any]:
    return yaml.safe_load(ACTION.read_text(encoding="utf-8"))


def test_action_root_is_three_levels_above_the_action_directory() -> None:
    assert (ACTION_DIR / ".." / ".." / "..").resolve() == REPO_ROOT


def test_action_never_reads_scripts_from_the_workspace() -> None:
    source = ACTION.read_text(encoding="utf-8")
    assert "GITHUB_WORKSPACE" not in source
    for step in _load_action()["runs"]["steps"]:
        run = step.get("run", "")
        if "scripts/" not in run:
            continue
        assert '"$AI_REVIEW_ROOT/scripts/ci/' in run, step["name"]
        assert step["env"]["AI_REVIEW_ROOT"] == "${{ github.action_path }}/../../..", step["name"]


def test_action_resolves_dependencies_from_the_action_root() -> None:
    steps = _load_action()["runs"]["steps"]
    uv_runs = [s["run"] for s in steps if "uv run" in s.get("run", "")]
    assert len(uv_runs) == 1
    assert 'uv run --frozen --project "$AI_REVIEW_ROOT" python' in uv_runs[0]


def test_default_prompt_and_agent_definitions_are_anchored_to_the_repository_root() -> None:
    from scripts.ci import invoke_claude_review, load_ai_review_prompt

    assert load_ai_review_prompt.DEFAULT_PROMPT_PATH.is_absolute()
    assert load_ai_review_prompt.DEFAULT_PROMPT_PATH.is_relative_to(REPO_ROOT)
    assert invoke_claude_review.AGENTS_DIR == REPO_ROOT / ".claude" / "agents"


def test_conflict_resolver_path_is_anchored_to_the_script() -> None:
    from scripts.ci import run_pr_conflict_resolver

    resolver = Path(run_pr_conflict_resolver._RESOLVER)
    assert resolver.is_absolute()
    assert resolver.is_file()
    assert resolver.is_relative_to(REPO_ROOT)


def test_comment_processing_script_does_not_trust_github_workspace() -> None:
    script = REPO_ROOT / ".claude/skills/github/scripts/pr/invoke_pr_comment_processing.py"
    assert 'environ.get("GITHUB_WORKSPACE")' not in script.read_text(encoding="utf-8")

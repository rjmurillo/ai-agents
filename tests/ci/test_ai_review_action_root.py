"""The ai-review action and its scripts anchor on their own tree, not the workspace.

Counterpart of the deleted ``test_pr_maintenance_trusted_code.py``: that module
pinned the workflow wiring, this one pins the action and script behavior that
makes a ``.trusted-helper`` caller safe.
"""

from __future__ import annotations

import os
import subprocess
import sys
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


_COMMENT_SCRIPT = REPO_ROOT / ".claude/skills/github/scripts/pr/invoke_pr_comment_processing.py"
_BOOTSTRAP_DIR = REPO_ROOT / ".claude/skills/github/scripts"


def _plant_workspace_lib(tmp_path: Path) -> tuple[Path, Path]:
    """Create a workspace whose github_core records its import, then raises."""
    workspace = tmp_path / "workspace"
    package = workspace / ".claude" / "lib" / "github_core"
    package.mkdir(parents=True)
    marker = tmp_path / "planted-lib-imported"
    package.joinpath("__init__.py").write_text(
        "import os\n"
        "from pathlib import Path\n"
        'Path(os.environ["PLANTED_LIB_MARKER"]).write_text("imported", encoding="utf-8")\n'
        'raise RuntimeError("planted workspace lib was imported")\n',
        encoding="utf-8",
    )
    assert not marker.exists()
    return workspace, marker


def _planted_env(workspace: Path, marker: Path) -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {"COPILOT_PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT", "PYTHONPATH"}
    }
    env.update(GITHUB_WORKSPACE=str(workspace), PLANTED_LIB_MARKER=str(marker))
    return env


def _run(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_comment_processing_script_never_imports_a_lib_planted_in_github_workspace(
    tmp_path: Path,
) -> None:
    """pr-maintenance runs the script from a trusted copy; the workspace may hold a PR head.

    The command comes from the same builder execute_ai_review_post_script.py uses, with
    the verdict FAIL so the script returns before any GitHub call once its imports resolve.
    """
    from scripts.ci.execute_ai_review_post_script import build_command

    workspace, marker = _plant_workspace_lib(tmp_path)
    env = _planted_env(workspace, marker)
    env.update(PR_NUMBER="1", AI_VERDICT="FAIL", AI_FINDINGS="{}")
    argv = build_command(_COMMENT_SCRIPT, env)
    argv[0] = sys.executable

    result = _run(argv, env)

    assert result.returncode == 0, result.stderr
    assert "skipping comment processing" in result.stderr
    assert not marker.exists(), "script imported github_core from GITHUB_WORKSPACE"


def test_planted_workspace_lib_is_detected_when_resolution_opts_into_the_workspace(
    tmp_path: Path,
) -> None:
    """Negative control: the same plant fires when ensure_plugin_paths opts into the workspace."""
    workspace, marker = _plant_workspace_lib(tmp_path)
    code = (
        "import sys\n"
        f"sys.path.insert(0, {str(_BOOTSTRAP_DIR)!r})\n"
        "from skill_bootstrap import ensure_plugin_paths\n"
        f"ensure_plugin_paths({str(_COMMENT_SCRIPT)!r}, ('.claude', 'lib'))\n"
        "import github_core\n"
    )

    result = _run([sys.executable, "-c", code], _planted_env(workspace, marker))

    assert result.returncode != 0
    assert "planted workspace lib was imported" in result.stderr
    assert marker.read_text(encoding="utf-8") == "imported"

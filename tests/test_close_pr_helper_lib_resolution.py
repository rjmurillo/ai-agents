"""The close_pr helper modules find lib the same way close_pr.py does.

close_pr.py resolves lib from the plugin root, then GITHUB_WORKSPACE, then a
path relative to the script. Its helpers must follow the same order. Otherwise
a run that finds lib only through GITHUB_WORKSPACE imports close_pr.py and then
exits 2 when a helper loads.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PR_SCRIPTS = REPO_ROOT / "src" / "claude" / "skills" / "github" / "scripts" / "pr"
LIB_DIR = REPO_ROOT / "src" / "claude" / "lib"

HELPERS = ("close_pr_steps.py", "pr_comment_lookup.py")


def _copy_out_of_tree(tmp_path: Path) -> Path:
    """Copy the helpers to a folder with no lib four levels up."""
    scripts = tmp_path / "a" / "b" / "c" / "d" / "pr"
    scripts.mkdir(parents=True)
    for name in (*HELPERS, "pr_comment_dedupe.py"):
        shutil.copy2(PR_SCRIPTS / name, scripts / name)
    # The helpers resolve lib through the skill's shared bootstrap one level up.
    shutil.copy2(PR_SCRIPTS.parent / "skill_bootstrap.py", scripts.parent / "skill_bootstrap.py")
    assert not (scripts / ".." / ".." / ".." / ".." / "lib").resolve().exists()
    return scripts


def _import(scripts: Path, module: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    code = f"import sys; sys.path.insert(0, {str(scripts)!r}); import {module}"
    return subprocess.run(
        [sys.executable, "-I", "-c", code],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=60,
        check=False,
    )


def _base_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.endswith("PLUGIN_ROOT")}
    env.pop("GITHUB_WORKSPACE", None)
    return env


@pytest.mark.parametrize("helper", HELPERS)
def test_helper_finds_lib_through_github_workspace(tmp_path: Path, helper: str) -> None:
    scripts = _copy_out_of_tree(tmp_path)
    workspace = tmp_path / "ws"
    (workspace / ".claude").mkdir(parents=True)
    shutil.copytree(LIB_DIR, workspace / ".claude" / "lib")
    env = _base_env() | {"GITHUB_WORKSPACE": str(workspace)}

    result = _import(scripts, helper.removesuffix(".py"), env)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("helper", HELPERS)
def test_helper_exits_2_when_no_lib_is_found(tmp_path: Path, helper: str) -> None:
    scripts = _copy_out_of_tree(tmp_path)

    result = _import(scripts, helper.removesuffix(".py"), _base_env())

    assert result.returncode == 2
    assert "Plugin lib directory not found" in result.stderr

"""Regression tests for validation scripts invoked directly by file path."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATION_SCRIPTS_WITH_LOCAL_IMPORTS = (
    "check_skill_portability.py",
    "git_hook_policy.py",
    "instruction_budget.py",
    "passive_context_budget.py",
    "skill_frontmatter.py",
)


def _dependency_only_pythonpath() -> str:
    """Return import paths for third-party deps without the repo root editable hook."""
    repo_root = REPO_ROOT.resolve()
    paths: list[str] = []
    for entry in sys.path:
        if not entry or entry.startswith("__editable__."):
            continue
        resolved = Path(entry).resolve()
        if "site-packages" in resolved.parts:
            paths.append(str(resolved))
            continue
        if resolved == repo_root or repo_root in resolved.parents:
            continue
    return os.pathsep.join(dict.fromkeys(paths))


@pytest.mark.parametrize("script_name", VALIDATION_SCRIPTS_WITH_LOCAL_IMPORTS)
def test_validation_script_runs_by_path_without_editable_repo_path(
    script_name: str,
    tmp_path: Path,
) -> None:
    """Direct file invocation must not rely on cwd, -m, uv, or editable .pth files."""
    script_path = REPO_ROOT / "scripts" / "validation" / script_name
    env = os.environ.copy()
    env["PYTHONPATH"] = _dependency_only_pythonpath()

    result = subprocess.run(
        [sys.executable, "-S", str(script_path), "--help"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )

    assert result.returncode == 0, (
        f"{script_name} must run by file path under python -S from {tmp_path}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    assert "ModuleNotFoundError" not in result.stderr

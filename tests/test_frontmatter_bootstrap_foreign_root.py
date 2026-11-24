"""A plugin root that names a different plugin must not break the shared parser import.

Skill scripts that read frontmatter add their plugin ``lib`` to ``sys.path`` and
import ``hook_utilities.frontmatter_block``. Repo gates such as
``check_skill_artifact_flow.py`` load some of those scripts by path. When
``CLAUDE_PLUGIN_ROOT`` names another plugin whose ``lib`` lacks the parser, the
bootstrap falls back to the script's own plugin ``lib``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run(script: str, plugin_root: Path | None) -> subprocess.CompletedProcess[str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("CLAUDE_PLUGIN_ROOT", "COPILOT_PLUGIN_ROOT")
    }
    if plugin_root is not None:
        env["CLAUDE_PLUGIN_ROOT"] = str(plugin_root)
    return subprocess.run(
        [sys.executable, script],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )


@pytest.mark.parametrize(
    "script",
    ["scripts/validation/check_skill_artifact_flow.py", "scripts/validation/skill_size.py"],
)
def test_gate_passes_when_plugin_root_names_a_foreign_plugin(tmp_path: Path, script: str) -> None:
    foreign = tmp_path / "foreign-plugin"
    (foreign / "lib").mkdir(parents=True)

    baseline = _run(script, None)
    result = _run(script, foreign)

    assert "hook_utilities" not in result.stderr, result.stderr
    assert result.returncode == baseline.returncode, result.stderr

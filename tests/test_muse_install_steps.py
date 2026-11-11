"""Replay the Muse install steps from src/muse/README.md into a scratch HOME (issue #7278).

The README copies skills into ``~/workspace/custom-skills/``. Skill scripts
resolve shared packages from ``lib/`` one level above that directory, so the
install must also place ``lib/`` at ``~/workspace/lib/``. The test runs the
documented bash blocks verbatim, then runs one lib-importing skill script.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "src" / "muse" / "README.md"
SKILL_SCRIPT = Path("workspace/custom-skills/github/scripts/pr/get_pr_checks.py")
LIB_MISSING_MESSAGE = "Plugin lib directory not found"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash is required")


def _install_section_blocks() -> list[str]:
    text = README.read_text(encoding="utf-8")
    section = text.split("## Install into Muse", 1)[1]
    return re.findall(r"```bash\n(.*?)```", section, flags=re.DOTALL)


def _scratch_env(home: Path) -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {"COPILOT_PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT"}
    }
    env["HOME"] = str(home)
    return env


def _bash(script: str, home: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-euo", "pipefail", "-c", script],
        cwd=REPO_ROOT,
        env=_scratch_env(home),
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def _run_skill_script(home: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", "-I", str(home / SKILL_SCRIPT), "--help"],
        env=_scratch_env(home),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_readme_has_install_and_verify_blocks() -> None:
    blocks = _install_section_blocks()

    assert len(blocks) == 2, "expected one install block and one verify block"
    assert "src/muse/lib" in blocks[0]
    assert "get_pr_checks.py --help" in blocks[1]


def test_documented_install_lets_a_lib_importing_skill_script_run(tmp_path: Path) -> None:
    install, verify = _install_section_blocks()

    installed = _bash(install, tmp_path)
    assert installed.returncode == 0, installed.stderr
    assert (tmp_path / "workspace" / "lib" / "github_core").is_dir()

    verified = _bash(verify, tmp_path)
    assert verified.returncode == 0, verified.stderr
    assert "usage: get_pr_checks.py" in verified.stdout


def test_skills_only_install_fails_with_missing_lib_message(tmp_path: Path) -> None:
    install, _ = _install_section_blocks()
    skills_only = "\n".join(
        line.replace(" ~/workspace/lib", "")
        for line in install.splitlines()
        if "src/muse/lib" not in line
    )
    assert "workspace/lib" not in skills_only
    assert "custom-skills" in skills_only

    installed = _bash(skills_only, tmp_path)
    assert installed.returncode == 0, installed.stderr

    result = _run_skill_script(tmp_path)
    assert result.returncode != 0
    assert LIB_MISSING_MESSAGE in result.stderr


def test_rerunning_install_keeps_existing_skills_and_refreshes_lib(tmp_path: Path) -> None:
    install, _ = _install_section_blocks()
    assert _bash(install, tmp_path).returncode == 0
    marker = tmp_path / "workspace" / "custom-skills" / "github" / "local-edit.txt"
    marker.write_text("keep", encoding="utf-8")
    stale = tmp_path / "workspace" / "lib" / "paths.py"
    stale.write_text("# stale\n", encoding="utf-8")

    rerun = _bash(install, tmp_path)

    assert rerun.returncode == 0, rerun.stderr
    assert marker.read_text(encoding="utf-8") == "keep"
    assert stale.read_text(encoding="utf-8") == (
        REPO_ROOT / "src" / "muse" / "lib" / "paths.py"
    ).read_text(encoding="utf-8")

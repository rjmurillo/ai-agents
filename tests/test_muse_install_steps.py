"""Replay the Muse install steps from src/muse/README.md into a scratch HOME (issue #7278).

The README copies skills into ``~/workspace/custom-skills/``. Skill scripts
resolve shared packages from ``lib/`` one level above that directory, so the
install must also place ``lib/`` at ``~/workspace/lib/``. Skills and ``lib/``
are one release, so a re-run replaces both and moves the old copies to a backup
directory. The test runs the documented bash blocks verbatim, then runs one
lib-importing skill script.
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
BACKUP_GLOB = "muse-install-backup-*"
_LIB_RESOLUTION_ENV = frozenset({"COPILOT_PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT", "GITHUB_WORKSPACE"})

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash is required")


def _install_section_blocks() -> list[str]:
    text = README.read_text(encoding="utf-8")
    section = text.split("## Install into Muse", 1)[1]
    return re.findall(r"```bash\n(.*?)```", section, flags=re.DOTALL)


def _scratch_env(home: Path) -> dict[str, str]:
    # GITHUB_WORKSPACE is always set in CI. The skill script then reads
    # $GITHUB_WORKSPACE/.claude/lib and never looks at ~/workspace/lib, which
    # would hide the install layout this test exists to check.
    env = {k: v for k, v in os.environ.items() if k not in _LIB_RESOLUTION_ENV}
    env["HOME"] = str(home)
    return env


def _bash(script: str, home: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-euo", "pipefail", "-c", script],
        cwd=REPO_ROOT,
        env=_scratch_env(home),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )


def _run_skill_script(home: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", "-I", str(home / SKILL_SCRIPT), "--help"],
        env=_scratch_env(home),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
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


def test_skill_script_fails_with_missing_lib_message_when_lib_is_absent(tmp_path: Path) -> None:
    install, _ = _install_section_blocks()
    assert _bash(install, tmp_path).returncode == 0
    (tmp_path / "workspace" / "lib").rename(tmp_path / "lib-moved-away")

    result = _run_skill_script(tmp_path)

    assert result.returncode != 0
    assert LIB_MISSING_MESSAGE in result.stderr


def test_fresh_install_creates_no_backup(tmp_path: Path) -> None:
    install, _ = _install_section_blocks()

    assert _bash(install, tmp_path).returncode == 0

    assert list((tmp_path / "workspace").glob(BACKUP_GLOB)) == []


def test_rerun_replaces_skills_and_lib_and_moves_old_copies_to_backup(tmp_path: Path) -> None:
    install, _ = _install_section_blocks()
    assert _bash(install, tmp_path).returncode == 0
    workspace = tmp_path / "workspace"
    local_edit = workspace / "custom-skills" / "github" / "local-edit.txt"
    local_edit.write_text("mine", encoding="utf-8")
    stale_module = workspace / "lib" / "dropped_upstream.py"
    stale_module.write_text("# removed in the new release\n", encoding="utf-8")
    (workspace / "lib" / "paths.py").write_text("# stale\n", encoding="utf-8")

    rerun = _bash(install, tmp_path)

    assert rerun.returncode == 0, rerun.stderr
    assert not local_edit.exists()
    assert not stale_module.exists()
    released_paths = REPO_ROOT / "src" / "muse" / "lib" / "paths.py"
    assert (workspace / "lib" / "paths.py").read_bytes() == released_paths.read_bytes()
    (backup,) = workspace.glob(BACKUP_GLOB)
    assert (backup / "custom-skills" / "github" / "local-edit.txt").read_text(
        encoding="utf-8"
    ) == "mine"
    assert (backup / "lib" / "dropped_upstream.py").is_file()
    assert _bash(_install_section_blocks()[1], tmp_path).returncode == 0


def test_personal_install_creates_no_agent_files(tmp_path: Path) -> None:
    """The personal agent has no documented agent format, so it gets no agents."""
    install, _ = _install_section_blocks()

    assert _bash(install, tmp_path).returncode == 0

    created = [p for p in tmp_path.rglob("*") if "agents" in p.relative_to(tmp_path).parts]
    assert created == []
    assert not (tmp_path / ".config").exists()

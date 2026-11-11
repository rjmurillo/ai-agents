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


def _section_blocks(heading: str) -> list[str]:
    """Return the bash blocks of the README section that starts at ``heading``.

    The section ends at the next ``## `` heading, so blocks of a later section
    are never replayed as part of this one.
    """
    text = README.read_text(encoding="utf-8")
    section = text.split(heading, 1)[1].split("\n## ", 1)[0]
    return re.findall(r"```bash\n(.*?)```", section, flags=re.DOTALL)


def _install_section_blocks() -> list[str]:
    return _section_blocks("## Install into Muse")


def _agents_install_block() -> str:
    (block,) = _section_blocks("## Install agents into Muse Code")
    return block


def _scratch_env(home: Path) -> dict[str, str]:
    # GITHUB_WORKSPACE is always set in CI. The skill script then reads
    # $GITHUB_WORKSPACE/.claude/lib and never looks at ~/workspace/lib, which
    # would hide the install layout this test exists to check.
    env = {k: v for k, v in os.environ.items() if k not in _LIB_RESOLUTION_ENV}
    env["HOME"] = str(home)
    return env


def _bash(script: str, home: Path, *, xdg: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = _scratch_env(home)
    env.pop("XDG_CONFIG_HOME", None)
    if xdg is not None:
        env["XDG_CONFIG_HOME"] = str(xdg)
    return subprocess.run(
        ["bash", "-euo", "pipefail", "-c", script],
        cwd=REPO_ROOT,
        env=env,
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


# Agents section (issue #7226, ADR-115 Decision 8 amendment) ---------------------

AGENTS_SRC = REPO_ROOT / "src" / "muse" / "agents"
AGENTS_BACKUP_GLOB = "agents-backup-*"


def _shipped_agent_names() -> list[str]:
    return sorted(p.name for p in AGENTS_SRC.glob("*.md"))


def test_agents_section_has_exactly_one_bash_block() -> None:
    assert "agents_dir=" in _agents_install_block()


def test_skills_blocks_do_not_include_the_agents_block() -> None:
    assert all("agents_dir=" not in block for block in _install_section_blocks())


def test_agents_install_lands_every_shipped_agent(tmp_path: Path) -> None:
    names = _shipped_agent_names()
    assert names, "no shipped agents under src/muse/agents"

    result = _bash(_agents_install_block(), tmp_path)

    assert result.returncode == 0, result.stderr
    installed = tmp_path / ".config" / "muse" / "agents"
    assert sorted(p.name for p in installed.glob("*.md")) == names
    for name in names:
        assert (installed / name).read_bytes() == (AGENTS_SRC / name).read_bytes()


def test_agents_install_honors_xdg_config_home(tmp_path: Path) -> None:
    xdg = tmp_path / "xdg"

    (tmp_path / "home").mkdir()
    result = _bash(_agents_install_block(), tmp_path / "home", xdg=xdg)

    assert result.returncode == 0, result.stderr
    assert sorted(p.name for p in (xdg / "muse" / "agents").glob("*.md")) == _shipped_agent_names()
    assert not (tmp_path / "home" / ".config").exists()


def test_agents_fresh_install_makes_no_backup(tmp_path: Path) -> None:
    assert _bash(_agents_install_block(), tmp_path).returncode == 0

    assert list((tmp_path / ".config" / "muse").glob(AGENTS_BACKUP_GLOB)) == []


def test_agents_reinstall_moves_a_same_named_file_to_backup(tmp_path: Path) -> None:
    block = _agents_install_block()
    assert _bash(block, tmp_path).returncode == 0
    muse = tmp_path / ".config" / "muse"
    mine = muse / "agents" / "architect.md"
    mine.write_text("my own architect\n", encoding="utf-8")
    unrelated = muse / "agents" / "my-agent.md"
    unrelated.write_text("keep me\n", encoding="utf-8")

    rerun = _bash(block, tmp_path)

    assert rerun.returncode == 0, rerun.stderr
    (backup,) = muse.glob(AGENTS_BACKUP_GLOB)
    assert (backup / "architect.md").read_text(encoding="utf-8") == "my own architect\n"
    assert mine.read_bytes() == (AGENTS_SRC / "architect.md").read_bytes()
    assert unrelated.read_text(encoding="utf-8") == "keep me\n"

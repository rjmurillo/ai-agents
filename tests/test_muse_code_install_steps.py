"""Replay the Muse Code install steps from src/muse/README.md into a scratch HOME (issue #7226).

ADR-115 Decision 8 (amended 2026-11-11): Muse Code gets skills, ``lib/``, and
agents under ``${XDG_CONFIG_HOME:-$HOME/.config}/muse/``. A re-run moves old
copies to a backup directory and never deletes one. The personal-agent steps
are replayed in ``test_muse_install_steps.py``.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tests.muse_install_helpers import (
    CODE_HEADING,
    LIB_MISSING_MESSAGE,
    REPO_ROOT,
    run_bash,
    scratch_env,
    section_blocks,
)

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash is required")


def _code_blocks() -> list[str]:
    return section_blocks(CODE_HEADING)


AGENTS_SRC = REPO_ROOT / "src" / "muse" / "agents"
SKILLS_SRC = REPO_ROOT / "src" / "muse" / "skills"
CODE_SKILL_SCRIPT = Path(".config/muse/skills/github/scripts/pr/get_pr_checks.py")
CODE_BACKUP_GLOB = "muse-install-backup-*"


def _shipped_agent_names() -> list[str]:
    return sorted(p.name for p in AGENTS_SRC.glob("*.md"))


def _code_install() -> str:
    install, _verify = _code_blocks()
    return install


def test_code_section_has_install_and_verify_blocks() -> None:
    install, verify = _code_blocks()

    assert "src/muse/agents/*.md" in install
    assert "get_pr_checks.py" in verify and "--help" in verify


def test_code_install_lands_skills_lib_and_agents(tmp_path: Path) -> None:
    result = run_bash(_code_install(), tmp_path)

    assert result.returncode == 0, result.stderr
    skills = tmp_path / ".config" / "muse" / "skills"
    assert sorted(p.name for p in skills.iterdir()) == sorted(p.name for p in SKILLS_SRC.iterdir())
    assert (tmp_path / ".config" / "muse" / "lib" / "github_core").is_dir()
    installed = tmp_path / ".config" / "muse" / "agents"
    assert sorted(p.name for p in installed.glob("*.md")) == _shipped_agent_names()
    for name in _shipped_agent_names():
        assert (installed / name).read_bytes() == (AGENTS_SRC / name).read_bytes()


def test_code_install_lets_a_lib_importing_skill_script_run(tmp_path: Path) -> None:
    assert run_bash(_code_install(), tmp_path).returncode == 0

    verified = run_bash(_code_blocks()[1], tmp_path)

    assert verified.returncode == 0, verified.stderr
    assert "usage: get_pr_checks.py" in verified.stdout


def test_code_skill_script_fails_when_lib_is_absent(tmp_path: Path) -> None:
    assert run_bash(_code_install(), tmp_path).returncode == 0
    (tmp_path / ".config" / "muse" / "lib").rename(tmp_path / "lib-moved-away")

    result = subprocess.run(
        ["python3", "-I", str(tmp_path / CODE_SKILL_SCRIPT), "--help"],
        env=scratch_env(tmp_path),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )

    assert result.returncode != 0
    assert LIB_MISSING_MESSAGE in result.stderr


def test_code_install_honors_xdg_config_home(tmp_path: Path) -> None:
    xdg = tmp_path / "xdg"
    (tmp_path / "home").mkdir()

    result = run_bash(_code_install(), tmp_path / "home", xdg=xdg)

    assert result.returncode == 0, result.stderr
    assert sorted(p.name for p in (xdg / "muse" / "agents").glob("*.md")) == _shipped_agent_names()
    assert (xdg / "muse" / "lib" / "github_core").is_dir()
    assert (xdg / "muse" / "skills" / "github" / "SKILL.md").is_file()
    assert not (tmp_path / "home" / ".config").exists()


def test_code_fresh_install_makes_no_backup(tmp_path: Path) -> None:
    assert run_bash(_code_install(), tmp_path).returncode == 0

    assert list((tmp_path / ".config" / "muse").glob(CODE_BACKUP_GLOB)) == []


def test_code_reinstall_moves_clashes_to_backup(tmp_path: Path) -> None:
    block = _code_install()
    assert run_bash(block, tmp_path).returncode == 0
    agents = tmp_path / ".config" / "muse" / "agents"
    (agents / "architect.md").write_text("my own architect\n", encoding="utf-8")
    (agents / "my-agent.md").write_text("keep me\n", encoding="utf-8")
    (tmp_path / ".config" / "muse" / "skills" / "github" / "local-edit.txt").write_text(
        "mine", encoding="utf-8"
    )
    (tmp_path / ".config" / "muse" / "lib" / "dropped_upstream.py").write_text(
        "# old\n", encoding="utf-8"
    )

    rerun = run_bash(block, tmp_path)

    assert rerun.returncode == 0, rerun.stderr
    (backup,) = (tmp_path / ".config" / "muse").glob(CODE_BACKUP_GLOB)
    assert (backup / "agents" / "architect.md").read_text(encoding="utf-8") == "my own architect\n"
    assert (agents / "architect.md").read_bytes() == (AGENTS_SRC / "architect.md").read_bytes()
    assert (agents / "my-agent.md").read_text(encoding="utf-8") == "keep me\n"
    assert (backup / "skills" / "github" / "local-edit.txt").read_text(encoding="utf-8") == "mine"
    assert (backup / "lib" / "dropped_upstream.py").is_file()
    assert not (tmp_path / ".config" / "muse" / "lib" / "dropped_upstream.py").exists()


def test_code_section_never_installs_to_a_codex_skill_root() -> None:
    install = _code_install()

    assert ".agents/skills" not in install
    assert "~/.agents" not in install

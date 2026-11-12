"""Replay the agents part of the Muse Code install block from the install guide (issue #7226).

``test_muse_code_install_steps.py`` replays the same guide block for skills and
``lib/``. This file checks that the block also copies the shipped Muse agents,
moves a clashing agent aside, leaves the user's own agents alone, and does not
write through a dangling symlink (ADR-115 Decision 8).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tests.test_muse_code_install_steps import (
    BACKUP_GLOB,
    REPO_ROOT,
    _install,
    _install_block,
    _scratch_env,
)

AGENTS_SRC = REPO_ROOT / "src" / "muse" / "agents"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash is required")


def _shipped_agent_names() -> list[str]:
    return sorted(p.name for p in AGENTS_SRC.glob("*.md"))


def test_install_places_every_shipped_agent_byte_for_byte(tmp_path: Path) -> None:
    assert _install(tmp_path).returncode == 0

    installed = tmp_path / ".config" / "muse" / "agents"
    assert sorted(p.name for p in installed.glob("*.md")) == _shipped_agent_names()
    for name in _shipped_agent_names():
        assert (installed / name).read_bytes() == (AGENTS_SRC / name).read_bytes()


def test_rerun_moves_a_clashing_agent_aside_and_keeps_the_users_own_agent(tmp_path: Path) -> None:
    assert _install(tmp_path).returncode == 0
    root = tmp_path / ".config" / "muse"
    clash = root / "agents" / "critic.md"
    clash.write_text("my edited critic\n", encoding="utf-8")
    own = root / "agents" / "my-own-agent.md"
    own.write_text("---\nname: my-own-agent\ndescription: x\n---\n", encoding="utf-8")

    rerun = _install(tmp_path)

    assert rerun.returncode == 0, rerun.stderr
    assert own.is_file(), "an agent the toolkit does not ship must be left alone"
    (backup,) = root.glob(BACKUP_GLOB)
    assert (backup / "agents" / "critic.md").read_text(encoding="utf-8") == "my edited critic\n"
    assert clash.read_bytes() == (AGENTS_SRC / "critic.md").read_bytes()


def test_install_backs_up_a_dangling_symlink_instead_of_writing_through_it(tmp_path: Path) -> None:
    root = tmp_path / ".config" / "muse"
    (root / "agents").mkdir(parents=True)
    outside = tmp_path / "outside" / "target.md"
    (root / "agents" / "critic.md").symlink_to(outside)

    installed = _install(tmp_path)

    assert installed.returncode == 0, installed.stderr
    assert not outside.exists(), "the install wrote through a symlink"
    (backup,) = root.glob(BACKUP_GLOB)
    assert (backup / "agents" / "critic.md").is_symlink()


def test_install_backs_up_a_dangling_lib_symlink(tmp_path: Path) -> None:
    root = tmp_path / ".config" / "muse"
    root.mkdir(parents=True)
    (root / "lib").symlink_to(tmp_path / "outside-lib")

    installed = _install(tmp_path)

    assert installed.returncode == 0, installed.stderr
    assert not (tmp_path / "outside-lib").exists(), "the install wrote through a symlink"
    (backup,) = root.glob(BACKUP_GLOB)
    assert (backup / "lib").is_symlink()


def test_install_backs_up_a_dangling_skill_symlink(tmp_path: Path) -> None:
    root = tmp_path / ".config" / "muse"
    (root / "skills").mkdir(parents=True)
    (root / "skills" / "github").symlink_to(tmp_path / "outside-skill")

    installed = _install(tmp_path)

    assert installed.returncode == 0, installed.stderr
    assert not (tmp_path / "outside-skill").exists(), "the install wrote through a symlink"
    (backup,) = root.glob(BACKUP_GLOB)
    assert (backup / "skills" / "github").is_symlink()


def _install_with_unwritable_backup(home: Path) -> subprocess.CompletedProcess[str]:
    """Run the guide block with a backup path that is a file, so every backup move fails."""
    stub = home / "stub"
    stub.mkdir()
    (stub / "date").write_text("#!/bin/sh\necho FIXED\n", encoding="utf-8")
    (stub / "date").chmod(0o755)
    (home / ".config" / "muse").mkdir(parents=True, exist_ok=True)
    (home / ".config" / "muse" / "install-backup-FIXED").write_text("a file", encoding="utf-8")
    env = _scratch_env(home)
    env["PATH"] = f"{stub}:{env['PATH']}"
    return subprocess.run(
        ["bash", "-euo", "pipefail", "-c", _install_block()],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )


def test_a_failed_backup_keeps_the_users_lib_skill_and_agent(tmp_path: Path) -> None:
    root = tmp_path / ".config" / "muse"
    (root / "lib").mkdir(parents=True)
    (root / "lib" / "mine.py").write_text("mine\n", encoding="utf-8")
    (root / "skills" / "github").mkdir(parents=True)
    (root / "skills" / "github" / "mine.txt").write_text("mine\n", encoding="utf-8")
    (root / "agents").mkdir(parents=True)
    (root / "agents" / "critic.md").write_text("mine\n", encoding="utf-8")

    result = _install_with_unwritable_backup(tmp_path)

    assert result.returncode == 0, result.stderr
    for kept in ("lib", "skills/github", "agents/critic.md"):
        assert f"backup failed, kept {root}/{kept}" in result.stderr, kept
    assert (root / "lib" / "mine.py").is_file() and not (root / "lib" / "lib").exists()
    assert (root / "skills" / "github" / "mine.txt").is_file()
    assert not (root / "skills" / "github" / "github").exists(), (
        "the copy nested inside the old one"
    )
    assert (root / "agents" / "critic.md").read_text(encoding="utf-8") == "mine\n"
    assert (root / "agents" / "architect.md").is_file(), "other agents still install"

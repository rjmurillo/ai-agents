"""Replay the agents part of the Muse Code install block from the install guide (issue #7226).

``test_muse_code_install_steps.py`` replays the same guide block for skills and
``lib/``. This file checks that the block also copies the shipped Muse agents,
moves a clashing agent aside, leaves the user's own agents alone, and does not
write through a dangling symlink (ADR-115 Decision 8).
"""

from __future__ import annotations

from pathlib import Path

from tests.test_muse_code_install_steps import BACKUP_GLOB, REPO_ROOT, _install

AGENTS_SRC = REPO_ROOT / "src" / "muse" / "agents"


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

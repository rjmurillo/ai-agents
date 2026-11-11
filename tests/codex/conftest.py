"""Shared fixtures and helpers for the ``src/codex/install_agents.py`` tests."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "src" / "codex" / "install_agents.py"
OWNERSHIP = ".project-toolkit-agents.json"

_spec = importlib.util.spec_from_file_location("install_agents_under_test", SCRIPT)
assert _spec is not None and _spec.loader is not None
ia = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = ia
_spec.loader.exec_module(ia)


def agent_bytes(name: str, body: str = "do the work") -> bytes:
    return (
        f'name = "{name}"\ndescription = "d {name}"\ndeveloper_instructions = "{body}"\n'.encode()
    )


def make_symlink(link: Path, target: Path) -> None:
    """Create ``link`` pointing at ``target``, or skip where the host forbids symlinks."""
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this host")


def child_env(**extra: str) -> dict[str, str]:
    """A minimal environment for a child interpreter that still starts on Windows."""
    keep = ("PATH", "SYSTEMROOT", "TEMP", "TMP", "USERPROFILE", "HOME")
    env = {name: os.environ[name] for name in keep if name in os.environ}
    env.update(extra)
    return env


def write_shipped(agents: Path, **bodies: str) -> None:
    agents.mkdir(parents=True, exist_ok=True)
    for old in agents.glob("*.toml"):
        old.unlink()
    for name, body in bodies.items():
        (agents / f"{name}.toml").write_bytes(agent_bytes(name, body))


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A fake plugin dir with three agents, an isolated CODEX_HOME, and a project dir."""
    agents = tmp_path / "plugin" / "agents"
    write_shipped(agents, architect="a1", critic="c1", qa="q1")
    home = tmp_path / "codex_home"
    home.mkdir()
    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    return type("W", (), {"agents": agents, "home": home, "project": project})()


def run_installer(world, *extra, project=True):
    argv = list(extra)
    if project:
        argv = ["--project", str(world.project), *argv]
    return ia.main(argv, agents_dir=world.agents)


def trust_project(world) -> None:
    (world.home / "config.toml").write_text(
        f'[projects."{world.project}"]\ntrust_level = "trusted"\n', encoding="utf-8"
    )


def target_dir(world) -> Path:
    return world.project / ".codex" / "agents"


def read_record(world, target=None) -> dict:
    return json.loads(((target or target_dir(world)) / OWNERSHIP).read_text(encoding="utf-8"))

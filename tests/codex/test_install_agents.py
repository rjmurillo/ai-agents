"""``src/codex/install_agents.py``: ownership-tracked install of the Codex agents."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import tomllib

SCRIPT = Path(__file__).resolve().parents[2] / "src" / "codex" / "install_agents.py"
OWNERSHIP = ".project-toolkit-agents.json"

_spec = importlib.util.spec_from_file_location("install_agents_under_test", SCRIPT)
assert _spec is not None and _spec.loader is not None
ia = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = ia
_spec.loader.exec_module(ia)


def _agent(name: str, body: str = "do the work") -> bytes:
    return (
        f'name = "{name}"\ndescription = "d {name}"\ndeveloper_instructions = "{body}"\n'.encode()
    )


def _write_shipped(agents: Path, **bodies: str) -> None:
    agents.mkdir(parents=True, exist_ok=True)
    for old in agents.glob("*.toml"):
        old.unlink()
    for name, body in bodies.items():
        (agents / f"{name}.toml").write_bytes(_agent(name, body))


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A fake plugin dir with three agents, an isolated CODEX_HOME, and a project dir."""
    agents = tmp_path / "plugin" / "agents"
    _write_shipped(agents, architect="a1", critic="c1", qa="q1")
    home = tmp_path / "codex_home"
    home.mkdir()
    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return type("W", (), {"agents": agents, "home": home, "project": project})()


def _run(world, *extra, project=True):
    argv = list(extra)
    if project:
        argv = ["--project", str(world.project), *argv]
    return ia.main(argv, agents_dir=world.agents)


def _trust(world) -> None:
    (world.home / "config.toml").write_text(
        f'[projects."{world.project}"]\ntrust_level = "trusted"\n', encoding="utf-8"
    )


def _target(world) -> Path:
    return world.project / ".codex" / "agents"


def _record(world, target=None) -> dict:
    return json.loads(((target or _target(world)) / OWNERSHIP).read_text())


def test_fresh_install_writes_all_agents_and_ownership(world, capsys):
    assert _run(world) == 0
    target = _target(world)
    assert sorted(p.name for p in target.glob("*.toml")) == [
        "architect.toml",
        "critic.toml",
        "qa.toml",
    ]
    files = _record(world)["files"]
    assert files["qa.toml"] == hashlib.sha256((target / "qa.toml").read_bytes()).hexdigest()
    assert "installed 3" in capsys.readouterr().out


def test_rerun_is_idempotent(world, capsys):
    _run(world)
    before = {p.name: p.read_bytes() for p in _target(world).iterdir()}
    capsys.readouterr()
    assert _run(world) == 0
    assert {p.name: p.read_bytes() for p in _target(world).iterdir()} == before
    assert "skipped 3" in capsys.readouterr().out


def test_upgrade_overwrites_an_owned_unedited_file(world):
    _run(world)
    _write_shipped(world.agents, architect="a2", critic="c1", qa="q1")
    assert _run(world) == 0
    assert b"a2" in (_target(world) / "architect.toml").read_bytes()


def test_dropped_owned_file_is_removed_and_unrecorded_one_stays(world):
    _run(world)
    (_target(world) / "mine.toml").write_bytes(_agent("mine"))
    _write_shipped(world.agents, architect="a1", critic="c1")
    assert _run(world) == 0
    assert not (_target(world) / "qa.toml").exists()
    assert (_target(world) / "mine.toml").exists()
    assert "qa.toml" not in _record(world)["files"]


def test_dropped_owned_file_that_was_edited_is_left_with_warning(world, capsys):
    _run(world)
    (_target(world) / "qa.toml").write_bytes(_agent("qa", "edited"))
    _write_shipped(world.agents, architect="a1", critic="c1")
    capsys.readouterr()
    assert _run(world) == 0
    assert b"edited" in (_target(world) / "qa.toml").read_bytes()
    assert "qa.toml was edited" in capsys.readouterr().err


def test_user_edited_owned_file_is_a_conflict_and_nothing_is_written(world, capsys):
    _run(world)
    (_target(world) / "critic.toml").write_bytes(_agent("critic", "mine"))
    _write_shipped(world.agents, architect="a9", critic="c1", qa="q1")
    assert _run(world) == 1
    assert b"mine" in (_target(world) / "critic.toml").read_bytes()
    assert b"a9" not in (_target(world) / "architect.toml").read_bytes()
    assert "CONFLICT: critic.toml" in capsys.readouterr().err


def test_unowned_same_name_file_refuses_and_writes_nothing(world, capsys):
    target = _target(world)
    target.mkdir(parents=True)
    (target / "qa.toml").write_bytes(_agent("qa", "theirs"))
    assert _run(world) == 1
    assert sorted(p.name for p in target.iterdir()) == ["qa.toml"]
    assert "CONFLICT: qa.toml" in capsys.readouterr().err


def test_namespace_installs_prefixed_file_with_prefixed_parsed_name(world, capsys):
    target = _target(world)
    target.mkdir(parents=True)
    (target / "qa.toml").write_bytes(_agent("qa", "theirs"))
    assert _run(world, "--namespace", "tk") == 0
    parsed = tomllib.loads((target / "tk-qa.toml").read_text())
    assert parsed["name"] == "tk-qa"
    assert parsed["developer_instructions"] == "q1"
    assert b"theirs" in (target / "qa.toml").read_bytes()
    assert "tk-qa.toml" in _record(world)["files"]
    err = capsys.readouterr().err
    assert "hand work to `qa`" in err and "your own `qa`" in err


def test_namespaced_file_survives_a_later_plain_run_and_upgrades(world):
    target = _target(world)
    target.mkdir(parents=True)
    (target / "qa.toml").write_bytes(_agent("qa", "theirs"))
    _run(world, "--namespace", "tk")
    _write_shipped(world.agents, architect="a1", critic="c1", qa="q2")
    assert _run(world) == 0
    assert tomllib.loads((target / "tk-qa.toml").read_text())["developer_instructions"] == "q2"
    assert b"theirs" in (target / "qa.toml").read_bytes()


def test_namespaced_name_collision_refuses(world, capsys):
    target = _target(world)
    target.mkdir(parents=True)
    (target / "qa.toml").write_bytes(_agent("qa"))
    (target / "tk-qa.toml").write_bytes(_agent("tk-qa", "theirs"))
    assert _run(world, "--namespace", "tk") == 1
    assert not (target / OWNERSHIP).exists()
    assert "tk-qa.toml" in capsys.readouterr().err


def test_no_namespace_warning_without_conflict(world, capsys):
    _run(world, "--namespace", "tk")
    assert "hand work to" not in capsys.readouterr().err


@pytest.mark.parametrize("prefix", ["", "Tk", "-tk", "t k", "t/k", "t.k"])
def test_invalid_prefix_exits_2(world, prefix):
    with pytest.raises(SystemExit) as exc:
        _run(world, "--namespace", prefix)
    assert exc.value.code == 2


def test_project_and_user_are_mutually_exclusive(world):
    with pytest.raises(SystemExit) as exc:
        ia.main(["--project", str(world.project), "--user"], agents_dir=world.agents)
    assert exc.value.code == 2


def test_user_install_honors_codex_home(world):
    assert _run(world, "--user", project=False) == 0
    assert (world.home / "agents" / "qa.toml").is_file()
    assert (world.home / "agents" / OWNERSHIP).is_file()
    assert not (world.project / ".codex").exists()


def test_user_install_falls_back_to_home_dot_codex(world, monkeypatch, tmp_path):
    monkeypatch.delenv("CODEX_HOME")
    monkeypatch.setattr(ia.Path, "home", classmethod(lambda cls: tmp_path / "fakehome"))
    assert _run(world, "--user", project=False) == 0
    assert (tmp_path / "fakehome" / ".codex" / "agents" / "qa.toml").is_file()


def test_trust_warning_present_when_project_untrusted(world, capsys):
    assert _run(world) == 0
    assert "trusted projects" in capsys.readouterr().err


def test_trust_warning_absent_when_project_trusted(world, capsys):
    _trust(world)
    assert _run(world) == 0
    assert "trusted" not in capsys.readouterr().err


def test_trust_warning_present_when_trust_level_is_not_trusted(world, capsys):
    (world.home / "config.toml").write_text(
        f'[projects."{world.project}"]\ntrust_level = "untrusted"\n', encoding="utf-8"
    )
    _run(world)
    assert "trusted projects" in capsys.readouterr().err


def test_user_install_never_warns_about_trust(world, capsys):
    _run(world, "--user", project=False)
    assert "trusted" not in capsys.readouterr().err


def test_dry_run_writes_nothing(world, capsys):
    assert _run(world, "--dry-run") == 0
    assert not (world.project / ".codex").exists()
    assert "dry run" in capsys.readouterr().out


def test_write_order_agents_before_ownership(world, monkeypatch):
    order: list[str] = []
    real = ia._atomic_write
    monkeypatch.setattr(ia, "_atomic_write", lambda p, d: (order.append(p.name), real(p, d)))
    _run(world)
    assert order[-1] == OWNERSHIP and OWNERSHIP not in order[:-1] and len(order) == 4


def test_crash_before_ownership_write_self_heals_by_adopting(world):
    """Agent files landed, the ownership file did not: identical bytes are adopted."""
    target = _target(world)
    target.mkdir(parents=True)
    for p in world.agents.glob("*.toml"):
        shutil.copy(p, target / p.name)
    assert _run(world) == 0
    assert set(_record(world)["files"]) == {"architect.toml", "critic.toml", "qa.toml"}


def test_unrecorded_file_with_different_bytes_is_not_adopted(world):
    """Negative control for adoption: only byte-identical files are adopted."""
    target = _target(world)
    target.mkdir(parents=True)
    (target / "qa.toml").write_bytes(_agent("qa", "other"))
    assert _run(world) == 1


def test_uninstall_removes_owned_unedited_and_the_ownership_file(world):
    _run(world)
    (_target(world) / "mine.toml").write_bytes(_agent("mine"))
    assert _run(world, "--uninstall") == 0
    assert sorted(p.name for p in _target(world).iterdir()) == ["mine.toml"]


def test_uninstall_leaves_edited_files_and_keeps_their_record(world, capsys):
    _run(world)
    (_target(world) / "qa.toml").write_bytes(_agent("qa", "edited"))
    capsys.readouterr()
    assert _run(world, "--uninstall") == 0
    assert not (_target(world) / "critic.toml").exists()
    assert (_target(world) / "qa.toml").exists()
    assert list(_record(world)["files"]) == ["qa.toml"]
    assert "qa.toml was edited" in capsys.readouterr().err


def test_uninstall_without_ownership_touches_nothing(world):
    target = _target(world)
    target.mkdir(parents=True)
    (target / "qa.toml").write_bytes(_agent("qa", "theirs"))
    assert _run(world, "--uninstall") == 0
    assert (target / "qa.toml").read_bytes() == _agent("qa", "theirs")


def test_uninstall_dry_run_removes_nothing(world):
    _run(world)
    assert _run(world, "--uninstall", "--dry-run") == 0
    assert (_target(world) / "qa.toml").exists()


def test_uninstall_removes_namespaced_files(world):
    target = _target(world)
    target.mkdir(parents=True)
    (target / "qa.toml").write_bytes(_agent("qa", "theirs"))
    _run(world, "--namespace", "tk")
    assert _run(world, "--uninstall") == 0
    assert not (target / "tk-qa.toml").exists()
    assert (target / "qa.toml").exists()


def test_uninstall_with_namespace_is_a_usage_error(world):
    with pytest.raises(SystemExit) as exc:
        _run(world, "--uninstall", "--namespace", "tk")
    assert exc.value.code == 2


@pytest.mark.parametrize(
    "bad",
    [
        "not json",
        '{"files": []}',
        '{"files": {"../x.toml": "h"}}',
        '{"files": {"a/b.toml": "h"}}',
        '{"nofiles": {}}',
    ],
)
def test_malformed_ownership_exits_2(world, bad, capsys):
    target = _target(world)
    target.mkdir(parents=True)
    (target / OWNERSHIP).write_text(bad)
    assert _run(world) == 2
    assert "ownership file" in capsys.readouterr().err


def test_symlinked_target_is_a_conflict(world, tmp_path):
    target = _target(world)
    target.mkdir(parents=True)
    outside = tmp_path / "outside.toml"
    outside.write_bytes(_agent("qa"))
    (target / "qa.toml").symlink_to(outside)
    assert _run(world) == 1
    assert outside.read_bytes() == _agent("qa")


def test_missing_or_empty_agents_dir_exits_2(world, tmp_path, capsys):
    assert ia.main(["--project", str(world.project)], agents_dir=tmp_path / "none") == 2
    (tmp_path / "empty").mkdir()
    assert ia.main(["--project", str(world.project)], agents_dir=tmp_path / "empty") == 2


def test_namespaced_rewrite_rejects_a_file_without_a_name_first_line():
    with pytest.raises(ia.InstallError):
        ia.namespaced_bytes(b'description = "x"\nname = "a"\n', "tk", "a.toml")


def test_script_runs_from_a_copy_next_to_its_agents(world, tmp_path):
    """Subprocess run from a copied plugin dir, as from the Codex plugin cache."""
    plugin = tmp_path / "plugin"
    shutil.copy(SCRIPT, plugin / "install_agents.py")
    env = {"PATH": "/usr/bin:/bin", "CODEX_HOME": str(world.home), "HOME": str(tmp_path / "h")}
    done = subprocess.run(
        [sys.executable, str(plugin / "install_agents.py"), "--project", str(world.project)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert (_target(world) / "qa.toml").is_file()
    again = subprocess.run(
        [
            sys.executable,
            str(plugin / "install_agents.py"),
            "--project",
            str(world.project),
            "--namespace",
            "Bad",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert again.returncode == 2


def test_namespaced_rewrite_rejects_invalid_toml():
    with pytest.raises(ia.InstallError, match="invalid TOML"):
        ia.namespaced_bytes(b'name = "a"\nbroken = \n', "tk", "a.toml")


def test_namespaced_rewrite_without_tomllib_still_prefixes(monkeypatch):
    monkeypatch.setattr(ia, "tomllib", None)
    assert ia.namespaced_bytes(_agent("a"), "tk", "a.toml").startswith(b'name = "tk-a"\n')


def test_trust_check_without_tomllib_warns_instead_of_guessing(world, monkeypatch):
    monkeypatch.setattr(ia, "tomllib", None)
    assert "needs Python 3.11+" in ia.trust_warning(world.project)


def test_edited_namespaced_file_is_kept_with_its_record(world, capsys):
    target = _target(world)
    target.mkdir(parents=True)
    (target / "qa.toml").write_bytes(_agent("qa", "theirs"))
    _run(world, "--namespace", "tk")
    (target / "tk-qa.toml").write_bytes(_agent("tk-qa", "edited"))
    capsys.readouterr()
    assert _run(world) == 0
    assert b"edited" in (target / "tk-qa.toml").read_bytes()
    assert _record(world)["namespaced"] == {"tk-qa.toml": "qa.toml"}
    assert "tk-qa.toml was edited" in capsys.readouterr().err


def test_uninstall_keeps_the_source_of_an_edited_namespaced_file(world):
    target = _target(world)
    target.mkdir(parents=True)
    (target / "qa.toml").write_bytes(_agent("qa", "theirs"))
    _run(world, "--namespace", "tk")
    (target / "tk-qa.toml").write_bytes(_agent("tk-qa", "edited"))
    assert _run(world, "--uninstall") == 0
    assert _record(world)["namespaced"] == {"tk-qa.toml": "qa.toml"}


def test_recorded_file_deleted_by_the_user_is_dropped_from_the_record(world):
    _run(world)
    (_target(world) / "qa.toml").unlink()
    _write_shipped(world.agents, architect="a1", critic="c1")
    assert _run(world) == 0
    assert "qa.toml" not in _record(world)["files"]


def test_failed_replace_leaves_no_temp_file_and_no_ownership(world, monkeypatch):
    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(ia.os, "replace", boom)
    with pytest.raises(OSError, match="disk full"):
        _run(world)
    assert [p.name for p in _target(world).iterdir()] == []


def test_module_entry_point_exits_with_main_status(world, tmp_path):
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True, check=False
    )
    assert done.returncode == 0 and "--namespace" in done.stdout

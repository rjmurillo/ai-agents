"""``install_agents.py``: forged namespace records, failure exit codes, and file modes."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import tomllib

from tests.codex.conftest import (
    OWNERSHIP,
    SCRIPT,
    agent_bytes,
    ia,
    make_symlink,
    run_installer,
    target_dir,
    trust_project,
)

SHIPPED_DIR = SCRIPT.parent / "agents"


def _plant(world, payload: dict) -> Path:
    target = target_dir(world)
    target.mkdir(parents=True, exist_ok=True)
    (target / OWNERSHIP).write_text(json.dumps(payload), encoding="utf-8")
    return target


def test_forged_namespaced_record_does_not_excuse_a_clash(world, capsys):
    target = _plant(
        world,
        {"files": {"tk-qa.toml": "a" * 64}, "namespaced": {"tk-qa.toml": "qa.toml"}},
    )
    (target / "qa.toml").write_bytes(agent_bytes("qa", "theirs"))
    before = sorted(p.name for p in target.iterdir())
    assert run_installer(world) == 1
    assert sorted(p.name for p in target.iterdir()) == before
    assert "qa.toml" in capsys.readouterr().err


def test_namespaced_record_without_a_files_entry_is_malformed(world, capsys):
    target = _plant(world, {"files": {}, "namespaced": {"tk-qa.toml": "qa.toml"}})
    assert run_installer(world) == 2
    assert [p.name for p in target.iterdir()] == [OWNERSHIP]
    assert "malformed ownership file" in capsys.readouterr().err


def test_present_namespaced_copy_still_excuses_the_clash(world):
    """Negative control for the forged-record test: a real earlier run keeps working."""
    target = target_dir(world)
    target.mkdir(parents=True)
    (target / "qa.toml").write_bytes(agent_bytes("qa", "theirs"))
    assert run_installer(world, "--namespace", "tk") == 0
    assert run_installer(world) == 0
    assert (target / "tk-qa.toml").is_file()


def test_rerun_keeps_warning_about_handoffs(world, capsys):
    target = target_dir(world)
    target.mkdir(parents=True)
    (target / "qa.toml").write_bytes(agent_bytes("qa", "theirs"))
    run_installer(world, "--namespace", "tk")
    capsys.readouterr()
    assert run_installer(world) == 0
    assert "hand work to `qa`" in capsys.readouterr().err


def test_changed_prefix_is_reported_not_silently_ignored(world, capsys):
    target = target_dir(world)
    target.mkdir(parents=True)
    (target / "qa.toml").write_bytes(agent_bytes("qa", "theirs"))
    run_installer(world, "--namespace", "tk")
    capsys.readouterr()
    assert run_installer(world, "--namespace", "zz") == 0
    assert "--namespace zz was not applied" in capsys.readouterr().err
    assert not (target / "zz-qa.toml").exists()


def test_edited_owned_file_conflict_names_the_edit(world, capsys):
    run_installer(world)
    edited = target_dir(world) / "qa.toml"
    edited.write_bytes(edited.read_bytes() + b"# mine\n")
    assert run_installer(world) == 1
    assert "qa.toml was edited after install" in capsys.readouterr().err


def test_symlink_conflict_names_the_symlink(world, capsys):
    target = target_dir(world)
    target.mkdir(parents=True)
    victim = world.project / "victim.txt"
    victim.write_text("keep", encoding="utf-8")
    make_symlink(target / "qa.toml", victim)
    assert run_installer(world) == 1
    assert "qa.toml is a symlink" in capsys.readouterr().err
    assert victim.read_text(encoding="utf-8") == "keep"


def test_undecodable_config_toml_warns_instead_of_crashing(world, capsys):
    (world.home / "config.toml").write_bytes(b"\xff\xfe\x00bad")
    assert run_installer(world) == 0
    assert "missing or unreadable" in capsys.readouterr().err
    assert (target_dir(world) / "qa.toml").is_file()


def test_trusted_project_still_gives_no_warning(world, capsys):
    """Negative control for the config.toml test."""
    trust_project(world)
    assert run_installer(world) == 0
    assert "trusted" not in capsys.readouterr().err


def test_ownership_path_that_is_not_a_file_exits_2_and_writes_nothing(world, capsys):
    target = target_dir(world)
    (target / OWNERSHIP).mkdir(parents=True)
    assert run_installer(world) == 2
    assert [p.name for p in target.iterdir()] == [OWNERSHIP]
    assert "not a regular file" in capsys.readouterr().err


def test_missing_project_directory_exits_2_and_creates_nothing(world, capsys):
    missing = world.project / "typo"
    assert ia.main(["--project", str(missing)], agents_dir=world.agents) == 2
    assert not missing.exists()
    assert "project directory does not exist" in capsys.readouterr().err


def test_namespaced_rewrite_names_a_file_that_is_not_utf8():
    with pytest.raises(ia.InstallError, match="critic.toml: not valid UTF-8"):
        ia.namespaced_bytes(b"\xff\xfe", "tk", "critic.toml")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX modes")
def test_installed_files_are_world_readable(world):
    run_installer(world)
    target = target_dir(world)
    modes = {p.name: p.stat().st_mode & 0o777 for p in target.iterdir()}
    assert set(modes.values()) == {0o644}, modes


def test_directory_is_synced_before_the_ownership_file(world, monkeypatch):
    events: list[str] = []
    real_write = ia._atomic_write
    monkeypatch.setattr(ia, "_sync_dir", lambda path: events.append("sync"))

    def spy(path: Path, data: bytes) -> None:
        events.append(path.name)
        real_write(path, data)

    monkeypatch.setattr(ia, "_atomic_write", spy)
    run_installer(world)
    assert events[-2:] == ["sync", OWNERSHIP]


def test_uninstall_after_the_user_deleted_a_recorded_file(world):
    run_installer(world)
    (target_dir(world) / "qa.toml").unlink()
    assert run_installer(world, "--uninstall") == 0
    assert not list(target_dir(world).glob("*.toml"))
    assert not (target_dir(world) / OWNERSHIP).exists()


def test_a_second_uninstall_with_no_record_is_a_no_op(world):
    assert run_installer(world, "--uninstall") == 0
    assert not target_dir(world).exists()


@pytest.mark.parametrize("path", sorted(SHIPPED_DIR.glob("*.toml")), ids=lambda p: p.stem)
def test_namespaced_rewrite_works_on_every_shipped_file(path):
    """The installer's name-line contract with the generator, checked on real output."""
    rewritten = ia.namespaced_bytes(path.read_bytes(), "tk", path.name)
    parsed = tomllib.loads(rewritten.decode("utf-8"))
    assert parsed["name"] == f"tk-{path.stem}"
    assert (
        parsed["developer_instructions"]
        == (tomllib.loads(path.read_text(encoding="utf-8"))["developer_instructions"])
    )


def test_cli_module_exit_code_for_missing_home(monkeypatch, world):
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: (_ for _ in ()).throw(RuntimeError("no home")))
    assert ia.main(["--user"], agents_dir=world.agents) == 2


def test_uninstall_with_no_record_says_so(world, capsys):
    assert run_installer(world, "--uninstall") == 0
    out = capsys.readouterr().out
    assert "nothing to remove" in out and "Applied" not in out


def test_directory_sync_excuses_only_an_unsupported_file_system(tmp_path, monkeypatch):
    import errno

    for code in (errno.EINVAL, errno.ENOTSUP):
        monkeypatch.setattr(
            ia.os, "fsync", lambda fd, code=code: (_ for _ in ()).throw(OSError(code, "x"))
        )
        ia._sync_dir(tmp_path)  # excused
    monkeypatch.setattr(
        ia.os, "fsync", lambda fd: (_ for _ in ()).throw(OSError(errno.EIO, "disk"))
    )
    if hasattr(ia.os, "O_DIRECTORY"):
        with pytest.raises(OSError):
            ia._sync_dir(tmp_path)


def test_io_failure_message_says_how_to_repair(world, monkeypatch, capsys):
    def boom(path, data):
        raise OSError(28, "No space left on device", "qa.toml")

    monkeypatch.setattr(ia, "_atomic_write", boom)
    assert run_installer(world) == 3
    assert "Rerun to repair" in capsys.readouterr().err


def test_summary_counts_a_namespaced_install_once(world, capsys):
    target = target_dir(world)
    target.mkdir(parents=True)
    (target / "qa.toml").write_bytes(agent_bytes("qa", "theirs"))
    assert run_installer(world, "--namespace", "tk") == 0
    assert "Summary: installed 3," in capsys.readouterr().out

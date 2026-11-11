"""``src/codex/install_agents.py``: ownership-tracked install of the Codex agents."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys

import pytest

from tests.codex.conftest import (
    OWNERSHIP,
    SCRIPT,
    agent_bytes,
    ia,
    read_record,
    run_installer,
    target_dir,
    trust_project,
    write_shipped,
)


def test_fresh_install_writes_all_agents_and_ownership(world, capsys):
    assert run_installer(world) == 0
    target = target_dir(world)
    assert sorted(p.name for p in target.glob("*.toml")) == [
        "architect.toml",
        "critic.toml",
        "qa.toml",
    ]
    files = read_record(world)["files"]
    assert files["qa.toml"] == hashlib.sha256((target / "qa.toml").read_bytes()).hexdigest()
    assert "installed 3" in capsys.readouterr().out


def test_rerun_is_idempotent(world, capsys):
    run_installer(world)
    before = {p.name: p.read_bytes() for p in target_dir(world).iterdir()}
    capsys.readouterr()
    assert run_installer(world) == 0
    assert {p.name: p.read_bytes() for p in target_dir(world).iterdir()} == before
    assert "skipped 3" in capsys.readouterr().out


def test_upgrade_overwrites_an_owned_unedited_file(world):
    run_installer(world)
    write_shipped(world.agents, architect="a2", critic="c1", qa="q1")
    assert run_installer(world) == 0
    assert b"a2" in (target_dir(world) / "architect.toml").read_bytes()


def test_dropped_owned_file_is_removed_and_unrecorded_one_stays(world):
    run_installer(world)
    (target_dir(world) / "mine.toml").write_bytes(agent_bytes("mine"))
    write_shipped(world.agents, architect="a1", critic="c1")
    assert run_installer(world) == 0
    assert not (target_dir(world) / "qa.toml").exists()
    assert (target_dir(world) / "mine.toml").exists()
    assert "qa.toml" not in read_record(world)["files"]


def test_dropped_owned_file_that_was_edited_is_left_with_warning(world, capsys):
    run_installer(world)
    (target_dir(world) / "qa.toml").write_bytes(agent_bytes("qa", "edited"))
    write_shipped(world.agents, architect="a1", critic="c1")
    capsys.readouterr()
    assert run_installer(world) == 0
    assert b"edited" in (target_dir(world) / "qa.toml").read_bytes()
    assert "qa.toml was edited" in capsys.readouterr().err


def test_user_edited_owned_file_is_a_conflict_and_nothing_is_written(world, capsys):
    run_installer(world)
    (target_dir(world) / "critic.toml").write_bytes(agent_bytes("critic", "mine"))
    write_shipped(world.agents, architect="a9", critic="c1", qa="q1")
    assert run_installer(world) == 1
    assert b"mine" in (target_dir(world) / "critic.toml").read_bytes()
    assert b"a9" not in (target_dir(world) / "architect.toml").read_bytes()
    assert "CONFLICT: critic.toml" in capsys.readouterr().err


def test_unowned_same_name_file_refuses_and_writes_nothing(world, capsys):
    target = target_dir(world)
    target.mkdir(parents=True)
    (target / "qa.toml").write_bytes(agent_bytes("qa", "theirs"))
    assert run_installer(world) == 1
    assert sorted(p.name for p in target.iterdir()) == ["qa.toml"]
    assert "CONFLICT: qa.toml" in capsys.readouterr().err


def test_directory_under_an_agent_name_is_a_conflict_and_nothing_is_written(world, capsys):
    target = target_dir(world)
    (target / "qa.toml").mkdir(parents=True)
    assert run_installer(world) == 1
    assert sorted(p.name for p in target.iterdir()) == ["qa.toml"]
    assert "CONFLICT: qa.toml" in capsys.readouterr().err


def test_project_and_user_are_mutually_exclusive(world):
    with pytest.raises(SystemExit) as exc:
        ia.main(["--project", str(world.project), "--user"], agents_dir=world.agents)
    assert exc.value.code == 2


def test_user_install_honors_codex_home(world):
    assert run_installer(world, "--user", project=False) == 0
    assert (world.home / "agents" / "qa.toml").is_file()
    assert (world.home / "agents" / OWNERSHIP).is_file()
    assert not (world.project / ".codex").exists()


def test_user_install_falls_back_to_home_dot_codex(world, monkeypatch, tmp_path):
    monkeypatch.delenv("CODEX_HOME")
    monkeypatch.setattr(ia.Path, "home", classmethod(lambda cls: tmp_path / "fakehome"))
    assert run_installer(world, "--user", project=False) == 0
    assert (tmp_path / "fakehome" / ".codex" / "agents" / "qa.toml").is_file()


def test_trust_warning_present_when_project_untrusted(world, capsys):
    assert run_installer(world) == 0
    assert "trusted projects" in capsys.readouterr().err


def test_trust_warning_absent_when_project_trusted(world, capsys):
    trust_project(world)
    assert run_installer(world) == 0
    assert "trusted" not in capsys.readouterr().err


def test_trust_warning_present_when_trust_level_is_not_trusted(world, capsys):
    (world.home / "config.toml").write_text(
        f'[projects."{world.project}"]\ntrust_level = "untrusted"\n', encoding="utf-8"
    )
    run_installer(world)
    assert "trusted projects" in capsys.readouterr().err


def test_user_install_never_warns_about_trust(world, capsys):
    run_installer(world, "--user", project=False)
    assert "trusted" not in capsys.readouterr().err


def test_dry_run_writes_nothing(world, capsys):
    assert run_installer(world, "--dry-run") == 0
    assert not (world.project / ".codex").exists()
    assert "dry run" in capsys.readouterr().out


def test_write_order_agents_before_ownership(world, monkeypatch):
    order: list[str] = []
    real = ia._atomic_write
    monkeypatch.setattr(ia, "_atomic_write", lambda p, d: (order.append(p.name), real(p, d)))
    run_installer(world)
    assert order[-1] == OWNERSHIP and OWNERSHIP not in order[:-1] and len(order) == 4


def test_crash_before_ownership_write_self_heals_by_adopting(world):
    """Agent files landed, the ownership file did not: identical bytes are adopted."""
    target = target_dir(world)
    target.mkdir(parents=True)
    for p in world.agents.glob("*.toml"):
        shutil.copy(p, target / p.name)
    assert run_installer(world) == 0
    assert set(read_record(world)["files"]) == {"architect.toml", "critic.toml", "qa.toml"}


def test_unrecorded_file_with_different_bytes_is_not_adopted(world):
    """Negative control for adoption: only byte-identical files are adopted."""
    target = target_dir(world)
    target.mkdir(parents=True)
    (target / "qa.toml").write_bytes(agent_bytes("qa", "other"))
    assert run_installer(world) == 1


def test_uninstall_removes_owned_unedited_and_the_ownership_file(world):
    run_installer(world)
    (target_dir(world) / "mine.toml").write_bytes(agent_bytes("mine"))
    assert run_installer(world, "--uninstall") == 0
    assert sorted(p.name for p in target_dir(world).iterdir()) == ["mine.toml"]


def test_uninstall_leaves_edited_files_and_keeps_their_record(world, capsys):
    run_installer(world)
    (target_dir(world) / "qa.toml").write_bytes(agent_bytes("qa", "edited"))
    capsys.readouterr()
    assert run_installer(world, "--uninstall") == 0
    assert not (target_dir(world) / "critic.toml").exists()
    assert (target_dir(world) / "qa.toml").exists()
    assert list(read_record(world)["files"]) == ["qa.toml"]
    assert "qa.toml was edited" in capsys.readouterr().err


def test_uninstall_without_ownership_touches_nothing(world):
    target = target_dir(world)
    target.mkdir(parents=True)
    (target / "qa.toml").write_bytes(agent_bytes("qa", "theirs"))
    assert run_installer(world, "--uninstall") == 0
    assert (target / "qa.toml").read_bytes() == agent_bytes("qa", "theirs")


def test_uninstall_dry_run_removes_nothing(world):
    run_installer(world)
    assert run_installer(world, "--uninstall", "--dry-run") == 0
    assert (target_dir(world) / "qa.toml").exists()


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
    target = target_dir(world)
    target.mkdir(parents=True)
    (target / OWNERSHIP).write_text(bad)
    assert run_installer(world) == 2
    assert "ownership file" in capsys.readouterr().err


def test_symlinked_target_is_a_conflict(world, tmp_path):
    target = target_dir(world)
    target.mkdir(parents=True)
    outside = tmp_path / "outside.toml"
    outside.write_bytes(agent_bytes("qa"))
    (target / "qa.toml").symlink_to(outside)
    assert run_installer(world) == 1
    assert outside.read_bytes() == agent_bytes("qa")


def test_missing_or_empty_agents_dir_exits_2(world, tmp_path, capsys):
    assert ia.main(["--project", str(world.project)], agents_dir=tmp_path / "none") == 2
    (tmp_path / "empty").mkdir()
    assert ia.main(["--project", str(world.project)], agents_dir=tmp_path / "empty") == 2


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
    assert (target_dir(world) / "qa.toml").is_file()
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


def test_trust_check_without_tomllib_warns_instead_of_guessing(world, monkeypatch):
    monkeypatch.setattr(ia, "tomllib", None)
    assert "without Python 3.11+" in ia.trust_warning(world.project)


def test_recorded_file_deleted_by_the_user_is_dropped_from_the_record(world):
    run_installer(world)
    (target_dir(world) / "qa.toml").unlink()
    write_shipped(world.agents, architect="a1", critic="c1")
    assert run_installer(world) == 0
    assert "qa.toml" not in read_record(world)["files"]


def test_failed_replace_exits_3_and_leaves_no_temp_file_or_ownership(world, monkeypatch, capsys):
    def boom(src, dst):
        raise OSError(28, "No space left on device", str(dst))

    monkeypatch.setattr(ia.os, "replace", boom)
    assert run_installer(world) == 3
    assert [p.name for p in target_dir(world).iterdir()] == []
    err = capsys.readouterr().err
    assert "No space left on device" in err and "architect.toml" in err
    assert "Traceback" not in err


def test_unreadable_target_exits_3_with_the_path(world, monkeypatch, capsys):
    real = ia.Path.read_bytes

    def deny(self):
        if self.name == "qa.toml" and self.parent.name == "agents" and "proj" in str(self):
            raise PermissionError(13, "Permission denied", str(self))
        return real(self)

    target_dir(world).mkdir(parents=True)
    (target_dir(world) / "qa.toml").write_bytes(agent_bytes("qa"))
    monkeypatch.setattr(ia.Path, "read_bytes", deny)
    assert run_installer(world) == 3
    assert "qa.toml" in capsys.readouterr().err


def test_a_clean_run_never_returns_3(world):
    """Negative control for the OSError handler."""
    assert run_installer(world) == 0


def test_module_entry_point_exits_with_main_status(world, tmp_path):
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True, check=False
    )
    assert done.returncode == 0 and "--namespace" in done.stdout

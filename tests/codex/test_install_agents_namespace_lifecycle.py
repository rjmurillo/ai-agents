"""``install_agents.py``: namespaced copies after a crash, a delete, or a name clash."""

from __future__ import annotations

from tests.codex.conftest import (
    OWNERSHIP,
    agent_bytes,
    ia,
    make_symlink,
    read_record,
    run_installer,
    target_dir,
    write_shipped,
)


def _namespaced_world(world):
    target = target_dir(world)
    target.mkdir(parents=True)
    (target / "qa.toml").write_bytes(agent_bytes("qa", "theirs"))
    assert run_installer(world, "--namespace", "tk") == 0
    return target


def test_interrupted_namespaced_upgrade_heals_on_the_next_run(world, capsys):
    """New bytes on disk, old hash on record: adopt the copy, do not call it an edit."""
    target = _namespaced_world(world)
    write_shipped(world.agents, architect="a1", critic="c1", qa="q2")
    (target / "tk-qa.toml").write_bytes(
        ia.namespaced_bytes(agent_bytes("qa", "q2"), "tk", "qa.toml")
    )
    capsys.readouterr()
    assert run_installer(world) == 0
    err = capsys.readouterr().err
    assert "edited after install" not in err
    assert (
        ia.sha256_hex((target / "tk-qa.toml").read_bytes())
        == read_record(world)["files"]["tk-qa.toml"]
    )


def test_a_real_edit_to_the_namespaced_copy_is_still_kept(world, capsys):
    """Negative control for the interrupted-upgrade test."""
    target = _namespaced_world(world)
    write_shipped(world.agents, architect="a1", critic="c1", qa="q2")
    (target / "tk-qa.toml").write_bytes(agent_bytes("tk-qa", "my own change"))
    capsys.readouterr()
    assert run_installer(world) == 0
    assert "tk-qa.toml was edited after install" in capsys.readouterr().err
    assert b"my own change" in (target / "tk-qa.toml").read_bytes()


def test_a_deleted_namespaced_copy_is_not_revived_under_another_prefix(world):
    target = _namespaced_world(world)
    (target / "tk-qa.toml").unlink()
    assert run_installer(world, "--namespace", "zz") == 0
    assert (target / "zz-qa.toml").is_file()
    assert not (target / "tk-qa.toml").exists()
    assert "tk-qa.toml" not in read_record(world)["files"]


def test_a_namespaced_name_that_is_a_shipped_agent_is_refused(world, capsys):
    write_shipped(world.agents, **{"a-b": "ab", "b": "bb"})
    target = target_dir(world)
    target.mkdir(parents=True)
    (target / "b.toml").write_bytes(agent_bytes("b", "theirs"))
    assert run_installer(world, "--namespace", "a") == 1
    assert "also a shipped agent" in capsys.readouterr().err
    assert not (target / OWNERSHIP).exists()


def test_a_symlink_does_not_stand_in_for_a_namespaced_copy(world, capsys):
    target = _namespaced_world(world)
    (target / "tk-qa.toml").unlink()
    make_symlink(target / "tk-qa.toml", world.project / "nowhere.toml")
    assert run_installer(world) == 1
    assert "qa.toml" in capsys.readouterr().err


def test_a_shipped_file_that_is_not_utf8_is_refused_before_any_write(world, capsys):
    (world.agents / "qa.toml").write_bytes(b"\xff\xfe")
    assert run_installer(world) == 2
    assert not target_dir(world).exists()
    assert "qa.toml: not a valid TOML agent file" in capsys.readouterr().err


def test_a_shipped_file_that_is_not_toml_is_refused(world, capsys):
    (world.agents / "qa.toml").write_text("name = = broken\n", encoding="utf-8")
    assert run_installer(world) == 2
    assert not target_dir(world).exists()

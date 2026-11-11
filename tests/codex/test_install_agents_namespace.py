"""``install_agents.py`` ``--namespace`` behavior: prefixed copies and their lifecycle."""

from __future__ import annotations

import pytest
import tomllib

from tests.codex.conftest import (
    OWNERSHIP,
    agent_bytes,
    ia,
    read_record,
    run_installer,
    target_dir,
    write_shipped,
)


def test_namespace_installs_prefixed_file_with_prefixed_parsed_name(world, capsys):
    target = target_dir(world)
    target.mkdir(parents=True)
    (target / "qa.toml").write_bytes(agent_bytes("qa", "theirs"))
    assert run_installer(world, "--namespace", "tk") == 0
    parsed = tomllib.loads((target / "tk-qa.toml").read_text(encoding="utf-8"))
    assert parsed["name"] == "tk-qa"
    assert parsed["developer_instructions"] == "q1"
    assert b"theirs" in (target / "qa.toml").read_bytes()
    assert "tk-qa.toml" in read_record(world)["files"]
    err = capsys.readouterr().err
    assert "hand work to `qa`" in err and "your own `qa`" in err


def test_namespaced_file_survives_a_later_plain_run_and_upgrades(world):
    target = target_dir(world)
    target.mkdir(parents=True)
    (target / "qa.toml").write_bytes(agent_bytes("qa", "theirs"))
    run_installer(world, "--namespace", "tk")
    write_shipped(world.agents, architect="a1", critic="c1", qa="q2")
    assert run_installer(world) == 0
    assert (
        tomllib.loads((target / "tk-qa.toml").read_text(encoding="utf-8"))["developer_instructions"]
        == "q2"
    )
    assert b"theirs" in (target / "qa.toml").read_bytes()


def test_deleted_namespaced_copy_is_reinstalled_and_reruns_agree(world):
    target = target_dir(world)
    target.mkdir(parents=True)
    (target / "qa.toml").write_bytes(agent_bytes("qa", "theirs"))
    run_installer(world, "--namespace", "tk")
    (target / "tk-qa.toml").unlink()
    # A recorded entry alone does not excuse the clash: the copy must be on disk.
    assert run_installer(world) == 1
    assert not (target / "tk-qa.toml").exists()
    assert run_installer(world, "--namespace", "tk") == 0
    assert tomllib.loads((target / "tk-qa.toml").read_text(encoding="utf-8"))["name"] == "tk-qa"
    assert "tk-qa.toml" in read_record(world)["files"]
    assert run_installer(world) == 0
    assert b"theirs" in (target / "qa.toml").read_bytes()


def test_namespaced_name_collision_refuses(world, capsys):
    target = target_dir(world)
    target.mkdir(parents=True)
    (target / "qa.toml").write_bytes(agent_bytes("qa"))
    (target / "tk-qa.toml").write_bytes(agent_bytes("tk-qa", "theirs"))
    assert run_installer(world, "--namespace", "tk") == 1
    assert not (target / OWNERSHIP).exists()
    assert "tk-qa.toml" in capsys.readouterr().err


def test_no_namespace_warning_without_conflict(world, capsys):
    run_installer(world, "--namespace", "tk")
    assert "hand work to" not in capsys.readouterr().err


@pytest.mark.parametrize("prefix", ["", "Tk", "-tk", "t k", "t/k", "t.k"])
def test_invalid_prefix_exits_2(world, prefix):
    with pytest.raises(SystemExit) as exc:
        run_installer(world, "--namespace", prefix)
    assert exc.value.code == 2


def test_uninstall_removes_namespaced_files(world):
    target = target_dir(world)
    target.mkdir(parents=True)
    (target / "qa.toml").write_bytes(agent_bytes("qa", "theirs"))
    run_installer(world, "--namespace", "tk")
    assert run_installer(world, "--uninstall") == 0
    assert not (target / "tk-qa.toml").exists()
    assert (target / "qa.toml").exists()


def test_uninstall_with_namespace_is_a_usage_error(world):
    with pytest.raises(SystemExit) as exc:
        run_installer(world, "--uninstall", "--namespace", "tk")
    assert exc.value.code == 2


def test_namespaced_rewrite_rejects_a_file_without_a_name_first_line():
    with pytest.raises(ia.InstallError):
        ia.namespaced_bytes(b'description = "x"\nname = "a"\n', "tk", "a.toml")


def test_namespaced_rewrite_rejects_invalid_toml():
    with pytest.raises(ia.InstallError, match="invalid TOML or misnamed"):
        ia.namespaced_bytes(b'name = "a"\nbroken = \n', "tk", "a.toml")


def test_namespaced_rewrite_without_tomllib_still_prefixes(monkeypatch):
    monkeypatch.setattr(ia, "tomllib", None)
    assert ia.namespaced_bytes(agent_bytes("a"), "tk", "a.toml").startswith(b'name = "tk-a"\n')


def test_edited_namespaced_file_is_kept_with_its_record(world, capsys):
    target = target_dir(world)
    target.mkdir(parents=True)
    (target / "qa.toml").write_bytes(agent_bytes("qa", "theirs"))
    run_installer(world, "--namespace", "tk")
    (target / "tk-qa.toml").write_bytes(agent_bytes("tk-qa", "edited"))
    capsys.readouterr()
    assert run_installer(world) == 0
    assert b"edited" in (target / "tk-qa.toml").read_bytes()
    assert read_record(world)["namespaced"] == {"tk-qa.toml": "qa.toml"}
    assert "tk-qa.toml was edited" in capsys.readouterr().err


def test_uninstall_keeps_the_source_of_an_edited_namespaced_file(world):
    target = target_dir(world)
    target.mkdir(parents=True)
    (target / "qa.toml").write_bytes(agent_bytes("qa", "theirs"))
    run_installer(world, "--namespace", "tk")
    (target / "tk-qa.toml").write_bytes(agent_bytes("tk-qa", "edited"))
    assert run_installer(world, "--uninstall") == 0
    assert read_record(world)["namespaced"] == {"tk-qa.toml": "qa.toml"}


def _clash_then_namespace(world):
    target = target_dir(world)
    target.mkdir(parents=True)
    (target / "qa.toml").write_bytes(agent_bytes("qa", "theirs"))
    run_installer(world, "--namespace", "tk")
    (target / "qa.toml").unlink()
    return target


def test_plain_agent_reinstalled_removes_the_unedited_namespaced_copy(world, capsys):
    target = _clash_then_namespace(world)
    assert (target / "tk-qa.toml").is_file()
    assert run_installer(world) == 0
    assert (target / "qa.toml").read_bytes() == agent_bytes("qa", "q1")
    assert not (target / "tk-qa.toml").exists()
    record = read_record(world)
    assert "tk-qa.toml" not in record["files"] and "namespaced" not in record
    assert "tk-qa.toml (plain agent is installed)" in capsys.readouterr().out
    assert run_installer(world) == 0  # idempotent afterwards


def test_plain_agent_reinstalled_keeps_an_edited_namespaced_copy_and_warns(world, capsys):
    target = _clash_then_namespace(world)
    (target / "tk-qa.toml").write_bytes(agent_bytes("tk-qa", "edited"))
    capsys.readouterr()
    assert run_installer(world) == 0
    assert (target / "qa.toml").is_file()
    assert b"edited" in (target / "tk-qa.toml").read_bytes()
    assert read_record(world)["namespaced"] == {"tk-qa.toml": "qa.toml"}
    assert "tk-qa.toml was edited" in capsys.readouterr().err


def test_namespaced_copy_stays_while_the_clash_persists(world):
    """Negative control: with the user's file still there, the copy is kept."""
    target = target_dir(world)
    target.mkdir(parents=True)
    (target / "qa.toml").write_bytes(agent_bytes("qa", "theirs"))
    run_installer(world, "--namespace", "tk")
    assert run_installer(world) == 0
    assert (target / "tk-qa.toml").is_file() and (target / "qa.toml").read_bytes().endswith(
        b'"theirs"\n'
    )


def _edited_plain_then_namespace(world, prefix):
    """The user edits an owned qa.toml, then installs with --namespace PREFIX."""
    target = target_dir(world)
    assert run_installer(world) == 0
    (target / "qa.toml").write_bytes(agent_bytes("qa", "my edit"))
    assert run_installer(world, "--namespace", prefix) == 0
    assert (target / f"{prefix}-qa.toml").is_file()
    return target


@pytest.mark.parametrize("prefix", ["tk", "aa"], ids=["after-plain", "before-plain"])
def test_a_plain_run_keeps_the_namespaced_copy_while_the_users_edit_remains(world, prefix, capsys):
    """qa.toml sorts before tk-qa.toml and after aa-qa.toml; the result must not depend on it."""
    target = _edited_plain_then_namespace(world, prefix)
    capsys.readouterr()
    for _ in range(2):
        assert run_installer(world) == 0
        assert (target / f"{prefix}-qa.toml").is_file()
        assert (target / "qa.toml").read_bytes() == agent_bytes("qa", "my edit")
    assert read_record(world)["namespaced"] == {f"{prefix}-qa.toml": "qa.toml"}
    out = capsys.readouterr()
    assert f"removed: {prefix}-qa.toml" not in out.out
    assert "qa.toml was edited" in out.err


@pytest.mark.parametrize("prefix", ["tk", "aa"])
def test_namespaced_copy_goes_once_the_users_edited_file_is_deleted(world, prefix):
    """Negative control: with the edited file gone the plain agent installs and the copy leaves."""
    target = _edited_plain_then_namespace(world, prefix)
    (target / "qa.toml").unlink()
    assert run_installer(world) == 0
    assert (target / "qa.toml").read_bytes() == agent_bytes("qa", "q1")
    assert not (target / f"{prefix}-qa.toml").exists()

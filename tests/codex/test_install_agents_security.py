"""``install_agents.py``: untrusted ownership file and symlinked targets (CWE-20, CWE-59)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import tomllib

from tests.codex.conftest import (
    OWNERSHIP,
    agent_bytes,
    ia,
    run_installer,
    target_dir,
)

GOOD_HASH = "a" * 64


def _plant_ownership(world, payload: dict) -> Path:
    target = target_dir(world)
    target.mkdir(parents=True, exist_ok=True)
    (target / OWNERSHIP).write_text(json.dumps(payload), encoding="utf-8")
    return target


@pytest.mark.parametrize(
    "bad_name",
    [
        'a"b.toml',
        "a\nb.toml",
        "a b.toml",
        "a'b.toml",
        "a$b.toml",
        "é.toml",
        ".hidden.toml",
        "a\\b.toml",
    ],
)
def test_ownership_name_with_unsafe_characters_is_rejected(world, bad_name, capsys):
    target = _plant_ownership(world, {"files": {bad_name: GOOD_HASH}})
    assert run_installer(world) == 2
    assert [p.name for p in target.iterdir()] == [OWNERSHIP]
    assert "ownership file" in capsys.readouterr().err


@pytest.mark.parametrize(
    "bad_hash", ["h", "symlink", "not-a-file", "A" * 64, "a" * 63, "a" * 64 + "\n", 5]
)
def test_ownership_non_hex_hash_is_rejected_and_nothing_written(world, bad_hash):
    target = _plant_ownership(world, {"files": {"qa.toml": bad_hash}})
    assert run_installer(world) == 2
    assert [p.name for p in target.iterdir()] == [OWNERSHIP]


def test_ownership_valid_hash_is_accepted(world):
    _plant_ownership(world, {"files": {"gone.toml": GOOD_HASH}})
    assert run_installer(world) == 0


def test_uninstall_with_not_a_file_marker_cannot_unlink_a_directory(world):
    target = _plant_ownership(world, {"files": {"victim.toml": "not-a-file"}})
    (target / "victim.toml").mkdir()
    (target / "victim.toml" / "keep.txt").write_text("x")
    assert run_installer(world, "--uninstall") == 2
    assert (target / "victim.toml" / "keep.txt").is_file()


def test_uninstall_with_symlink_marker_cannot_unlink_a_symlink(world, tmp_path):
    target = _plant_ownership(world, {"files": {"victim.toml": "symlink"}})
    outside = tmp_path / "outside.toml"
    outside.write_text("x")
    (target / "victim.toml").symlink_to(outside)
    assert run_installer(world, "--uninstall") == 2
    assert (target / "victim.toml").is_symlink()


@pytest.mark.parametrize(
    ("entry_name", "source"),
    [
        ('tk-q"a.toml', 'q"a.toml'),
        ("tk-qa.toml", "qa.toml\n"),
        ("TK-qa.toml", "qa.toml"),
        ("tk-qa.toml", "other.toml"),
        ("-qa.toml", "qa.toml"),
        ("qa.toml", "qa.toml"),
        ("t k-qa.toml", "qa.toml"),
    ],
)
def test_crafted_namespaced_entry_is_rejected(world, entry_name, source):
    target = _plant_ownership(
        world, {"files": {entry_name: GOOD_HASH}, "namespaced": {entry_name: source}}
    )
    assert run_installer(world) == 2
    assert [p.name for p in target.iterdir()] == [OWNERSHIP]


def test_well_formed_namespaced_entry_is_accepted(world):
    _plant_ownership(
        world, {"files": {"tk-qa.toml": GOOD_HASH}, "namespaced": {"tk-qa.toml": "qa.toml"}}
    )
    assert run_installer(world) == 0


def test_namespaced_name_is_built_from_prefix_and_file_stem_only():
    data = b'name = "evil-name"\ndescription = "d"\n'
    out = ia.namespaced_bytes(data, "tk", "qa.toml")
    assert tomllib.loads(out.decode())["name"] == "tk-qa"


def test_namespaced_bytes_rejects_a_name_line_carrying_an_escaped_quote():
    data = b'name = "x\\" injected"\ndescription = "d"\n'
    with pytest.raises(ia.InstallError, match="first line"):
        ia.namespaced_bytes(data, "tk", "qa.toml")


@pytest.mark.parametrize("prefix", ['t"k', "t\nk", "Tk", "", "tk\n"])
def test_namespaced_bytes_rejects_an_invalid_prefix(prefix):
    with pytest.raises(ia.InstallError, match="prefix"):
        ia.namespaced_bytes(agent_bytes("qa"), prefix, "qa.toml")


def test_namespaced_bytes_rejects_an_unsafe_file_name():
    with pytest.raises(ia.InstallError, match="unsafe"):
        ia.namespaced_bytes(agent_bytes("qa"), "tk", 'q"a.toml')


def test_trailing_newline_prefix_is_a_usage_error(world):
    with pytest.raises(SystemExit) as exc:
        run_installer(world, "--namespace", "tk\n")
    assert exc.value.code == 2


def test_ownership_file_symlink_is_refused(world, tmp_path):
    target = target_dir(world)
    target.mkdir(parents=True)
    outside = tmp_path / "evil.json"
    outside.write_text(json.dumps({"files": {}}))
    (target / OWNERSHIP).symlink_to(outside)
    assert run_installer(world) == 2


def test_project_dot_codex_symlink_is_refused_and_nothing_written(world, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (world.project / ".codex").symlink_to(elsewhere)
    assert run_installer(world) == 2
    assert list(elsewhere.iterdir()) == []


def test_project_agents_symlink_is_refused_and_nothing_written(world, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (world.project / ".codex").mkdir()
    (world.project / ".codex" / "agents").symlink_to(elsewhere)
    assert run_installer(world) == 2
    assert list(elsewhere.iterdir()) == []


def test_user_agents_symlink_is_refused_and_nothing_written(world, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (world.home / "agents").symlink_to(elsewhere)
    assert run_installer(world, "--user", project=False) == 2
    assert list(elsewhere.iterdir()) == []


def test_symlink_refusal_also_covers_dry_run_and_uninstall(world, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (world.project / ".codex").symlink_to(elsewhere)
    assert run_installer(world, "--dry-run") == 2
    assert run_installer(world, "--uninstall") == 2


def test_a_symlinked_project_root_itself_is_allowed(world, tmp_path):
    """Negative control: only components below the root are checked."""
    link = tmp_path / "proj-link"
    link.symlink_to(world.project)
    assert ia.main(["--project", str(link)], agents_dir=world.agents) == 0
    assert (world.project / ".codex" / "agents" / "qa.toml").is_file()

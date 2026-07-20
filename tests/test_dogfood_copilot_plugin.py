"""Tests for the Copilot dogfood-install helper (ADR-083 item 3 need, copy-only; #3222)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "dev" / "dogfood_copilot_plugin.py"

_spec = importlib.util.spec_from_file_location("dogfood_copilot_plugin", _SCRIPT)
assert _spec is not None and _spec.loader is not None
dogfood = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dogfood)


def _make_plugin_root(path: Path, version: str) -> Path:
    """Create a minimal plugin root with a manifest carrying version."""
    (path / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    (path / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "project-toolkit", "version": version}), encoding="utf-8"
    )
    (path / "hooks").mkdir(exist_ok=True)
    return path


def _require_symlinks(tmp_path: Path) -> None:
    """Skip when the platform forbids symlink creation (Windows without privilege)."""
    probe = tmp_path / "_symlink_probe"
    try:
        probe.symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks not permitted on this platform")
    finally:
        if probe.is_symlink():
            probe.unlink()


@pytest.fixture
def source(tmp_path: Path) -> Path:
    return _make_plugin_root(tmp_path / "src" / "copilot-cli", "9.9.9")


@pytest.fixture
def target(tmp_path: Path) -> Path:
    return tmp_path / "installed" / "ai-agents" / "project-toolkit"


# --- install (positive) ---


def test_install_creates_copy(source: Path, target: Path) -> None:
    note = dogfood.dogfood_install(source, target)
    assert target.is_dir()
    assert not target.is_symlink()
    assert (target / ".claude-plugin" / "plugin.json").is_file()
    assert dogfood._plugin_version(target) == "9.9.9"
    assert "copied" in note


def test_install_excludes_local_caches(source: Path, target: Path) -> None:
    cache_dir = source / "__pycache__"
    cache_dir.mkdir()
    (cache_dir / "mod.cpython-314.pyc").write_bytes(b"\x00")
    (source / "skills" / ".ruff_cache").mkdir(parents=True)
    (source / "skills" / ".ruff_cache" / "CACHEDIR.TAG").write_text("x", encoding="utf-8")
    (source / "stale.pyc").write_bytes(b"\x00")

    dogfood.dogfood_install(source, target)

    assert not (target / "__pycache__").exists()
    assert not (target / "skills" / ".ruff_cache").exists()
    assert not (target / "stale.pyc").exists()
    assert (target / ".claude-plugin" / "plugin.json").is_file()


def test_install_refreshes_stale_copy(source: Path, target: Path) -> None:
    _make_plugin_root(target, "0.0.1")  # older install
    note = dogfood.dogfood_install(source, target)
    assert dogfood._plugin_version(target) == "9.9.9"
    assert "backed up copy" in note


def test_install_backs_up_existing_copy_once(source: Path, target: Path) -> None:
    _make_plugin_root(target, "0.0.1")
    original = (target / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")

    dogfood.dogfood_install(source, target)  # first install backs up
    dogfood.dogfood_install(source, target)  # second must not clobber the backup

    backup = target.with_name(target.name + ".marketplace-bak")
    assert backup.is_dir()
    assert (backup / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8") == original


def test_install_replaces_prior_symlink(source: Path, target: Path, tmp_path: Path) -> None:
    _require_symlinks(tmp_path)
    other = _make_plugin_root(tmp_path / "other", "1.0.0")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(other, target_is_directory=True)

    note = dogfood.dogfood_install(source, target)

    assert target.is_dir()
    assert not target.is_symlink()
    assert "removed prior symlink" in note


def test_install_survives_dangling_backup_symlink(
    source: Path, target: Path, tmp_path: Path
) -> None:
    _require_symlinks(tmp_path)
    _make_plugin_root(target, "0.0.1")  # a real copy to back up
    backup = target.with_name(target.name + ".marketplace-bak")
    backup.symlink_to(tmp_path / "gone")  # dangling: points nowhere

    note = dogfood.dogfood_install(source, target)

    assert dogfood._plugin_version(target) == "9.9.9"
    assert "backed up copy" in note
    assert backup.is_dir()  # stray link replaced by the real backup
    assert not backup.is_symlink()


def test_install_replaces_corrupt_file_backup(source: Path, target: Path) -> None:
    _make_plugin_root(target, "0.0.1")  # a real copy to back up
    backup = target.with_name(target.name + ".marketplace-bak")
    backup.write_text("not a backup", encoding="utf-8")  # corrupt: a regular file

    note = dogfood.dogfood_install(source, target)

    assert dogfood._plugin_version(target) == "9.9.9"
    assert "backed up copy" in note
    assert backup.is_dir()  # corrupt file replaced by the real backup
    assert dogfood._plugin_version(backup) == "0.0.1"  # prior copy preserved


def test_install_replaces_stray_non_plugin_backup_dir(source: Path, target: Path) -> None:
    _make_plugin_root(target, "0.0.1")  # a real copy to back up
    backup = target.with_name(target.name + ".marketplace-bak")
    backup.mkdir()  # stray directory, not a plugin root
    (backup / "junk.txt").write_text("stray", encoding="utf-8")

    note = dogfood.dogfood_install(source, target)

    assert dogfood._plugin_version(target) == "9.9.9"
    assert "backed up copy" in note
    assert dogfood._plugin_version(backup) == "0.0.1"  # real prior copy backed up
    assert not (backup / "junk.txt").exists()  # stray directory discarded


# --- install (negative) ---


def test_install_rejects_non_plugin_source(tmp_path: Path, target: Path) -> None:
    not_a_plugin = tmp_path / "empty"
    not_a_plugin.mkdir()
    with pytest.raises(ValueError, match="not a plugin root"):
        dogfood.dogfood_install(not_a_plugin, target)


def _write_manifest(root: Path, text: str) -> Path:
    """Write a raw manifest body (possibly malformed) to a plugin root."""
    (root / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    (root / ".claude-plugin" / "plugin.json").write_text(text, encoding="utf-8")
    return root


def test_install_rejects_malformed_manifest(tmp_path: Path, target: Path) -> None:
    bad = _write_manifest(tmp_path / "bad", "{not valid json")
    with pytest.raises(ValueError, match="not a plugin root"):
        dogfood.dogfood_install(bad, target)


def test_install_rejects_non_object_manifest(tmp_path: Path, target: Path) -> None:
    bad = _write_manifest(tmp_path / "list", "[]")
    with pytest.raises(ValueError, match="not a plugin root"):
        dogfood.dogfood_install(bad, target)


def test_install_rejects_manifest_without_name(tmp_path: Path, target: Path) -> None:
    bad = _write_manifest(tmp_path / "noname", json.dumps({"version": "1.0.0"}))
    with pytest.raises(ValueError, match="not a plugin root"):
        dogfood.dogfood_install(bad, target)


def test_install_rejects_malformed_source_before_touching_target(
    source: Path, target: Path, tmp_path: Path
) -> None:
    _make_plugin_root(target, "0.0.1")  # a healthy prior install
    bad = _write_manifest(tmp_path / "bad", "null")
    with pytest.raises(ValueError, match="not a plugin root"):
        dogfood.dogfood_install(bad, target)
    # The bad source must not have disturbed the existing install or made a backup.
    assert dogfood._plugin_version(target) == "0.0.1"
    assert not target.with_name(target.name + ".marketplace-bak").exists()


def test_main_returns_config_error_on_bad_source(monkeypatch, tmp_path: Path, capsys) -> None:
    empty = tmp_path / "src" / "copilot-cli"
    empty.mkdir(parents=True)
    monkeypatch.setattr(dogfood, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(dogfood, "default_target", lambda: tmp_path / "installed" / "x")
    rc = dogfood.main([])
    assert rc == 2
    assert "error:" in capsys.readouterr().err


def test_main_returns_config_error_on_git_failure(monkeypatch, capsys) -> None:
    def _boom() -> Path:
        raise subprocess.CalledProcessError(128, ["git", "rev-parse"])

    monkeypatch.setattr(dogfood, "_repo_root", _boom)
    rc = dogfood.main(["--status"])
    assert rc == 2
    assert "error:" in capsys.readouterr().err


# --- uninstall (positive + restore + no-backup edge) ---


def test_uninstall_restores_backup(source: Path, target: Path) -> None:
    _make_plugin_root(target, "0.0.1")
    dogfood.dogfood_install(source, target)
    note = dogfood.dogfood_uninstall(target)
    assert "restored backup" in note
    assert target.is_dir()
    assert dogfood._plugin_version(target) == "0.0.1"


def test_uninstall_without_backup_advises_reinstall(source: Path, target: Path) -> None:
    dogfood.dogfood_install(source, target)  # no pre-existing copy to back up
    note = dogfood.dogfood_uninstall(target)
    assert "no backup" in note
    assert not target.exists()


def test_uninstall_when_nothing_installed(target: Path) -> None:
    note = dogfood.dogfood_uninstall(target)
    assert "nothing installed" in note


def test_uninstall_removes_regular_file_and_restores_backup(target: Path) -> None:
    backup = _make_plugin_root(target.with_name(target.name + ".marketplace-bak"), "0.0.1")
    assert backup.is_dir()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("stray file", encoding="utf-8")  # target is a plain file

    note = dogfood.dogfood_uninstall(target)

    assert "removed file" in note
    assert target.is_dir()  # backup restored over the removed file
    assert dogfood._plugin_version(target) == "0.0.1"


# --- status (each state) ---


def test_status_reports_current_copy(source: Path, target: Path) -> None:
    dogfood.dogfood_install(source, target)
    status = dogfood.dogfood_status(source, target)
    assert "installed copy" in status
    assert "9.9.9" in status
    assert "re-run" not in status  # matches the shipped version


def test_status_flags_stale_copy(source: Path, target: Path) -> None:
    _make_plugin_root(target, "0.0.1")
    status = dogfood.dogfood_status(source, target)
    assert "re-run --install to refresh" in status


def test_status_reports_not_installed(source: Path, target: Path) -> None:
    assert "not installed" in dogfood.dogfood_status(source, target)


# --- helpers ---


def test_plugin_version_none_without_manifest(tmp_path: Path) -> None:
    assert dogfood._plugin_version(tmp_path) is None


def test_plugin_version_none_on_non_object_manifest(tmp_path: Path) -> None:
    root = _write_manifest(tmp_path / "list", "[1, 2, 3]")
    assert dogfood._plugin_version(root) is None


def test_plugin_version_none_on_malformed_manifest(tmp_path: Path) -> None:
    root = _write_manifest(tmp_path / "bad", "{oops")
    assert dogfood._plugin_version(root) is None


def test_plugin_version_none_when_version_missing(tmp_path: Path) -> None:
    root = _write_manifest(tmp_path / "noversion", json.dumps({"name": "x"}))
    assert dogfood._plugin_version(root) is None


def test_default_target_honors_copilot_home(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path / "cop"))
    resolved = dogfood.default_target()
    assert resolved == tmp_path / "cop" / "installed-plugins" / "ai-agents" / "project-toolkit"


def test_default_target_ignores_empty_copilot_home(monkeypatch) -> None:
    monkeypatch.setenv("COPILOT_HOME", "")
    resolved = dogfood.default_target()
    expected = Path.home() / ".copilot" / "installed-plugins" / "ai-agents" / "project-toolkit"
    assert resolved == expected


def test_default_target_ignores_whitespace_copilot_home(monkeypatch) -> None:
    monkeypatch.setenv("COPILOT_HOME", "   ")
    resolved = dogfood.default_target()
    expected = Path.home() / ".copilot" / "installed-plugins" / "ai-agents" / "project-toolkit"
    assert resolved == expected

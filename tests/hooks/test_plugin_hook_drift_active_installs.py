#!/usr/bin/env python3
"""Tests for the active-install filter in invoke_plugin_hook_drift_check.py (#7227).

Claude Code leaves superseded plugin copies in its cache after an update. The
check reads `installed_plugins.json` and compares only the installs the
harness itself lists, so a stale copy never counts as drift.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HOOKS_DIR = str(Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "SessionStart")
sys.path.insert(0, HOOKS_DIR)

import invoke_plugin_hook_drift_check as drift
import plugin_hook_drift_record as record_module
import plugin_hook_drift_state as state

PLUGIN_NAME = "project-toolkit"
RETIRED_GUARD_COMMAND = (
    'python3 -u "${CLAUDE_PLUGIN_ROOT}/hooks/PreToolUse/invoke_lsp_pre_delegation_guard.py"'
)


@pytest.fixture(autouse=True)
def _isolate_copilot_home(monkeypatch) -> None:
    monkeypatch.delenv("COPILOT_HOME", raising=False)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _make_plugin_root(root: Path, hooks: object, *, name: str = PLUGIN_NAME) -> Path:
    _write_json(root / ".claude-plugin" / "plugin.json", {"name": name})
    if hooks is not None:
        _write_json(root / "hooks" / "hooks.json", {"hooks": hooks})
    return root


def _registration(command: str, *, event: str = "PreToolUse", matcher: str = "Task") -> dict:
    return {event: [{"matcher": matcher, "hooks": [{"type": "command", "command": command}]}]}


def _copilot_registration(command: str, *, event: str = "preToolUse") -> dict:
    return {event: [{"type": "command", "matcher": "task", "bash": command, "timeoutSec": 10}]}


def _make_checkout(project_dir: Path, hooks: object) -> Path:
    _make_plugin_root(project_dir / ".claude", hooks)
    _make_plugin_root(project_dir / "src" / "copilot-cli", hooks)
    return project_dir


def _cache_install(home: Path, version: str, hooks: object) -> Path:
    """One versioned cache copy, laid out as Claude Code's installer does."""
    return _make_plugin_root(
        home / ".claude" / "plugins" / "cache" / "ai-agents" / PLUGIN_NAME / version, hooks
    )


def _write_record(home: Path, payload: object) -> Path:
    record = home / ".claude" / "plugins" / "installed_plugins.json"
    _write_json(record, payload)
    return record


def _record_for(*install_paths: Path, key: str = f"{PLUGIN_NAME}@ai-agents") -> dict:
    return {
        "version": 2,
        "plugins": {
            key: [
                {"scope": "user", "installPath": str(path), "version": path.name}
                for path in install_paths
            ]
        },
    }


def _claude_reports(outcome: state.ScanOutcome) -> list:
    return [report for report in outcome.reports if report.surface == "Claude Code"]


def test_active_install_with_drift_is_reported(tmp_path) -> None:
    project_dir = _make_checkout(tmp_path / "repo", {})
    home = tmp_path / "home"
    active = _cache_install(home, "bbb222", _registration(RETIRED_GUARD_COMMAND))
    _write_record(home, _record_for(active))

    outcome = drift.check_installed_plugins(project_dir, home)

    reports = _claude_reports(outcome)
    assert [report.install_path for report in reports] == [active]
    assert reports[0].has_drift
    assert outcome.notes == []


def test_stale_cache_copy_with_drift_is_ignored(tmp_path) -> None:
    project_dir = _make_checkout(tmp_path / "repo", {})
    home = tmp_path / "home"
    stale = _cache_install(home, "aaa111", _registration(RETIRED_GUARD_COMMAND))
    active = _cache_install(home, "bbb222", {})
    _write_record(home, _record_for(active))

    outcome = drift.check_installed_plugins(project_dir, home)

    reports = _claude_reports(outcome)
    assert [report.install_path for report in reports] == [active]
    assert not reports[0].has_drift
    assert stale not in [report.install_path for report in outcome.reports]
    assert outcome.notes == []


def test_many_stale_copies_do_not_inflate_the_drift_count(tmp_path) -> None:
    project_dir = _make_checkout(tmp_path / "repo", {})
    home = tmp_path / "home"
    for index in range(5):
        _cache_install(home, f"old{index}", _registration(RETIRED_GUARD_COMMAND))
    active = _cache_install(home, "current", {})
    _write_record(home, _record_for(active))

    outcome = drift.check_installed_plugins(project_dir, home)

    assert len(_claude_reports(outcome)) == 1
    assert not any(report.has_drift for report in outcome.reports)


def test_missing_installed_plugins_json_falls_back_to_every_copy(tmp_path) -> None:
    project_dir = _make_checkout(tmp_path / "repo", {})
    home = tmp_path / "home"
    first = _cache_install(home, "aaa111", _registration(RETIRED_GUARD_COMMAND))
    second = _cache_install(home, "bbb222", {})

    outcome = drift.check_installed_plugins(project_dir, home)

    assert sorted(report.install_path for report in _claude_reports(outcome)) == [first, second]
    assert len(outcome.notes) == 1
    assert "not found" in outcome.notes[0]
    assert "\n" not in outcome.notes[0]


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"version": 99, "plugins": {}}, "unknown schema"),
        ({"version": 2, "plugins": []}, "unknown schema"),
        ({"plugins": {}}, "unknown schema"),
        (["not", "an", "object"], "unknown schema"),
    ],
)
def test_unknown_schema_falls_back_with_one_note(tmp_path, payload, expected) -> None:
    project_dir = _make_checkout(tmp_path / "repo", {})
    home = tmp_path / "home"
    install = _cache_install(home, "aaa111", {})
    _write_record(home, payload)

    outcome = drift.check_installed_plugins(project_dir, home)

    assert [report.install_path for report in _claude_reports(outcome)] == [install]
    assert len(outcome.notes) == 1
    assert expected in outcome.notes[0]


def test_unparseable_record_falls_back_without_crashing(tmp_path) -> None:
    project_dir = _make_checkout(tmp_path / "repo", {})
    home = tmp_path / "home"
    install = _cache_install(home, "aaa111", {})
    record = home / ".claude" / "plugins" / "installed_plugins.json"
    record.write_text("{not json", encoding="utf-8")

    outcome = drift.check_installed_plugins(project_dir, home)

    assert [report.install_path for report in _claude_reports(outcome)] == [install]
    assert "unreadable" in outcome.notes[0]


def test_oversized_record_falls_back(tmp_path, monkeypatch) -> None:
    project_dir = _make_checkout(tmp_path / "repo", {})
    home = tmp_path / "home"
    install = _cache_install(home, "aaa111", {})
    _write_record(home, _record_for(install))
    monkeypatch.setattr(record_module, "MAX_RECORD_BYTES", 8)

    outcome = drift.check_installed_plugins(project_dir, home)

    assert [report.install_path for report in _claude_reports(outcome)] == [install]
    assert "too large" in outcome.notes[0]


def test_record_without_this_plugin_reports_no_claude_install(tmp_path) -> None:
    project_dir = _make_checkout(tmp_path / "repo", {})
    home = tmp_path / "home"
    _cache_install(home, "aaa111", _registration(RETIRED_GUARD_COMMAND))
    other = home / ".claude" / "plugins" / "cache" / "mkt" / "other-plugin" / "1.0.0"
    other.mkdir(parents=True)
    _write_record(home, _record_for(other, key="other-plugin@mkt"))

    outcome = drift.check_installed_plugins(project_dir, home)

    assert _claude_reports(outcome) == []
    assert outcome.notes == []


def test_record_path_outside_the_plugin_cache_is_ignored(tmp_path) -> None:
    project_dir = _make_checkout(tmp_path / "repo", {})
    home = tmp_path / "home"
    outside = _make_plugin_root(tmp_path / "elsewhere", _registration(RETIRED_GUARD_COMMAND))
    _write_record(home, _record_for(outside))
    _cache_install(home, "aaa111", {})

    outcome = drift.check_installed_plugins(project_dir, home)

    assert _claude_reports(outcome) == []


def test_record_path_that_is_a_symlink_is_ignored(tmp_path) -> None:
    project_dir = _make_checkout(tmp_path / "repo", {})
    home = tmp_path / "home"
    real = _cache_install(home, "real", {})
    link = real.parent / "linked"
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("cannot create symlink on this platform")
    _write_record(home, _record_for(link))

    assert _claude_reports(drift.check_installed_plugins(project_dir, home)) == []


def test_record_with_malformed_entries_is_tolerated(tmp_path) -> None:
    project_dir = _make_checkout(tmp_path / "repo", {})
    home = tmp_path / "home"
    active = _cache_install(home, "bbb222", {})
    payload = {
        "version": 2,
        "plugins": {
            f"{PLUGIN_NAME}@ai-agents": [
                "not-a-dict",
                {"installPath": 7},
                {"installPath": ""},
                {"installPath": str(tmp_path / "missing")},
                {"installPath": str(active)},
                {"installPath": str(active)},
            ],
            "broken@ai-agents": "not-a-list",
        },
    }
    _write_record(home, payload)

    outcome = drift.check_installed_plugins(project_dir, home)

    assert [report.install_path for report in _claude_reports(outcome)] == [active]


def test_record_never_echoes_its_install_path_in_notes(tmp_path) -> None:
    project_dir = _make_checkout(tmp_path / "repo", {})
    home = tmp_path / "home"
    _write_record(home, {"version": 99, "plugins": {}})

    outcome = drift.check_installed_plugins(project_dir, home)

    assert str(home) not in "".join(outcome.notes)


def test_copilot_surface_still_scans_every_copy_when_claude_record_exists(tmp_path) -> None:
    project_dir = _make_checkout(tmp_path / "repo", {})
    home = tmp_path / "home"
    active = _cache_install(home, "bbb222", {})
    _write_record(home, _record_for(active))
    copilot = _make_plugin_root(
        home / ".copilot" / "installed-plugins" / "ai-agents" / PLUGIN_NAME,
        _copilot_registration(RETIRED_GUARD_COMMAND),
    )

    outcome = drift.check_installed_plugins(project_dir, home)

    assert [r.install_path for r in outcome.reports if r.surface == "Copilot CLI"] == [copilot]


def test_missing_plugins_directory_adds_no_fallback_note(tmp_path) -> None:
    project_dir = _make_checkout(tmp_path / "repo", {})

    outcome = drift.check_installed_plugins(project_dir, tmp_path / "home")

    assert outcome.notes == []


def test_read_active_installs_returns_empty_list_for_uninstalled_plugin(tmp_path) -> None:
    search_root = tmp_path / "plugins"
    search_root.mkdir()
    record = search_root / "installed_plugins.json"
    _write_json(record, {"version": 2, "plugins": {}})

    assert record_module.read_active_installs(record, PLUGIN_NAME, search_root) == ([], None)

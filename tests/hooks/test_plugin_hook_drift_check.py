#!/usr/bin/env python3
"""Tests for invoke_plugin_hook_drift_check.py SessionStart hook (#5085).

The hook exists because an installed plugin kept enforcing four PreToolUse
guards that had been deleted from `main`, and no session surface said so. The
central case here reproduces that exact shape: a source manifest that
registers nothing (the ADR-097 shipped state) against an install that still
registers `invoke_lsp_pre_delegation_guard.py`, and asserts the report names
both the guard and the install path.

The rest covers what would make the check untrustworthy: reporting an
unreadable manifest as clean, staying silent when everything matches, letting
the scan wander unbounded or through symlinks, and blocking session start on
any internal error.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

HOOKS_DIR = str(Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "SessionStart")
sys.path.insert(0, HOOKS_DIR)

import invoke_plugin_hook_drift_check as drift

PLUGIN_NAME = "project-toolkit"
RETIRED_GUARD_COMMAND = (
    'python3 -u "${CLAUDE_PLUGIN_ROOT}/hooks/PreToolUse/invoke_lsp_pre_delegation_guard.py"'
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _make_plugin_root(root: Path, hooks: object, *, name: str = PLUGIN_NAME) -> Path:
    """Lay out a plugin root the way the installer does: manifest + hooks.json."""
    _write_json(root / ".claude-plugin" / "plugin.json", {"name": name})
    if hooks is not None:
        _write_json(root / "hooks" / "hooks.json", {"hooks": hooks})
    return root


def _registration(command: str, *, event: str = "PreToolUse", matcher: str = "Task") -> dict:
    return {event: [{"matcher": matcher, "hooks": [{"type": "command", "command": command}]}]}


def _source(hooks: object) -> set[tuple[str, str, str]]:
    """Registrations for a well-formed mapping, failing loudly if it is not."""
    found = drift.registrations(hooks)
    assert found is not None, f"test fixture is not a well-formed hooks mapping: {hooks!r}"
    return found


# --- registrations(): shape handling, malformed is not "registers nothing" ---


def test_registrations_flattens_event_matcher_command() -> None:
    found = drift.registrations(_registration("run-me"))

    assert found == {("PreToolUse", "Task", "run-me")}


def test_registrations_treats_absent_matcher_as_empty_string() -> None:
    found = drift.registrations({"SessionStart": [{"hooks": [{"command": "run-me"}]}]})

    assert found == {("SessionStart", "", "run-me")}


def test_registrations_returns_empty_set_for_empty_mapping() -> None:
    # The ADR-097 shipped state. An empty set is a real answer, not a failure.
    assert drift.registrations({}) == set()


@pytest.mark.parametrize("hooks", [None, [], "PreToolUse", 7])
def test_registrations_rejects_non_mapping(hooks) -> None:
    assert drift.registrations(hooks) is None


def test_registrations_rejects_non_list_event_value() -> None:
    # `{"PreToolUse": {}}` is malformed, not "registers nothing"; collapsing
    # the two would read a broken manifest as the deliberate empty state.
    assert drift.registrations({"PreToolUse": {}}) is None


# --- read_registrations(): every failure is named, never silently clean -----


def test_read_registrations_reports_missing_manifest(tmp_path) -> None:
    found, error = drift.read_registrations(tmp_path / "hooks" / "hooks.json")

    assert found is None
    assert error is not None
    assert "no hook manifest" in error


def test_read_registrations_reports_malformed_json(tmp_path) -> None:
    manifest = tmp_path / "hooks.json"
    manifest.write_text("{not json", encoding="utf-8")

    found, error = drift.read_registrations(manifest)

    assert found is None
    assert error is not None
    assert "unreadable hook manifest" in error


def test_read_registrations_reports_non_object_document(tmp_path) -> None:
    manifest = tmp_path / "hooks.json"
    manifest.write_text("[]", encoding="utf-8")

    found, error = drift.read_registrations(manifest)

    assert found is None
    assert "not a JSON object" in (error or "")


def test_read_registrations_reports_malformed_hooks_mapping(tmp_path) -> None:
    manifest = tmp_path / "hooks.json"
    _write_json(manifest, {"hooks": {"PreToolUse": {}}})

    found, error = drift.read_registrations(manifest)

    assert found is None
    assert "malformed 'hooks' mapping" in (error or "")


# --- find_installed_roots(): bounded, symlink-safe, name-matched ------------


def test_find_installed_roots_finds_a_nested_install(tmp_path) -> None:
    install = _make_plugin_root(tmp_path / "marketplaces" / "ai-agents" / ".claude", {})

    assert drift.find_installed_roots(tmp_path, PLUGIN_NAME) == [install]


def test_find_installed_roots_ignores_a_different_plugin(tmp_path) -> None:
    _make_plugin_root(tmp_path / "marketplaces" / "other", {}, name="someone-elses-plugin")

    assert drift.find_installed_roots(tmp_path, PLUGIN_NAME) == []


def test_find_installed_roots_returns_empty_for_missing_search_root(tmp_path) -> None:
    assert drift.find_installed_roots(tmp_path / "absent", PLUGIN_NAME) == []


def test_find_installed_roots_does_not_descend_past_max_depth(tmp_path) -> None:
    deep = tmp_path.joinpath(*[f"level{i}" for i in range(drift.MAX_SCAN_DEPTH + 1)])
    _make_plugin_root(deep, {})

    assert drift.find_installed_roots(tmp_path, PLUGIN_NAME) == []


def test_find_installed_roots_does_not_follow_symlinks(tmp_path) -> None:
    real = _make_plugin_root(tmp_path / "outside" / ".claude", {})
    search_root = tmp_path / "plugins"
    search_root.mkdir()
    try:
        (search_root / "link").symlink_to(real.parent, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("platform does not permit creating a directory symlink")

    assert drift.find_installed_roots(search_root, PLUGIN_NAME) == []


def test_find_installed_roots_does_not_descend_into_a_matched_root(tmp_path) -> None:
    outer = _make_plugin_root(tmp_path / "install", {})
    _make_plugin_root(outer / "vendored" / ".claude", {})

    assert drift.find_installed_roots(tmp_path, PLUGIN_NAME) == [outer]


def test_find_installed_roots_prunes_heavy_directories(tmp_path) -> None:
    _make_plugin_root(tmp_path / "node_modules" / "pkg" / ".claude", {})

    assert drift.find_installed_roots(tmp_path, PLUGIN_NAME) == []


# --- compare_install(): the issue #5085 shape --------------------------------


def test_compare_install_names_a_guard_the_source_retired(tmp_path) -> None:
    install = _make_plugin_root(tmp_path / "install", _registration(RETIRED_GUARD_COMMAND))

    report = drift.compare_install("Claude Code", install, set())

    assert report.has_drift
    assert report.error is None
    assert report.only_in_source == ()
    assert len(report.only_in_install) == 1
    assert "invoke_lsp_pre_delegation_guard.py" in report.only_in_install[0]
    assert "PreToolUse" in report.only_in_install[0]


def test_compare_install_reports_no_drift_when_registrations_match(tmp_path) -> None:
    install = _make_plugin_root(tmp_path / "install", _registration("shared"))
    source = _source(_registration("shared"))

    report = drift.compare_install("Claude Code", install, source)

    assert not report.has_drift
    assert report.only_in_install == ()
    assert report.only_in_source == ()


def test_compare_install_reports_the_other_direction_too(tmp_path) -> None:
    # An install missing a hook the source ships is drift as well. Reporting
    # one direction only would certify a half-updated install as clean.
    install = _make_plugin_root(tmp_path / "install", {})
    source = _source(_registration("shipped-now"))

    report = drift.compare_install("Claude Code", install, source)

    assert report.has_drift
    assert report.only_in_install == ()
    assert "shipped-now" in report.only_in_source[0]


def test_compare_install_reports_an_unreadable_install_as_drift(tmp_path) -> None:
    install = _make_plugin_root(tmp_path / "install", None)

    report = drift.compare_install("Claude Code", install, set())

    assert report.has_drift
    assert report.error is not None


# --- check_installed_plugins(): source resolution and per-surface notes ------


def _make_checkout(project_dir: Path, hooks: object) -> Path:
    _make_plugin_root(project_dir / ".claude", hooks)
    _make_plugin_root(project_dir / "src" / "copilot-cli", hooks)
    return project_dir


def test_check_installed_plugins_compares_claude_installs(tmp_path) -> None:
    project_dir = _make_checkout(tmp_path / "repo", {})
    home = tmp_path / "home"
    install = _make_plugin_root(
        home / ".claude" / "plugins" / "marketplaces" / "ai-agents" / ".claude",
        _registration(RETIRED_GUARD_COMMAND),
    )

    reports, notes = drift.check_installed_plugins(project_dir, home)

    assert notes == []
    assert [report.install_path for report in reports] == [install]
    assert reports[0].surface == "Claude Code"
    assert reports[0].has_drift


def test_check_installed_plugins_compares_copilot_installs(tmp_path) -> None:
    project_dir = _make_checkout(tmp_path / "repo", {})
    home = tmp_path / "home"
    _make_plugin_root(
        home / ".copilot" / "installed-plugins" / "ai-agents" / "project-toolkit",
        _registration(RETIRED_GUARD_COMMAND),
    )

    reports, _ = drift.check_installed_plugins(project_dir, home)

    assert [report.surface for report in reports] == ["Copilot CLI"]
    assert reports[0].has_drift


def test_check_installed_plugins_returns_nothing_when_no_install_exists(tmp_path) -> None:
    project_dir = _make_checkout(tmp_path / "repo", {})

    reports, notes = drift.check_installed_plugins(project_dir, tmp_path / "home")

    assert reports == []
    assert notes == []


def test_check_installed_plugins_notes_an_unreadable_source_manifest(tmp_path) -> None:
    project_dir = tmp_path / "repo"
    _make_plugin_root(project_dir / ".claude", None)
    _make_plugin_root(project_dir / "src" / "copilot-cli", {})

    _, notes = drift.check_installed_plugins(project_dir, tmp_path / "home")

    assert len(notes) == 1
    assert "Claude Code" in notes[0]


def test_check_installed_plugins_notes_a_missing_source_plugin_manifest(tmp_path) -> None:
    project_dir = tmp_path / "repo"
    _make_plugin_root(project_dir / "src" / "copilot-cli", {})

    _, notes = drift.check_installed_plugins(project_dir, tmp_path / "home")

    assert len(notes) == 1
    assert "no readable plugin manifest" in notes[0]


# --- format_message(): what actually reaches the injected context -----------


def _report(
    *,
    surface: str = "Claude Code",
    install_path: Path = Path("/home/u/.claude/plugins/marketplaces/ai-agents/.claude"),
    only_in_install: tuple[str, ...] = (),
    only_in_source: tuple[str, ...] = (),
    error: str | None = None,
) -> drift.InstallReport:
    return drift.InstallReport(
        surface=surface,
        install_path=install_path,
        only_in_install=only_in_install,
        only_in_source=only_in_source,
        error=error,
    )


def test_format_message_states_the_no_install_case_explicitly() -> None:
    message = drift.format_message([], [])

    assert "No installed copy" in message


def test_format_message_states_the_clean_case_with_a_count() -> None:
    # A passing check must be distinguishable from one that did not run.
    message = drift.format_message([_report(), _report()], [])

    assert "2 installed copy/copies match" in message


def test_format_message_names_the_guard_and_the_install_path() -> None:
    report = _report(only_in_install=(f"PreToolUse (matcher 'Task'): {RETIRED_GUARD_COMMAND}",))

    message = drift.format_message([report], [])

    assert "1 of 1 installed copy/copies register hooks" in message
    assert "invoke_lsp_pre_delegation_guard.py" in message
    assert str(report.install_path) in message


def test_format_message_omits_clean_installs_from_the_drift_list() -> None:
    drifted = _report(only_in_install=("PreToolUse (matcher 'Task'): retired",))
    clean = _report(install_path=Path("/home/u/.copilot/installed-plugins/x"))

    message = drift.format_message([drifted, clean], [])

    assert "1 of 2 installed copy/copies" in message
    assert str(clean.install_path) not in message


def test_format_message_carries_notes_through() -> None:
    message = drift.format_message([], ["Claude Code: no readable plugin manifest at /x"])

    assert "no readable plugin manifest at /x" in message


# --- main(): skip gate, emission, and fail-open -----------------------------


def test_main_skips_all_disk_work_for_a_consumer_repo(capsys) -> None:
    with (
        patch.object(drift, "skip_if_consumer_repo", return_value=True),
        patch.object(
            drift,
            "check_installed_plugins",
            side_effect=AssertionError("must not run for a consumer repo"),
        ),
        patch.object(drift.sys, "exit", side_effect=SystemExit) as mock_exit,
    ):
        with pytest.raises(SystemExit):
            drift.main()

    mock_exit.assert_called_once_with(0)
    assert capsys.readouterr().out == ""


def test_main_emits_the_drift_message_for_the_project_repo(capsys, tmp_path) -> None:
    report = _report(only_in_install=("PreToolUse (matcher 'Task'): retired-guard",))
    with (
        patch.object(drift, "skip_if_consumer_repo", return_value=False),
        patch.object(drift, "get_project_directory", return_value=str(tmp_path)),
        patch.object(drift, "check_installed_plugins", return_value=([report], [])),
    ):
        drift.main()

    assert "retired-guard" in capsys.readouterr().out


def test_hook_exits_zero_when_the_check_raises(tmp_path) -> None:
    # Fail-open is the whole contract: a broken drift check must never be the
    # reason a session cannot start.
    import subprocess

    script = Path(HOOKS_DIR) / "invoke_plugin_hook_drift_check.py"
    proc = subprocess.run(
        [sys.executable, "-u", str(script)],
        input=b"",
        capture_output=True,
        cwd=str(tmp_path),
        timeout=60,
    )

    assert proc.returncode == 0

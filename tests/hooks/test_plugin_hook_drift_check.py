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

import pytest

HOOKS_DIR = str(Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "SessionStart")
sys.path.insert(0, HOOKS_DIR)

import invoke_plugin_hook_drift_check as drift
import plugin_hook_drift_model as model
import plugin_hook_drift_state as state

PLUGIN_NAME = "project-toolkit"
RETIRED_GUARD_COMMAND = (
    'python3 -u "${CLAUDE_PLUGIN_ROOT}/hooks/PreToolUse/invoke_lsp_pre_delegation_guard.py"'
)


@pytest.fixture(autouse=True)
def _isolate_copilot_home(monkeypatch) -> None:
    """Keep the ambient COPILOT_HOME out of every fixture-home assertion.

    The hook honors the variable (this repo's e2e harnesses set it), so a test
    that means "under the fixture home" has to say so. Tests that exercise the
    override set it back explicitly.
    """
    monkeypatch.delenv("COPILOT_HOME", raising=False)


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


def _copilot_registration(command: str, *, event: str = "preToolUse") -> dict:
    """Copilot's real schema: flat under the event, command under `bash`.

    Using Claude's nested shape here would test the parser against a manifest
    Copilot CLI never writes, which is how the Copilot half of this check went
    unexercised in the first place.
    """
    return {event: [{"type": "command", "matcher": "task", "bash": command, "timeoutSec": 10}]}


def _source(hooks: object) -> set[tuple[str, str, str]]:
    """Registrations for a well-formed mapping, failing loudly if it is not."""
    found = model.registrations(hooks)
    assert found is not None, f"test fixture is not a well-formed hooks mapping: {hooks!r}"
    return found


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


# --- ScanBudget: a truncated walk is an outcome, never a clean answer -------


def _install_behind_decoys(search_root: Path, decoys: int = 2) -> Path:
    """Lay out a search root whose plugin copy sorts after ``decoys`` siblings.

    Breadth-first order plus sorted children puts the install last, so a walk
    bounded below the directory count never reaches it.
    """
    for index in range(decoys):
        (search_root / f"a_decoy{index}").mkdir(parents=True)
    return _make_plugin_root(search_root / "z_install", {})


def test_scan_budget_reports_exhaustion() -> None:
    budget = drift.ScanBudget(remaining=1)

    assert budget.spend() is True
    assert budget.truncated is False
    assert budget.spend() is False
    assert budget.truncated is True


def test_find_installed_roots_flags_a_walk_that_hit_the_directory_bound(tmp_path) -> None:
    # The install exists but sits past the bound. Returning [] with no other
    # signal would read as "not installed here", which is the false-clean
    # result this hook exists to prevent.
    install = _install_behind_decoys(tmp_path)
    budget = drift.ScanBudget(remaining=2)

    found = drift.find_installed_roots(tmp_path, PLUGIN_NAME, budget)

    assert found == []
    assert budget.truncated is True
    assert install.is_dir()


def test_find_installed_roots_does_not_flag_a_walk_that_finished(tmp_path) -> None:
    install = _install_behind_decoys(tmp_path)
    budget = drift.ScanBudget()

    found = drift.find_installed_roots(tmp_path, PLUGIN_NAME, budget)

    assert found == [install]
    assert budget.truncated is False


def test_find_installed_roots_does_not_flag_a_missing_search_root(tmp_path) -> None:
    budget = drift.ScanBudget()

    assert drift.find_installed_roots(tmp_path / "absent", PLUGIN_NAME, budget) == []
    assert budget.truncated is False


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
    (install / "hooks").mkdir()
    (install / "hooks" / "hooks.json").write_text("{not json", encoding="utf-8")

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

    outcome = drift.check_installed_plugins(project_dir, home)

    # No installed_plugins.json here, so the scan falls back to every copy and
    # says so in one note.
    assert len(outcome.notes) == 1
    assert "installed_plugins.json not found" in outcome.notes[0]
    assert outcome.incomplete == []
    assert [report.install_path for report in outcome.reports] == [install]
    assert outcome.reports[0].surface == "Claude Code"
    assert outcome.reports[0].has_drift


def test_check_installed_plugins_compares_copilot_installs(tmp_path) -> None:
    project_dir = _make_checkout(tmp_path / "repo", {})
    home = tmp_path / "home"
    _make_plugin_root(
        home / ".copilot" / "installed-plugins" / "ai-agents" / "project-toolkit",
        _copilot_registration(RETIRED_GUARD_COMMAND),
    )

    outcome = drift.check_installed_plugins(project_dir, home)

    assert [report.surface for report in outcome.reports] == ["Copilot CLI"]
    assert outcome.reports[0].error is None
    assert outcome.reports[0].has_drift
    assert outcome.incomplete == []


def test_check_installed_plugins_returns_nothing_when_no_install_exists(tmp_path) -> None:
    project_dir = _make_checkout(tmp_path / "repo", {})

    outcome = drift.check_installed_plugins(project_dir, tmp_path / "home")

    assert outcome.reports == []
    assert outcome.notes == []
    assert outcome.incomplete == []


def test_check_installed_plugins_notes_an_unreadable_source_manifest(tmp_path) -> None:
    project_dir = tmp_path / "repo"
    _make_plugin_root(project_dir / ".claude", None)
    _make_plugin_root(project_dir / "src" / "copilot-cli", {})

    notes = drift.check_installed_plugins(project_dir, tmp_path / "home").notes

    assert len(notes) == 1
    assert "Claude Code" in notes[0]


def test_check_installed_plugins_notes_a_missing_source_plugin_manifest(tmp_path) -> None:
    project_dir = tmp_path / "repo"
    _make_plugin_root(project_dir / "src" / "copilot-cli", {})

    notes = drift.check_installed_plugins(project_dir, tmp_path / "home").notes

    assert len(notes) == 1
    assert "no readable plugin manifest" in notes[0]


def test_check_installed_plugins_notes_do_not_leak_the_source_root_path(tmp_path) -> None:
    # source_root is checkout-derived path text; it must go through the same
    # path_token boundary install_path already does before landing in a note
    # that stdout carries into session context (CWE-74).
    project_dir = tmp_path / "repo"
    _make_plugin_root(project_dir / "src" / "copilot-cli", {})

    notes = drift.check_installed_plugins(project_dir, tmp_path / "home").notes

    assert len(notes) == 1
    assert str(project_dir) not in notes[0]
    assert "install sha256:" in notes[0]


def test_check_installed_plugins_incomplete_does_not_leak_the_search_root_path(
    tmp_path, monkeypatch
) -> None:
    # search_root is derived from COPILOT_HOME, an environment variable this
    # hook does not control; it must not reach stdout as raw path text.
    project_dir = _make_checkout(tmp_path / "repo", {})
    home = tmp_path / "home"
    _install_behind_decoys(home / ".claude" / "plugins")
    monkeypatch.setattr(state, "MAX_SCAN_DIRS", 2)

    outcome = drift.check_installed_plugins(project_dir, home)

    assert len(outcome.incomplete) == 1
    assert str(home) not in outcome.incomplete[0]
    assert "install sha256:" in outcome.incomplete[0]


def test_check_installed_plugins_reports_a_scan_it_could_not_finish(tmp_path, monkeypatch) -> None:
    # The install is real and stale, but sits past the directory bound. The
    # outcome has to say the search was cut short; an empty report list alone
    # would be indistinguishable from "nothing installed".
    project_dir = _make_checkout(tmp_path / "repo", {})
    home = tmp_path / "home"
    _install_behind_decoys(home / ".claude" / "plugins")
    # ScanBudget reads the bound from the model at construction, so the
    # bound has to be lowered where it lives.
    monkeypatch.setattr(state, "MAX_SCAN_DIRS", 2)

    outcome = drift.check_installed_plugins(project_dir, home)

    assert outcome.reports == []
    assert len(outcome.incomplete) == 1
    assert "Claude Code" in outcome.incomplete[0]


def test_check_installed_plugins_reports_a_complete_scan_as_complete(tmp_path) -> None:
    # Negative control for the test above: the same layout under the real
    # bound must not claim the scan was cut short.
    project_dir = _make_checkout(tmp_path / "repo", {})
    home = tmp_path / "home"
    install = _install_behind_decoys(home / ".claude" / "plugins")

    outcome = drift.check_installed_plugins(project_dir, home)

    assert [report.install_path for report in outcome.reports] == [install]
    assert outcome.incomplete == []


# --- COPILOT_HOME: the override decides which tree is searched --------------


def test_copilot_home_honors_the_override(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path / "cop"))

    assert drift.copilot_home(tmp_path / "home") == tmp_path / "cop"


@pytest.mark.parametrize("value", ["", "   "])
def test_copilot_home_falls_back_when_the_override_is_blank(tmp_path, monkeypatch, value) -> None:
    # Matches scripts/dev/dogfood_copilot_plugin.py::default_target, which
    # strips the variable and treats an empty result as unset.
    monkeypatch.setenv("COPILOT_HOME", value)

    assert drift.copilot_home(tmp_path / "home") == tmp_path / "home" / ".copilot"


def test_copilot_home_falls_back_when_the_override_is_absent(tmp_path) -> None:
    assert drift.copilot_home(tmp_path / "home") == tmp_path / "home" / ".copilot"


def test_plugin_surfaces_searches_the_overridden_copilot_home(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path / "cop"))

    surfaces = {surface.label: surface for surface in drift.plugin_surfaces(tmp_path / "home")}

    assert surfaces["Copilot CLI"].search_roots == (tmp_path / "cop" / "installed-plugins",)
    assert surfaces["Claude Code"].search_roots == (tmp_path / "home" / ".claude" / "plugins",)


def test_check_installed_plugins_compares_an_install_under_a_custom_copilot_home(
    tmp_path, monkeypatch
) -> None:
    # An operator who moved Copilot's home must not be told the stale install
    # that is blocking them does not exist.
    project_dir = _make_checkout(tmp_path / "repo", {})
    copilot = tmp_path / "elsewhere"
    monkeypatch.setenv("COPILOT_HOME", str(copilot))
    install = _make_plugin_root(
        copilot / "installed-plugins" / "ai-agents" / "project-toolkit",
        _copilot_registration(RETIRED_GUARD_COMMAND),
    )

    outcome = drift.check_installed_plugins(project_dir, tmp_path / "home")

    assert [report.install_path for report in outcome.reports] == [install]
    assert outcome.reports[0].surface == "Copilot CLI"
    assert outcome.reports[0].error is None
    assert outcome.reports[0].has_drift


# --- A surface that was never searched is inconclusive, not clean -----------


def test_check_installed_plugins_marks_an_unreadable_source_surface_incomplete(tmp_path) -> None:
    # No search ran for this surface, so "no installed copy found" would be a
    # claim about a tree nothing ever looked at.
    project_dir = tmp_path / "repo"
    _make_plugin_root(project_dir / ".claude", None)
    _make_plugin_root(project_dir / "src" / "copilot-cli", {})

    outcome = drift.check_installed_plugins(project_dir, tmp_path / "home")

    assert outcome.reports == []
    assert len(outcome.notes) == 1
    assert len(outcome.incomplete) == 1
    assert "Claude Code" in outcome.incomplete[0]
    assert "not searched" in outcome.incomplete[0]


def test_check_installed_plugins_marks_a_missing_plugin_manifest_incomplete(tmp_path) -> None:
    project_dir = tmp_path / "repo"
    _make_plugin_root(project_dir / "src" / "copilot-cli", {})

    outcome = drift.check_installed_plugins(project_dir, tmp_path / "home")

    assert len(outcome.incomplete) == 1
    assert "not searched" in outcome.incomplete[0]


def test_check_installed_plugins_leaves_incomplete_empty_when_both_surfaces_read(tmp_path) -> None:
    # Negative control: a fully readable checkout claims a complete pass.
    project_dir = tmp_path / "repo"
    _make_plugin_root(project_dir / ".claude", {})
    _make_plugin_root(project_dir / "src" / "copilot-cli", {})

    outcome = drift.check_installed_plugins(project_dir, tmp_path / "home")

    assert outcome.incomplete == []
    assert outcome.notes == []


# --- installed_plugins.json: only the harness's active installs count (#7227) --


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
    monkeypatch.setattr(drift, "MAX_RECORD_BYTES", 8)

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

    assert drift.read_active_installs(record, PLUGIN_NAME, search_root) == ([], None)

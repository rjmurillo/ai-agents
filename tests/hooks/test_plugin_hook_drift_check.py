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

    assert outcome.notes == []
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


def test_check_installed_plugins_reports_a_scan_it_could_not_finish(tmp_path, monkeypatch) -> None:
    # The install is real and stale, but sits past the directory bound. The
    # outcome has to say the search was cut short; an empty report list alone
    # would be indistinguishable from "nothing installed".
    project_dir = _make_checkout(tmp_path / "repo", {})
    home = tmp_path / "home"
    _install_behind_decoys(home / ".claude" / "plugins")
    monkeypatch.setattr(drift, "MAX_SCAN_DIRS", 2)

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


def test_format_message_names_a_missing_hook_as_missing_not_as_an_extra() -> None:
    # The extras wording sends the reader hunting for a retired rule. Here the
    # install ships too few hooks, not too many; the opposite fix applies.
    report = _report(only_in_source=("SessionStart (matcher ''): shipped-now",))

    message = drift.format_message([report], [])

    assert "are missing hooks this checkout ships" in message
    assert "register hooks this checkout does not" not in message
    assert "shipped-now" in message


def test_format_message_names_an_unreadable_manifest_as_uncompared() -> None:
    report = _report(error="unreadable hook manifest /x/hooks.json: ValueError: bad")

    message = drift.format_message([report], [])

    assert "have a hook manifest this check could not read" in message
    assert "never compared" in message
    assert "register hooks this checkout does not" not in message


def test_format_message_uses_neutral_wording_for_mixed_drift() -> None:
    extras = _report(only_in_install=("PreToolUse (matcher 'Task'): retired",))
    missing = _report(
        install_path=Path("/home/u/.copilot/installed-plugins/x"),
        only_in_source=("SessionStart (matcher ''): shipped-now",),
    )

    message = drift.format_message([extras, missing], [])

    assert "diverge from this checkout's hook registrations" in message
    assert "retired" in message
    assert "shipped-now" in message


def test_format_message_does_not_call_a_truncated_scan_a_clean_result() -> None:
    # No reports plus a cut-short search is not "nothing is installed".
    message = drift.format_message([], [], ["Claude Code: /home/u/.claude/plugins"])

    assert "not conclusive" in message
    assert "found on disk" not in message
    assert "/home/u/.claude/plugins" in message


def test_format_message_caps_a_matching_result_from_a_truncated_scan() -> None:
    message = drift.format_message([_report()], [], ["Claude Code: /home/u/.claude/plugins"])

    assert "1 installed copy/copies match" in message
    assert "not conclusive" in message


def test_format_message_states_no_install_plainly_when_the_scan_finished() -> None:
    # Negative control for the two tests above: a complete scan keeps the
    # unqualified wording and must not warn about conclusiveness.
    message = drift.format_message([], [])

    assert "found on disk" in message
    assert "not conclusive" not in message


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
        patch.object(
            drift, "check_installed_plugins", return_value=drift.ScanOutcome(reports=[report])
        ),
    ):
        drift.main()

    assert "retired-guard" in capsys.readouterr().out


def test_hook_exits_zero_on_a_clean_run(tmp_path) -> None:
    # The launch path itself must not fail. This says nothing about the
    # exception handler; the next test owns that.
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


def test_hook_exits_zero_and_warns_when_the_check_raises(tmp_path) -> None:
    # Fail-open is the whole contract: a broken drift check must never be the
    # reason a session cannot start. The earlier version of this test never
    # made anything raise, so it passed with the exception handler deleted and
    # proved nothing. Force a real failure inside the scan and assert both
    # halves of the contract: the warning is emitted and the exit is still 0.
    import subprocess
    import textwrap

    driver = tmp_path / "driver.py"
    driver.write_text(
        textwrap.dedent(
            f"""
            import runpy
            import sys
            import types

            # main() resolves the project directory through hook_utilities, so
            # a stand-in that raises there fails the real code path under the
            # module's own __main__ guard, which is what fail-open protects.
            utilities = types.ModuleType("hook_utilities")
            def get_project_directory():
                raise RuntimeError("scan exploded")
            utilities.get_project_directory = get_project_directory
            guards = types.ModuleType("hook_utilities.guards")
            guards.skip_if_consumer_repo = lambda name: False
            utilities.guards = guards
            sys.modules["hook_utilities"] = utilities
            sys.modules["hook_utilities.guards"] = guards

            runpy.run_path(
                {str(Path(HOOKS_DIR) / "invoke_plugin_hook_drift_check.py")!r},
                run_name="__main__",
            )
            """
        ),
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, "-u", str(driver)],
        input=b"",
        capture_output=True,
        cwd=str(tmp_path),
        timeout=60,
    )

    assert proc.returncode == 0
    assert b"scan exploded" in proc.stderr
    assert b"[WARNING]" in proc.stderr

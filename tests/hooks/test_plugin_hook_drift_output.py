#!/usr/bin/env python3
"""What the drift check actually emits, and that it never blocks a session.

Split from `test_plugin_hook_drift_check.py`, which owns the scan and the
comparison. The message is where a correct comparison can still mislead: the
extras wording sent a reader whose install is *missing* a hook off to hunt a
retired rule, and a scan that stopped at its bound read as "no drift". Both are
pinned here, alongside the fail-open contract for `main()`.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

HOOKS_DIR = str(Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "SessionStart")
sys.path.insert(0, HOOKS_DIR)

import invoke_plugin_hook_drift_check as drift

RETIRED_GUARD_COMMAND = (
    'python3 -u "${CLAUDE_PLUGIN_ROOT}/hooks/PreToolUse/invoke_lsp_pre_delegation_guard.py"'
)


@pytest.fixture(autouse=True)
def _isolate_copilot_home(monkeypatch) -> None:
    monkeypatch.delenv("COPILOT_HOME", raising=False)


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

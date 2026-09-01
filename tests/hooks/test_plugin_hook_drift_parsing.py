#!/usr/bin/env python3
"""Parsing, membership resolution, and output-safety tests for #5085's hook.

`test_plugin_hook_drift_check.py` owns the scan, the comparison, and the
message. This file owns the layer underneath: what a manifest is understood to
enforce, and what is allowed to leave the process afterwards.

Three detection gaps are pinned here because each one made the check report a
clean result over an install it had not actually understood:

- A Claude registration usually names the dispatcher, not a hook. Comparing
  entry points calls a stale install a match whenever both sides dispatch.
- Copilot manifests use a flatter schema. Read with Claude's parser they yield
  the empty set, so every stale Copilot install compared clean.
- Malformed group shapes fell through to the empty set, which downstream reads
  as the deliberate "registers nothing" state.

The fourth concern is output safety. An installed manifest under the scanned
trees is attacker-influenceable and this hook's output becomes session context,
so the tests below assert what is NOT echoed.
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

PLUGIN_NAME = "project-toolkit"
RETIRED_GUARD = "invoke_lsp_pre_delegation_guard.py"
DISPATCH_COMMAND = (
    'cd "$CLAUDE_PROJECT_DIR" && python3 -u .claude/hooks/invoke_dispatch_claude.py '
    "--group pretooluse-task"
)


@pytest.fixture(autouse=True)
def _isolate_copilot_home(monkeypatch) -> None:
    monkeypatch.delenv("COPILOT_HOME", raising=False)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _plugin_root(root: Path, hooks: object, groups: object = None) -> Path:
    """Lay out a plugin root: plugin manifest, hooks.json, dispatch groups."""
    _write_json(root / ".claude-plugin" / "plugin.json", {"name": PLUGIN_NAME})
    if hooks is not None:
        _write_json(root / "hooks" / "hooks.json", {"hooks": hooks})
    if groups is not None:
        _write_json(root / "hooks" / "dispatch_groups.json", {"groups": groups})
    return root


def _claude_hooks(command: str, *, event: str = "PreToolUse", matcher: str = "Task") -> dict:
    return {event: [{"matcher": matcher, "hooks": [{"type": "command", "command": command}]}]}


def _copilot_hooks(command: str, *, event: str = "preToolUse", matcher: str = "task") -> dict:
    """The real Copilot shape: flat under the event, command under `bash`.

    Mirrors `scripts/validation/hook_contracts.py::parse_copilot_hooks`, whose
    docstring states "the entries sit directly under the event name, the
    command lives under 'bash', and the timeout is spelled 'timeoutSec'".
    """
    return {
        event: [
            {
                "type": "command",
                "matcher": matcher,
                "bash": command,
                "powershell": f"pwsh -File {command}",
                "timeoutSec": 10,
            }
        ]
    }


def _group(*files: str, event: str = "PreToolUse") -> dict:
    return {
        "pretooluse-task": {"event": event, "mode": "block", "shims": [{"file": f} for f in files]}
    }


# --- Copilot schema: the flat shape is actually parsed ----------------------


def test_copilot_registrations_reads_the_bash_command() -> None:
    found = model.copilot_registrations(_copilot_hooks(f"python3 hooks/{RETIRED_GUARD}"))

    assert found == {("preToolUse", "task", RETIRED_GUARD)}


def test_claude_parser_reads_a_copilot_manifest_as_registering_nothing() -> None:
    # This is the bug being fixed, pinned so it cannot come back silently: the
    # nested parser finds no inner "hooks" list, so a stale Copilot install
    # compared equal to an empty source.
    assert model.registrations(_copilot_hooks("python3 hooks/guard.py")) is None


def test_copilot_registrations_rejects_a_non_list_event_value() -> None:
    assert model.copilot_registrations({"preToolUse": {}}) is None


def test_copilot_registrations_rejects_a_non_object_registration() -> None:
    assert model.copilot_registrations({"preToolUse": ["guard.py"]}) is None


def test_copilot_registrations_rejects_a_registration_with_no_command() -> None:
    assert model.copilot_registrations({"preToolUse": [{"type": "command"}]}) is None


def test_copilot_registrations_accepts_an_empty_mapping() -> None:
    assert model.copilot_registrations({}) == set()


def test_check_installed_plugins_detects_a_stale_copilot_install(tmp_path) -> None:
    project_dir = tmp_path / "repo"
    _plugin_root(project_dir / ".claude", {})
    _plugin_root(project_dir / "src" / "copilot-cli", {})
    home = tmp_path / "home"
    install = _plugin_root(
        home / ".copilot" / "installed-plugins" / "ai-agents" / "project-toolkit",
        _copilot_hooks(f"python3 hooks/PreToolUse/{RETIRED_GUARD}"),
    )

    outcome = drift.check_installed_plugins(project_dir, home)

    assert [report.install_path for report in outcome.reports] == [install]
    report = outcome.reports[0]
    assert report.error is None, "a real Copilot manifest must parse, not error"
    assert len(report.only_in_install) == 1
    assert RETIRED_GUARD in report.only_in_install[0]


# --- Dispatch membership: what a Claude registration actually enforces ------


def test_dispatch_membership_includes_event_and_mode_with_each_shim() -> None:
    groups = _group(f"PreToolUse/{RETIRED_GUARD}", "PreToolUse/invoke_other.py")["pretooluse-task"]

    members = model.dispatch_membership({"pretooluse-task": groups}, "pretooluse-task")

    assert members == (
        f"PreToolUse/block/{RETIRED_GUARD}",
        "PreToolUse/block/invoke_other.py",
    )


def test_dispatch_membership_distinguishes_a_group_that_changed_event_or_mode() -> None:
    # The dispatcher acts on event and mode, so a group moved from
    # PreToolUse/block to SessionStart/observe no longer enforces the same
    # policy even though every shim name is unchanged. Comparing basenames
    # alone called those two installs identical.
    same_shims = f"PreToolUse/{RETIRED_GUARD}"
    before = _group(same_shims)
    after = _group(same_shims, event="SessionStart")
    after["pretooluse-task"]["mode"] = "observe"

    assert model.dispatch_membership(before, "pretooluse-task") != model.dispatch_membership(
        after, "pretooluse-task"
    )


@pytest.mark.parametrize(
    "groups",
    [
        None,
        {},
        {"pretooluse-task": []},
        {"pretooluse-task": {"shims": {}}},
        {"pretooluse-task": {"shims": ["PreToolUse/x.py"]}},
        {"pretooluse-task": {"shims": [{"file": 7}]}},
        {"pretooluse-task": {"shims": [{}]}},
        {"pretooluse-task": {"event": "PreToolUse", "mode": "block", "shims": []}},
        {"pretooluse-task": {"mode": "block", "shims": [{"file": "a.py"}]}},
        {"pretooluse-task": {"event": "PreToolUse", "shims": [{"file": "a.py"}]}},
    ],
)
def test_dispatch_membership_returns_none_when_it_cannot_resolve(groups) -> None:
    # Unresolvable is not "the group is empty". An empty tuple here would let
    # an install whose manifest we cannot read compare equal to a clean source.
    assert model.dispatch_membership(groups, "pretooluse-task") is None


def test_registrations_expands_a_dispatch_group_to_its_shims() -> None:
    found = model.registrations(
        _claude_hooks(DISPATCH_COMMAND), _group(f"PreToolUse/{RETIRED_GUARD}")
    )

    assert found is not None
    assert len(found) == 1
    event, matcher, unit = next(iter(found))
    assert (event, matcher) == ("PreToolUse", "Task")
    assert unit == f"pretooluse-task: PreToolUse/block/{RETIRED_GUARD}"


def test_registrations_returns_none_for_an_unresolvable_dispatch_group() -> None:
    assert model.registrations(_claude_hooks(DISPATCH_COMMAND), {}) is None


def test_registrations_returns_none_for_a_dispatch_command_with_no_group() -> None:
    command = "python3 -u .claude/hooks/invoke_dispatch_claude.py"

    assert model.registrations(_claude_hooks(command), {}) is None


def test_compare_install_names_a_retired_shim_behind_an_identical_dispatcher(tmp_path) -> None:
    # The whole point of finding C. Both manifests register the same dispatcher
    # command, so an entry-point comparison calls this install a match while it
    # still enforces the guard issue #5085 was about.
    source_root = _plugin_root(
        tmp_path / "src", _claude_hooks(DISPATCH_COMMAND), _group("PreToolUse/invoke_kept.py")
    )
    install = _plugin_root(
        tmp_path / "install",
        _claude_hooks(DISPATCH_COMMAND),
        _group("PreToolUse/invoke_kept.py", f"PreToolUse/{RETIRED_GUARD}"),
    )
    source, error = model.root_registrations(source_root, model.CLAUDE_SCHEMA)

    assert error is None
    report = drift.compare_install("Claude Code", install, source or set())

    assert report.has_drift
    assert len(report.only_in_install) == 1
    assert RETIRED_GUARD in report.only_in_install[0]


def test_compare_install_reports_no_drift_for_identical_dispatch_membership(tmp_path) -> None:
    # Negative control for the test above: expansion must not invent drift.
    groups = _group("PreToolUse/invoke_kept.py")
    source_root = _plugin_root(tmp_path / "src", _claude_hooks(DISPATCH_COMMAND), groups)
    install = _plugin_root(tmp_path / "install", _claude_hooks(DISPATCH_COMMAND), groups)
    source, _ = model.root_registrations(source_root, model.CLAUDE_SCHEMA)

    report = drift.compare_install("Claude Code", install, source or set())

    assert not report.has_drift


def test_root_registrations_errors_when_the_install_cannot_resolve_its_group(tmp_path) -> None:
    install = _plugin_root(tmp_path / "install", _claude_hooks(DISPATCH_COMMAND))

    found, error = model.root_registrations(install, model.CLAUDE_SCHEMA)

    assert found is None
    assert "dispatch group" in (error or "")


# --- Malformed Claude shapes are unknown, never "registers nothing" ---------


@pytest.mark.parametrize(
    "hooks",
    [
        {"PreToolUse": ["not-an-object"]},
        {"PreToolUse": [{"matcher": "Task"}]},
        {"PreToolUse": [{"matcher": "Task", "hooks": {}}]},
        {"PreToolUse": [{"matcher": "Task", "hooks": ["not-an-object"]}]},
    ],
)
def test_registrations_rejects_malformed_group_shapes(hooks) -> None:
    assert model.registrations(hooks) is None


# --- registrations(): shape handling, malformed is not "registers nothing" ---


def test_registrations_flattens_event_matcher_command() -> None:
    found = model.registrations(_claude_hooks("run-me"))

    assert found == {("PreToolUse", "Task", "run-me")}


def test_registrations_treats_absent_matcher_as_empty_string() -> None:
    found = model.registrations({"SessionStart": [{"hooks": [{"command": "run-me"}]}]})

    assert found == {("SessionStart", "", "run-me")}


def test_registrations_returns_empty_set_for_empty_mapping() -> None:
    # The ADR-097 shipped state. An empty set is a real answer, not a failure.
    assert model.registrations({}) == set()


@pytest.mark.parametrize("hooks", [None, [], "PreToolUse", 7])
def test_registrations_rejects_non_mapping(hooks) -> None:
    assert model.registrations(hooks) is None


def test_registrations_rejects_non_list_event_value() -> None:
    # `{"PreToolUse": {}}` is malformed, not "registers nothing"; collapsing
    # the two would read a broken manifest as the deliberate empty state.
    assert model.registrations({"PreToolUse": {}}) is None


# --- read_registrations(): every failure is named, never silently clean -----


def test_read_registrations_reports_missing_manifest(tmp_path) -> None:
    found, error = model.read_registrations(tmp_path / "hooks" / "hooks.json")

    assert found is None
    assert error is not None
    assert "no hook manifest" in error


def test_read_registrations_reports_malformed_json(tmp_path) -> None:
    manifest = tmp_path / "hooks.json"
    manifest.write_text("{not json", encoding="utf-8")

    found, error = model.read_registrations(manifest)

    assert found is None
    assert error is not None
    assert "unreadable hook manifest" in error


def test_read_registrations_reports_non_object_document(tmp_path) -> None:
    manifest = tmp_path / "hooks.json"
    manifest.write_text("[]", encoding="utf-8")

    found, error = model.read_registrations(manifest)

    assert found is None
    assert "not a JSON object" in (error or "")


def test_read_registrations_reports_malformed_hooks_mapping(tmp_path) -> None:
    manifest = tmp_path / "hooks.json"
    _write_json(manifest, {"hooks": {"PreToolUse": {}}})

    found, error = model.read_registrations(manifest)

    assert found is None
    assert "malformed 'hooks' mapping" in (error or "")


# --- Resource ceilings: an unbounded manifest cannot stall session start ----


def test_read_registrations_refuses_a_manifest_over_the_byte_ceiling(tmp_path) -> None:
    # A same-named plugin root under the scanned trees is attacker-placeable.
    # Reading it without a ceiling is a denial-of-service surface at startup.
    manifest = tmp_path / "hooks.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    filler = "x" * (model.MAX_MANIFEST_BYTES + 1024)
    manifest.write_text(json.dumps({"hooks": {}, "pad": filler}), encoding="utf-8")

    found, error = model.read_registrations(manifest)

    assert found is None
    assert "exceeds" in (error or "")
    assert "not compared" in (error or "")


def test_read_registrations_accepts_a_manifest_under_the_byte_ceiling(tmp_path) -> None:
    # Negative control: the ceiling must not reject ordinary manifests.
    manifest = tmp_path / "hooks.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({"hooks": {}, "pad": "x" * 1024}), encoding="utf-8")

    found, error = model.read_registrations(manifest)

    assert error is None
    assert found == set()


def test_registrations_refuses_more_than_the_registration_ceiling() -> None:
    # Parsing partially would manufacture drift in both directions against a
    # source that is fine, so the whole manifest is reported as not compared.
    hooks = {
        f"Event{index}": [{"matcher": "", "hooks": [{"command": f"guard{index}.py"}]}]
        for index in range(model.MAX_REGISTRATIONS + 5)
    }

    assert model.registrations(hooks) is None


def test_copilot_registrations_refuses_more_than_the_registration_ceiling() -> None:
    hooks = {
        f"event{index}": [{"type": "command", "bash": f"guard{index}.py"}]
        for index in range(model.MAX_REGISTRATIONS + 5)
    }

    assert model.copilot_registrations(hooks) is None


def test_registrations_accepts_a_manifest_under_the_registration_ceiling() -> None:
    # Negative control for the two ceilings above.
    hooks = {
        f"Event{index}": [{"matcher": "", "hooks": [{"command": f"guard{index}.py"}]}]
        for index in range(10)
    }

    found = model.registrations(hooks)

    assert found is not None
    assert len(found) == 10


# --- A malformed matcher is drift, never a normalized empty string ----------


@pytest.mark.parametrize("matcher", [{}, [], 0, False, 7])
def test_registrations_rejects_a_non_string_matcher(matcher) -> None:
    # `entry.get("matcher") or ""` collapsed every falsy value to the same
    # normalized matcher as an absent one, so an install carrying a garbage
    # matcher compared equal to a source that has no matcher at all. The
    # canonical Copilot parser rejects these shapes rather than coercing them.
    hooks = {"PreToolUse": [{"matcher": matcher, "hooks": [{"command": "guard.py"}]}]}

    assert model.registrations(hooks) is None


@pytest.mark.parametrize("matcher", [{}, [], 0, False, 7])
def test_copilot_registrations_rejects_a_non_string_matcher(matcher) -> None:
    hooks = {"preToolUse": [{"type": "command", "matcher": matcher, "bash": "guard.py"}]}

    assert model.copilot_registrations(hooks) is None


def test_registrations_still_accepts_an_absent_or_null_matcher() -> None:
    # Negative control: null and absent are legitimate and mean "no matcher".
    absent = model.registrations({"SessionStart": [{"hooks": [{"command": "guard.py"}]}]})
    explicit_null = model.registrations(
        {"SessionStart": [{"matcher": None, "hooks": [{"command": "guard.py"}]}]}
    )

    assert absent == {("SessionStart", "", "guard.py")}
    assert explicit_null == absent


def test_compare_install_reports_a_garbage_matcher_rather_than_matching(tmp_path) -> None:
    # End to end: the command matches the source, only the matcher is garbage.
    install = _plugin_root(
        tmp_path / "install",
        {"PreToolUse": [{"matcher": {}, "hooks": [{"command": "guard.py"}]}]},
    )
    source = model.registrations(_claude_hooks("guard.py"))

    report = drift.compare_install("Claude Code", install, source or set())

    assert report.has_drift
    assert report.error is not None


# --- The plugin manifest is read through the same byte ceiling --------------


def test_read_plugin_name_refuses_an_oversized_plugin_manifest(tmp_path) -> None:
    # This manifest is read once per visited directory, so an unbounded read
    # here is the cheapest denial-of-service surface in the hook.
    root = tmp_path / "install"
    manifest = root / ".claude-plugin" / "plugin.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    filler = "x" * (model.MAX_MANIFEST_BYTES + 1024)
    manifest.write_text(json.dumps({"name": PLUGIN_NAME, "pad": filler}), encoding="utf-8")

    assert model.read_plugin_name(root) is None


def test_read_plugin_name_still_reads_an_ordinary_manifest(tmp_path) -> None:
    # Negative control for the ceiling above.
    root = _plugin_root(tmp_path / "install", {})

    assert model.read_plugin_name(root) == PLUGIN_NAME


def test_find_installed_roots_skips_an_install_behind_an_oversized_manifest(tmp_path) -> None:
    root = tmp_path / "search" / "install"
    manifest = root / ".claude-plugin" / "plugin.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    filler = "x" * (model.MAX_MANIFEST_BYTES + 1024)
    manifest.write_text(json.dumps({"name": PLUGIN_NAME, "pad": filler}), encoding="utf-8")

    assert drift.find_installed_roots(tmp_path / "search", PLUGIN_NAME) == []

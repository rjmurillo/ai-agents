#!/usr/bin/env python3
"""Plugin Stop registration for the reflect nudge (REQ-048 TASK-006).

Covers AC-18, AC-21, AC-25, and the ADR-084 rule 5 negative controls. The
registration is the plugin group ``plugin-stop-1-reflect_nudge``. The Copilot
exclusion is a NON-SECURITY scope choice (owner decision D20), recorded in the
``description`` of ``templates/hooks/dispatch_groups.json``.

ADR-085 Decision 7 item 9 asks for three kinds of test around a
``copilotExclude`` field. Where each lives:

- Copilot-side absence regression: ``test_copilot_plugin_has_no_entry_for_the_hook``
  and ``test_flipping_the_flag_puts_the_hook_back_on_copilot`` (the inverse).
- Claude-side presence regression: ``test_claude_plugin_registers_the_group_on_stop_only``.
- Strict-boolean validation: ``test_copilot_exclude_rejects_non_boolean_types`` in
  ``tests/build_scripts/test_dispatch_expansion.py``.
"""

from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path

import pytest

from tests.hooks import test_dispatch_groups_parity as parity

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPTS = str(REPO_ROOT / "build" / "scripts")
if BUILD_SCRIPTS not in sys.path:
    sys.path.insert(0, BUILD_SCRIPTS)

from generate_hooks_events import _expand_dispatch_groups

GROUP = "plugin-stop-1-reflect_nudge"
SHIM = "Stop/invoke_reflect_nudge.py"
CLAUDE_PLUGIN_HOOKS = REPO_ROOT / "src" / "claude" / "hooks.json"
CLAUDE_PLUGIN_HOOKS_DIR = REPO_ROOT / "src" / "claude" / "hooks"
COPILOT_HOOKS = REPO_ROOT / "src" / "copilot-cli" / "hooks" / "hooks.json"
HOOK_TEMPLATE = REPO_ROOT / "templates" / "hooks" / "Stop" / "invoke_reflect_nudge.py"
THRESHOLD_ENV = "AI_AGENTS_RETRO_NUDGE_THRESHOLD"
MAX_LINES = 500


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _registered_commands(doc: dict) -> list[tuple[str, str]]:
    return [
        (event, hook["command"])
        for event, groups in doc["hooks"].items()
        for group in groups
        for hook in group["hooks"]
    ]


def _module_docstring(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.match(r'(?:#![^\n]*\n)?"""(.*?)"""', text, re.DOTALL)
    assert match, f"{path} has no module docstring"
    return match.group(1)


# --- AC-21, AC-25: where the group is registered ------------------------------


def test_claude_plugin_registers_the_group_on_stop_only() -> None:
    commands = _registered_commands(_load(CLAUDE_PLUGIN_HOOKS))
    assert [event for event, _ in commands] == ["Stop"], "AC-25: Stop only"
    command = commands[0][1]
    assert f"--group {GROUP}" in command
    assert "${CLAUDE_PLUGIN_ROOT}/hooks/invoke_dispatch_claude.py" in command


def test_claude_plugin_ships_the_shim_and_the_dispatcher_library() -> None:
    assert (CLAUDE_PLUGIN_HOOKS_DIR / SHIM).is_file()
    lib = REPO_ROOT / "src" / "claude" / "lib"
    for name in (
        "claude_hook_dispatch.py",
        "claude_hook_protocol.py",
        "hook_dispatch.py",
        "hook_dispatch_protocol.py",
        "hook_dispatch_timeout.py",
        "output_capture.py",
        "shim_loader.py",
    ):
        assert (lib / name).is_file(), f"the launcher imports {name} from the plugin lib/"


def test_group_is_a_plugin_surface_stop_group_excluded_from_copilot() -> None:
    spec = parity.MANIFEST["groups"][GROUP]
    assert spec["event"] == "Stop"
    assert spec["surface"] == "plugin"
    assert spec["advisory"] is True
    (shim,) = spec["shims"]
    assert shim["file"] == SHIM
    assert shim["copilotExclude"] is True
    assert re.fullmatch(r"#\d+", shim["copilotExcludeIssue"])
    assert re.fullmatch(r"ADR-\d+", shim["copilotExcludeDecision"])


def test_copilot_plugin_has_no_entry_for_the_hook() -> None:
    doc = _load(COPILOT_HOOKS)
    assert "invoke_reflect_nudge" not in json.dumps(doc)
    assert GROUP not in json.dumps(doc)
    assert doc["hooks"].get("Stop", []) == []


def _expand(manifest_groups: dict, tmp_path: Path) -> dict:
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()
    (hooks_dir / "dispatch_groups.json").write_text(
        json.dumps({"groups": manifest_groups}), encoding="utf-8"
    )
    return _expand_dispatch_groups(_load(CLAUDE_PLUGIN_HOOKS)["hooks"], hooks_dir)


def test_expansion_omits_the_excluded_shim(tmp_path: Path) -> None:
    expanded = _expand(_load(CLAUDE_PLUGIN_HOOKS_DIR / "dispatch_groups.json")["groups"], tmp_path)
    assert "invoke_reflect_nudge" not in json.dumps(expanded)


def test_flipping_the_flag_puts_the_hook_back_on_copilot(tmp_path: Path) -> None:
    """Inverse control: the absence above is caused by the flag, not by luck."""
    groups = copy.deepcopy(_load(CLAUDE_PLUGIN_HOOKS_DIR / "dispatch_groups.json")["groups"])
    groups[GROUP]["shims"][0]["copilotExclude"] = False
    expanded = _expand(groups, tmp_path)
    assert "invoke_reflect_nudge.py" in json.dumps(expanded)


def test_registration_and_manifest_agree_on_advisory() -> None:
    """The launcher reads ``--advisory`` from the registration, not the manifest."""
    for doc in (_load(CLAUDE_PLUGIN_HOOKS), _load(parity.HOOKS_DIR / "hooks.json")):
        for _event, command in _registered_commands(doc):
            group = re.search(r"--group\s+([A-Za-z0-9_-]+)", command)
            assert group, command
            declared = parity.MANIFEST["groups"][group.group(1)].get("advisory") is True
            flagged = re.search(r"--group\s+\S+\s+--advisory\b", command) is not None
            assert declared == flagged, f"{group.group(1)}: manifest says {declared}"


# --- AC-18, ADR-084 rule 5: the Customer value line ---------------------------


def test_docstring_has_one_customer_value_line_naming_the_switch_and_off_values() -> None:
    docstring = _module_docstring(HOOK_TEMPLATE)
    lines = [line for line in docstring.splitlines() if "Customer value:" in line]
    assert len(lines) == 1, lines
    assert HOOK_TEMPLATE.read_text(encoding="utf-8").count("Customer value:") == 1
    assert THRESHOLD_ENV in lines[0]
    assert re.search(r"\b0\b", lines[0]) and re.search(r"\boff\b", lines[0])


def test_docstring_states_the_firing_bound() -> None:
    flat = " ".join(_module_docstring(HOOK_TEMPLATE).split())
    assert "at most one friction nudge per session per threshold tier" in flat


def test_every_registered_copy_carries_the_same_docstring_lines() -> None:
    """The generated copies ship what the template says."""
    needle = "Customer value:"
    for copy_path in (
        parity.HOOKS_DIR / SHIM,
        CLAUDE_PLUGIN_HOOKS_DIR / SHIM,
    ):
        assert copy_path.read_text(encoding="utf-8").count(needle) == 1, copy_path


def test_hook_template_stays_within_the_file_size_limit() -> None:
    count = len(HOOK_TEMPLATE.read_text(encoding="utf-8").splitlines())
    assert count <= MAX_LINES, count


# --- ADR-084 rule 5 negative controls ----------------------------------------


def _patch_surface(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, body: str | None) -> None:
    groups = {}
    if body is not None:
        shim = tmp_path / "Stop" / "x.py"
        shim.parent.mkdir()
        shim.write_text(body, encoding="utf-8")
        groups["g"] = {"surface": "plugin", "shims": [{"file": "Stop/x.py"}]}
    monkeypatch.setattr(parity, "HOOKS_DIR", tmp_path)
    monkeypatch.setattr(parity, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(parity, "MANIFEST", {"groups": groups})


def test_presence_check_fails_for_a_vendored_hook_without_the_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_surface(monkeypatch, tmp_path, '"""No value statement here."""\n')
    with pytest.raises(AssertionError, match="Customer value"):
        parity.test_every_vendored_hook_states_its_customer_value()


def test_presence_check_passes_for_a_vendored_hook_with_the_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_surface(monkeypatch, tmp_path, '"""Customer value: tells you X."""\n')
    parity.test_every_vendored_hook_states_its_customer_value()
    parity.test_the_customer_value_check_examines_a_nonempty_surface()


def test_nonempty_surface_guard_fails_on_an_empty_surface(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_surface(monkeypatch, tmp_path, None)
    parity.test_every_vendored_hook_states_its_customer_value()  # vacuous pass
    with pytest.raises(AssertionError, match="vacuously"):
        parity.test_the_customer_value_check_examines_a_nonempty_surface()

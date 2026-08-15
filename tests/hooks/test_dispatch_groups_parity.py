#!/usr/bin/env python3
"""Parity checks between hook registrations and dispatch_groups.json (#3075).

The dispatch manifest is the source of truth for group membership. These
tests keep the three surfaces honest: repo settings (.claude/settings.json),
the project-toolkit plugin manifest (.claude/hooks/hooks.json), and the
files on disk. A registration that names a missing group, a group whose
event or matcher disagrees with its registration, or a shim file that does
not exist would otherwise fail at hook time (fail-closed) for every tool
call in the group.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shlex
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = REPO_ROOT / ".claude" / "hooks"
MANIFEST = json.loads((HOOKS_DIR / "dispatch_groups.json").read_text(encoding="utf-8"))
SETTINGS = json.loads((REPO_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
PLUGIN_HOOKS = json.loads((HOOKS_DIR / "hooks.json").read_text(encoding="utf-8"))

_GROUP_RE = re.compile(r"dispatch_claude\.py\"?\s+--group\s+([A-Za-z0-9_-]+)")
_DEFAULT_SHIM_TIMEOUT = 30
_DISPATCHER_HEADROOM = 5


def _dispatch_registrations(hooks_map: dict) -> list[tuple[str, str | None, str]]:
    """Yield (event, matcher, group_id) for every dispatcher registration."""
    found = []
    for event, groups in hooks_map.items():
        for group in groups:
            for hook in group.get("hooks", []):
                match = _GROUP_RE.search(hook.get("command", "") or "")
                if match:
                    found.append((event, group.get("matcher"), match.group(1)))
    return found


SETTINGS_REGS = _dispatch_registrations(SETTINGS["hooks"])
PLUGIN_REGS = _dispatch_registrations(PLUGIN_HOOKS["hooks"])


def test_every_manifest_shim_exists_on_disk():
    missing = [
        f"{group_id}: {shim['file']}"
        for group_id, spec in MANIFEST["groups"].items()
        for shim in spec["shims"]
        if not (HOOKS_DIR / shim["file"]).is_file()
    ]
    assert missing == []


@pytest.mark.parametrize(("event", "matcher", "group_id"), SETTINGS_REGS)
def test_settings_registrations_match_manifest(event, matcher, group_id):
    spec = MANIFEST["groups"].get(group_id)
    assert spec is not None, f"settings.json references unknown group {group_id}"
    assert spec["event"] == event
    assert spec.get("matcher") == matcher
    assert spec.get("surface") != "plugin", (
        f"settings.json must not register plugin-surface group {group_id}"
    )


def test_settings_dispatcher_timeouts_cover_serial_members_and_headroom():
    timeout_by_group = {
        match.group(1): hook["timeout"]
        for groups in SETTINGS["hooks"].values()
        for group in groups
        for hook in group.get("hooks", [])
        if (match := _GROUP_RE.search(hook.get("command", "") or ""))
    }
    for group_id, timeout in timeout_by_group.items():
        shims = MANIFEST["groups"][group_id]["shims"]
        required = (
            sum(shim.get("timeout", _DEFAULT_SHIM_TIMEOUT) for shim in shims)
            + _DISPATCHER_HEADROOM
        )
        assert timeout >= required, (
            f"{group_id}: dispatcher timeout {timeout}s is below the "
            f"{required}s serial budget"
        )


@pytest.mark.parametrize(("event", "matcher", "group_id"), PLUGIN_REGS)
def test_plugin_registrations_match_manifest(event, matcher, group_id):
    spec = MANIFEST["groups"].get(group_id)
    assert spec is not None, f"hooks.json references unknown group {group_id}"
    assert spec["event"] == event
    assert spec.get("matcher") == matcher
    assert spec.get("surface") == "plugin", (
        f"plugin hooks.json must register plugin-surface groups, got {group_id}"
    )


def test_settings_uses_every_project_group():
    project_groups = {
        gid for gid, spec in MANIFEST["groups"].items() if spec.get("surface") != "plugin"
    }
    registered = {gid for _, _, gid in SETTINGS_REGS}
    assert registered == project_groups


def test_plugin_uses_every_plugin_group():
    plugin_groups = {
        gid for gid, spec in MANIFEST["groups"].items() if spec.get("surface") == "plugin"
    }
    registered = {gid for _, _, gid in PLUGIN_REGS}
    assert registered == plugin_groups


def test_modes_are_valid_and_event_appropriate():
    for group_id, spec in MANIFEST["groups"].items():
        assert spec["mode"] in {"gate", "gate_all", "observe"}, group_id
        if spec["event"] == "PreToolUse":
            assert spec["mode"] == "gate", (
                f"{group_id}: PreToolUse groups must fail closed (gate mode)"
            )


def _group_shim_basenames(surface_is_plugin: bool) -> set[str]:
    return {
        shim["file"].split("/")[-1]
        for spec in MANIFEST["groups"].values()
        if (spec.get("surface") == "plugin") == surface_is_plugin
        for shim in spec["shims"]
    }


def _settings_direct_basenames() -> set[str]:
    basenames = {
        Path(token).name
        for groups in SETTINGS["hooks"].values()
        for group in groups
        for hook in group.get("hooks", [])
        if "invoke_dispatch_claude.py" not in (hook.get("command") or "")
        for token in shlex.split(hook.get("command") or "")
        if token.endswith((".py", ".sh"))
    }
    return basenames


def test_repo_settings_cover_plugin_shims_minus_documented_prunes():
    # The self-host bail (invoke_dispatch_claude.py exiting 0 for plugin
    # invocations inside this repo) is only safe when repo settings run
    # every hook the plugin would have run, minus the prunes this repo
    # deliberately made. A plugin shim missing here would silently never
    # run during this repo's own sessions (the 19-day dead-hook class).
    pruned = {
        # ADR-084 keeps customer-value markdown hooks plugin-only.
        "invoke_markdown_auto_lint.py",
        "invoke_markdownlint_guard.py",
        # Gate groups do not take the plugin dispatcher's self-host bail.
        "invoke_push_pr_script_identity_guard.py",
        # ADR-085: settings.json twin removed; gate-mode groups skip self-host bail.
        "invoke_require_subagent_model.py",
    }
    uncovered = (
        _group_shim_basenames(surface_is_plugin=True)
        - _group_shim_basenames(surface_is_plugin=False)
        - _settings_direct_basenames()
    )
    assert uncovered == pruned, (
        f"plugin shims not covered by repo settings (and not documented prunes): "
        f"{sorted(uncovered - pruned)}; stale prune entries: {sorted(pruned - uncovered)}"
    )


def test_plugin_registrations_are_dispatcher_only():
    # Every plugin hook command must route through the dispatcher so the
    # self-host bail applies to the whole plugin surface (no double-fire
    # inside the publishing repo).
    direct = [
        hook.get("command")
        for groups in PLUGIN_HOOKS["hooks"].values()
        for group in groups
        for hook in group.get("hooks", [])
        if "invoke_dispatch_claude.py" not in (hook.get("command") or "")
    ]
    assert direct == []


# Every hook authorized to run, with the decision that authorized it. This is
# the ledger #3197 kept only in issue prose, which is how two retired hooks
# (invoke_auto_retrospective.py, invoke_context_loader.py) stayed registered
# and firing for weeks with 103 tests over this manifest reporting green.
#
# The gate deliberately asserts identity, not naming. A group-name coherence
# assertion was tried first and falsified: replayed over the last 14 revisions
# of dispatch_groups.json it flagged healthy descriptive groups such as
# `pretooluse-write-edit` in 12 of them. ADR-082 specifies a group's event,
# mode, membership, merge rules, and timeout ownership; it says nothing about
# ids, so a name carries no contract to check against. That silence is tracked
# in #3374. Names are not a gate.
#
# The authorized set is small and shrinking while the running set is what
# drifts, so this stays cheap and gets stronger as the ROI program completes.
AUTHORIZED_HOOKS = {
    "invoke_require_subagent_model.py": "#4874: deny sub-agent spawns that would "
    "silently inherit the session model on Claude and Copilot CLI",
    "invoke_push_pr_script_identity_guard.py": "#4764: block repository-controlled "
    "lookalike PR scripts before Python execution",
    "invoke_markdownlint_guard.py": "ADR-084 keeper (customer value)",
    "invoke_markdown_auto_lint.py": "ADR-084 keeper (customer value)",
    "invoke_observation_sync.py": "#3217: relocate to .githooks/CI, authorized until then",
    "invoke_compact_checkpoint.py": "#3217 KEEP, trimmed by #3273",
    "invoke_context_loader.py": "#3349 KEEP: read-only, fail-open, automates the "
    "SESSION-PROTOCOL start gate for this repo's own sessions",
    "session-start.sh": "#3244 deterministic .githooks activation",
    "invoke_memory_recall.py": "#4011 KEEP: fail-open recall, dogfood-only, "
    "stdout on exit 0 so it can never erase a prompt",
    "invoke_memory_capture.py": "#4011 KEEP: fail-open suggestion after the "
    "tool already ran, dogfood-only",
    "invoke_memory_reflection.py": "#4011 KEEP: the only live caller that "
    "persists memory confidence scores, dogfood-only",
}


def _every_running_basename() -> set[str]:
    return (
        _group_shim_basenames(surface_is_plugin=True)
        | _group_shim_basenames(surface_is_plugin=False)
        | _settings_direct_basenames()
    )


def test_every_dispatched_hook_is_authorized():
    unauthorized = _every_running_basename() - set(AUTHORIZED_HOOKS)
    assert unauthorized == set(), (
        f"hooks run with no recorded authorization: {sorted(unauthorized)}. "
        f"Either delete them or add an entry to AUTHORIZED_HOOKS naming the "
        f"ADR or issue that authorized the keep."
    )


def test_no_authorization_outlives_the_hook_it_authorizes():
    # The converse. Without it the ledger only grows: an entry whose hook was
    # deleted keeps claiming a decision that no longer applies to anything,
    # and the next reader has to diff it against the tree by hand.
    stale = set(AUTHORIZED_HOOKS) - _every_running_basename()
    assert stale == set(), (
        f"authorized but not running: {sorted(stale)}. Delete these entries; "
        f"the ledger records what runs, not what once did."
    )


# Every other test in this file checks that invoke_require_subagent_model.py
# is registered, authorized, and shipped in every manifest it must appear
# in. None of them call the hook itself, so a regression in the actual
# block/allow decision it exists to make (#4874: deny a sub-agent spawn
# that would silently inherit the session model) would pass every test
# above. These tests drive the shipped entrypoint's main() directly with
# both harnesses' payload shapes (Copilot review finding on PR #4846,
# tests/build_scripts... ADR-068/071/085 sibling gap notwithstanding).
REQUIRE_SUBAGENT_MODEL_PATH = HOOKS_DIR / "PreToolUse" / "invoke_require_subagent_model.py"


def _load_require_subagent_model() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "require_subagent_model_under_test", REQUIRE_SUBAGENT_MODEL_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def require_subagent_model() -> ModuleType:
    return _load_require_subagent_model()


def _write_pinned_definition(path: Path, model: str = "claude-sonnet-5") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nmodel: {model}\n---\nbody\n", encoding="utf-8")


class TestRequireSubagentModelGate:
    """Behavioral coverage for the #4874 sub-agent model gate's main()."""

    @pytest.fixture(autouse=True)
    def _isolated_gate_env(self, monkeypatch, tmp_path):
        # main() looks up Path.home() directly (not overridable), so
        # without pointing CLAUDE_CONFIG_DIR/COPILOT_HOME at empty tmp
        # directories, the deny assertions below would depend on whatever
        # agent definitions happen to exist in the real machine's home
        # directory.
        monkeypatch.delenv("CLAUDE_CODE_SUBAGENT_MODEL", raising=False)
        monkeypatch.delenv("COPILOT_PLUGIN_ROOT", raising=False)
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "no-claude-config"))
        monkeypatch.setenv("COPILOT_HOME", str(tmp_path / "no-copilot-home"))

    def test_non_subagent_tool_is_allowed_without_inspecting_args(
        self, require_subagent_model, monkeypatch
    ):
        monkeypatch.setattr(require_subagent_model, "_read_payload", lambda: {"tool_name": "Bash"})
        assert require_subagent_model.main() == 0

    def test_explicit_model_in_the_call_is_allowed(self, require_subagent_model, monkeypatch):
        payload = {
            "tool_name": "Task",
            "tool_input": {"subagent_type": "unregistered-agent", "model": "gpt-5"},
        }
        monkeypatch.setattr(require_subagent_model, "_read_payload", lambda: payload)
        assert require_subagent_model.main() == 0

    def test_escape_hatch_env_var_allows_inherit_by_default(
        self, require_subagent_model, monkeypatch
    ):
        payload = {"tool_name": "Task", "tool_input": {"subagent_type": "unregistered-agent"}}
        monkeypatch.setattr(require_subagent_model, "_read_payload", lambda: payload)
        monkeypatch.setenv("CLAUDE_CODE_SUBAGENT_MODEL", "1")
        assert require_subagent_model.main() == 0

    def test_no_model_and_no_definition_file_is_denied(
        self, require_subagent_model, monkeypatch, tmp_path
    ):
        payload = {"tool_name": "Task", "tool_input": {"subagent_type": "unregistered-agent"}}
        monkeypatch.setattr(require_subagent_model, "_read_payload", lambda: payload)
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        assert require_subagent_model.main() == 2

    def test_claude_agent_definition_with_pinned_model_is_allowed(
        self, require_subagent_model, monkeypatch, tmp_path
    ):
        payload = {"tool_name": "Task", "tool_input": {"subagent_type": "pinned-agent"}}
        monkeypatch.setattr(require_subagent_model, "_read_payload", lambda: payload)
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        _write_pinned_definition(tmp_path / ".claude" / "agents" / "pinned-agent.md")
        assert require_subagent_model.main() == 0

    def test_copilot_cli_payload_with_pinned_definition_is_allowed(
        self, require_subagent_model, monkeypatch, tmp_path
    ):
        # Copilot CLI's native runtime tool is "task" with lowercase
        # toolName/toolArgs (cross-harness payload contract, module docstring).
        payload = {"toolName": "task", "toolArgs": {"agent_type": "pinned-agent"}}
        monkeypatch.setattr(require_subagent_model, "_read_payload", lambda: payload)
        monkeypatch.chdir(tmp_path)
        _write_pinned_definition(tmp_path / ".github" / "agents" / "pinned-agent.agent.md")
        assert require_subagent_model.main() == 0

    def test_copilot_cli_payload_without_definition_is_denied(
        self, require_subagent_model, monkeypatch, tmp_path
    ):
        payload = {"toolName": "task", "toolArgs": {"agent_type": "unregistered-agent"}}
        monkeypatch.setattr(require_subagent_model, "_read_payload", lambda: payload)
        monkeypatch.chdir(tmp_path)
        assert require_subagent_model.main() == 2

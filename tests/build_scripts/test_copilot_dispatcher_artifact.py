"""Committed-artifact regression for the Copilot universal dispatcher cutover.

ADR-068 / #2295 / #2342. Asserts the generated src/copilot-cli/hooks/ tree
consolidates EVERY event to one dispatcher entry, that the tool-gating event
(PreToolUse) runs in gate mode (fail-closed short-circuit, unchanged) and the
observational PostToolUse event runs in observe mode (all shims run, exit 0),
and that the generated entrypoint
runs the real guard set in one process with the right behavior per mode. Runs
in CI against the committed artifacts using this repo as the plugin root.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "build" / "scripts"))

from generate_hooks_body import is_shimmed  # noqa: E402
from generate_hooks_events import _COMPANIONS_BY_OWNER  # noqa: E402
from regen_guard import detect_reason_strict  # noqa: E402

_COPILOT = _REPO / "src" / "copilot-cli"
_HOOKS_JSON = _COPILOT / "hooks" / "hooks.json"
_GATING = "PreToolUse"
_OBSERVE_EVENTS = ("PostToolUse",)
_ALL_EVENTS = (_GATING, *_OBSERVE_EVENTS)
_DISPATCH_TEST_TIMEOUT_CAP_SEC = 60
_DISPATCHER_TIMEOUT_HEADROOM_SEC = 5


def _hooks() -> dict[str, list[dict[str, Any]]]:
    data = json.loads(_HOOKS_JSON.read_text(encoding="utf-8"))
    return cast("dict[str, list[dict[str, Any]]]", data["hooks"])


_DISPATCH_GROUPS = json.loads(
    (_REPO / ".claude" / "hooks" / "dispatch_groups.json").read_text(encoding="utf-8")
)["groups"]


def _effective_commands(manifest: dict[str, Any], event: str | None = None) -> list[str]:
    """Flatten hook registrations to per-script command strings.

    Claude-side manifests register invoke_dispatch_claude.py groups (#3075); a
    group registration counts as one command per member shim so tests can
    keep asserting on the effective script set.
    """
    commands: list[str] = []
    events = [event] if event else list(manifest["hooks"].keys())
    for evt in events:
        for group in manifest["hooks"].get(evt, []):
            for hook in group.get("hooks", []):
                command = hook.get("command", "") or ""
                if "invoke_dispatch_claude.py" in command:
                    group_id = command.rsplit("--group", 1)[1].strip().split(";")[0].strip()
                    commands.extend(
                        shim["file"] for shim in _DISPATCH_GROUPS[group_id]["shims"]
                    )
                else:
                    commands.append(command)
    return commands


def _run_entry(
    event: str,
    payload: dict[str, Any],
    project_dir: Path | None = None,
) -> subprocess.CompletedProcess[bytes]:
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(project_dir if project_dir is not None else _REPO)
    env["CLAUDE_PLUGIN_ROOT"] = str(_COPILOT)
    env["COPILOT_PLUGIN_ROOT"] = str(_COPILOT)
    env["AI_AGENTS_PROJECT_REPO"] = "1"
    event_timeout_sec = int(_hooks()[event][0]["timeoutSec"])
    timeout_sec = min(event_timeout_sec + 5, _DISPATCH_TEST_TIMEOUT_CAP_SEC)
    return subprocess.run(
        [sys.executable, "-u", str(_COPILOT / "hooks" / event / "_dispatch.py")],
        input=json.dumps(payload).encode(),
        capture_output=True,
        env=env,
        timeout=timeout_sec,
    )


class TestDispatcherArtifacts:
    def test_every_event_is_one_dispatcher_entry(self):
        hooks = _hooks()
        # #2342: every generated event collapses to one dispatcher entry.
        assert set(hooks) == set(_ALL_EVENTS), f"unexpected event set: {sorted(hooks)}"
        for event in _ALL_EVENTS:
            entries = hooks[event]
            assert len(entries) == 1, f"{event}: expected 1 dispatcher entry, got {len(entries)}"
            assert f"/hooks/{event}/_dispatch.py" in entries[0]["bash"]
            assert f"/hooks/{event}/_dispatch.py" in entries[0]["powershell"]

    def test_retired_hooks_are_absent_and_keepers_are_plugin_only(self):
        settings = json.loads(
            (_REPO / ".claude" / "settings.json").read_text(encoding="utf-8")
        )
        plugin_hooks = json.loads(
            (_REPO / ".claude" / "hooks" / "hooks.json").read_text(
                encoding="utf-8"
            )
        )
        manifests = [settings, plugin_hooks]
        removed = (
            "invoke_adr_change_detection.py",
            "invoke_adr_review_guard.py",
            "invoke_autonomous_execution_detector.py",
            "invoke_correction_applier.py",
            "invoke_false_completion_gate.py",
            "invoke_memory_first_enforcer.py",
            "invoke_research_then_implement.py",
            "invoke_retrospective_gate.py",
            "invoke_security_commit_gate.py",
            "invoke_security_gate.py",
            "invoke_serena_reassertion.py",
            "invoke_session_initialization_enforcer.py",
            "invoke_session_log_field_guard.py",
            "invoke_session_log_guard.py",
            "invoke_session_start_memory_first.py",
            "invoke_auto_retrospective.py",
            "invoke_session_validator.py",
            "invoke_test_auto_approval.py",
            "invoke_topical_memory_injection.py",
            "invoke_user_prompt_memory_check.py",
        )
        plugin_keepers = (
            "invoke_markdown_auto_lint.py",
            "invoke_markdownlint_guard.py",
        )
        # invoke_auto_retrospective.py left this list in #3349: it was the
        # last shim in the Stop group and was deleted, not relocated.
        internal_keepers = ("invoke_context_loader.py",)

        for manifest in manifests:
            serialized = json.dumps(manifest) + json.dumps(_effective_commands(manifest))
            assert all(script not in serialized for script in removed)

        serialized_plugin = json.dumps(_effective_commands(plugin_hooks))
        serialized_settings = json.dumps(_effective_commands(settings))
        assert all(script in serialized_plugin for script in plugin_keepers)
        assert all(script not in serialized_settings for script in plugin_keepers)
        assert all(script in serialized_settings for script in internal_keepers)
        assert "invoke_observation_sync.py" not in serialized_plugin
        assert "invoke_observation_sync.py" in serialized_settings

        pretooluse_manifest = json.loads(
            (_COPILOT / "hooks" / "PreToolUse" / "_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        serialized_generated = json.dumps(pretooluse_manifest)
        assert all(
            script.removesuffix(".py") not in serialized_generated
            for script in removed
        )
        assert "invoke_markdownlint_guard" in serialized_generated

        posttooluse_manifest = json.loads(
            (_COPILOT / "hooks" / "PostToolUse" / "_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        assert {
            f"{shim.split('__', 1)[0]}.py"
            for shim in posttooluse_manifest["shims"]
        } == {
            "invoke_markdown_auto_lint.py",
        }

        generated_events = {
            path.parent.name
            for path in (_COPILOT / "hooks").glob("*/_manifest.json")
            if path.is_file()
        }
        assert generated_events == set(_ALL_EVENTS)

    def test_manifest_modes_match_event_role(self):
        # PreToolUse gates (fail-closed); the rest observe (run all, exit 0).
        for event in _ALL_EVENTS:
            manifest = json.loads(
                (_COPILOT / "hooks" / event / "_manifest.json").read_text(encoding="utf-8")
            )
            expected = "gate" if event == _GATING else "observe"
            assert manifest["mode"] == expected, f"{event}: mode={manifest['mode']!r}"

    def test_each_event_has_manifest_entrypoint_and_bootstrap(self):
        for event in _ALL_EVENTS:
            event_dir = _COPILOT / "hooks" / event
            assert (event_dir / "_dispatch.py").is_file(), f"{event}: no _dispatch.py"
            # The entrypoint imports ensure_plugin_paths from a sibling
            # _bootstrap.py; every consolidated event dir needs its own copy.
            assert (event_dir / "_bootstrap.py").is_file(), f"{event}: no _bootstrap.py"
            manifest = json.loads((event_dir / "_manifest.json").read_text(encoding="utf-8"))
            assert manifest["shims"], f"{event}: empty manifest"
            assert set(manifest["timeouts"]) == set(manifest["shims"])
            assert _hooks()[event][0]["timeoutSec"] == (
                sum(manifest["timeouts"].values()) + _DISPATCHER_TIMEOUT_HEADROOM_SEC
            )
            for shim in manifest["shims"]:
                assert (event_dir / shim).is_file(), f"{event}: manifest shim {shim} missing"

    def test_no_unregistered_matcher_shims_are_shipped(self):
        for event in _ALL_EVENTS:
            event_dir = _COPILOT / "hooks" / event
            manifest = json.loads(
                (event_dir / "_manifest.json").read_text(encoding="utf-8")
            )
            registered = set(manifest["shims"])
            stale = []
            for path in event_dir.glob("*.py"):
                if path.name in registered:
                    continue
                source = path.read_text(encoding="utf-8")
                if is_shimmed(source) and detect_reason_strict(path) is None:
                    stale.append(path.name)
            assert sorted(stale) == [], f"{event}: unregistered matcher shims: {stale}"

    def test_pretooluse_allows_non_matching_tool(self):
        proc = _run_entry(_GATING, {"tool_name": "____NoSuchTool____", "tool_input": {}})
        assert proc.returncode == 0, proc.stderr.decode()[:600]

    def test_observe_events_run_in_one_process_and_return_zero(self):
        # Each observational dispatcher runs its real shim set end to end and
        # returns 0 (observe mode never gates). This exercises the committed
        # artifact under the real plugin-root contract, not a string match.
        for event in _OBSERVE_EVENTS:
            proc = _run_entry(event, {"tool_name": "Read", "tool_input": {}})
            assert proc.returncode == 0, (
                f"{event}: observe dispatcher returned {proc.returncode}\n"
                f"{proc.stderr.decode()[:600]}"
            )

    def test_push_pr_identity_guard_excluded_from_pretooluse_manifest_and_hooks(self):
        """Issue #5013: the push-pr identity guard must not ship to Copilot.

        dispatch_groups.json marks the guard's shim entry
        ``copilotExclude: true``; generate_hooks_expand.py drops any such
        shim before it reaches the Copilot tree (#5013). This asserts the
        COMMITTED artifact reflects that: no shim file, no timeout entry, and
        no mention in the hooks.json dispatcher registration strings, while
        the other active PreToolUse shims are still registered.
        """
        guard_marker = "push_pr_script_identity_guard"
        event_dir = _COPILOT / "hooks" / _GATING
        manifest = json.loads((event_dir / "_manifest.json").read_text(encoding="utf-8"))

        assert not any(guard_marker in shim for shim in manifest["shims"]), manifest["shims"]
        assert not any(guard_marker in shim for shim in manifest["timeouts"]), (
            manifest["timeouts"]
        )

        # Other active PreToolUse shims remain registered; the guard's
        # exclusion must not have taken a sibling down with it.
        assert any("invoke_markdownlint_guard" in shim for shim in manifest["shims"])
        assert any("invoke_require_subagent_model" in shim for shim in manifest["shims"])

        for entry in _hooks()[_GATING]:
            assert guard_marker not in entry.get("bash", "")
            assert guard_marker not in entry.get("powershell", "")

        # The shim file itself must not be shipped either; a generator
        # omission that left a stray copy on disk would still be a partial
        # decommission Copilot's file-scan in _dispatch.py could pick back up.
        stale = [p.name for p in event_dir.glob("*.py") if guard_marker in p.name]
        assert stale == [], f"guard file still shipped despite exclusion: {stale}"

    def test_push_pr_identity_guard_companions_absent_from_copilot_but_kept_for_claude(self):
        """Issue #5013: the guard's runtime companions must not ship either.

        The guard's own shim file not containing ``push_pr_script_identity_guard``
        in its name (the previous test's ``stale`` check) does NOT prove its
        NINE companion modules (``_push_pr_guard_commands.py`` and siblings,
        looked up here from the OWNERSHIP TABLE
        ``generate_hooks_events._COMPANIONS_BY_OWNER`` -- an "ownership table
        that already names its companions" -- not a hardcoded list) are gone
        too: none of their filenames contain that marker, so a generator that
        dropped only the owner and left every companion behind would still
        pass that check. ``find_stale_matcher_shims`` only recognizes
        shim-WRAPPED files (``is_shimmed``); a companion is a plain,
        never-shimmed module, so this is the one test that would catch that
        specific miss. The canonical Claude source companions must remain
        untouched: Claude Code keeps running the guard unchanged.
        """
        owner_key = "PreToolUse/invoke_push_pr_script_identity_guard.py"
        companions = _COMPANIONS_BY_OWNER[owner_key]
        assert len(companions) == 9, companions

        claude_dir = _REPO / ".claude" / "hooks" / "PreToolUse"
        for companion_name in companions:
            assert (claude_dir / companion_name).is_file(), (
                f"canonical Claude companion missing: {companion_name}"
            )

        copilot_event_dir = _COPILOT / "hooks" / _GATING
        for companion_name in companions:
            assert not (copilot_event_dir / companion_name).exists(), (
                f"companion still shipped to Copilot despite owner exclusion: {companion_name}"
            )

    @pytest.mark.parametrize(
        "command",
        [
            pytest.param("echo hello world", id="ordinary-unrelated-command"),
            pytest.param(
                "python3 attacker/pr/new_pr.py --title fix",
                id="pre-5013-denied-lookalike",
            ),
        ],
    )
    def test_pretooluse_bash_payload_never_launches_push_pr_guard(self, command: str):
        """A Bash payload must not launch or reference the retired push-pr
        identity guard through the generated manifest path.

        Two shapes: an ordinary unrelated command that never touched the
        guard, and the pre-#5013 attack shape (a repository-controlled
        ``new_pr.py`` lookalike) the guard used to deny. The second shape is
        the meaningful control: if the shim were still wired in by accident,
        THIS command would come back denied where the first would not
        detect it. This runs the SHIPPED
        ``src/copilot-cli/hooks/PreToolUse/_dispatch.py`` end to end (not
        the generator) and asserts both allow and silence: the guard's
        module name must not appear anywhere in the dispatcher's own
        diagnostics.
        """
        guard_marker = "push_pr_script_identity_guard"
        proc = _run_entry(
            _GATING,
            {
                "tool_name": "Bash",
                "tool_input": {"command": command},
                "cwd": str(_REPO),
            },
        )

        assert proc.returncode == 0, (
            f"payload was denied: {proc.returncode}\n{proc.stderr.decode()[:600]}"
        )
        combined = proc.stdout.decode(errors="replace") + proc.stderr.decode(errors="replace")
        assert guard_marker not in combined, combined[:600]

"""Committed-artifact regression for the Copilot universal dispatcher cutover.

ADR-068 / #2295 / #2342. Asserts the generated src/copilot-cli/hooks/ tree
consolidates EVERY event to one dispatcher entry, that the tool-gating event
(PreToolUse) runs in gate mode (fail-closed short-circuit, unchanged) and the
observational events (PostToolUse, SessionStart, SessionEnd, UserPromptSubmit)
run in observe mode (all shims run, exit 0), and that the generated entrypoint
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

_REPO = Path(__file__).resolve().parents[2]
_COPILOT = _REPO / "src" / "copilot-cli"
_HOOKS_JSON = _COPILOT / "hooks" / "hooks.json"
_GATING = "PreToolUse"
_OBSERVE_EVENTS = ("PostToolUse", "SessionStart", "SessionEnd", "UserPromptSubmit")
_ALL_EVENTS = (_GATING, *_OBSERVE_EVENTS)
_DISPATCH_TEST_TIMEOUT_CAP_SEC = 60


def _hooks() -> dict[str, list[dict[str, Any]]]:
    data = json.loads(_HOOKS_JSON.read_text(encoding="utf-8"))
    return cast("dict[str, list[dict[str, Any]]]", data["hooks"])


def _run_entry(event: str, payload: dict[str, Any]) -> subprocess.CompletedProcess[bytes]:
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(_REPO)
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
        # #2342: exactly five events, each collapsed to a single dispatcher entry.
        assert set(hooks) == set(_ALL_EVENTS), f"unexpected event set: {sorted(hooks)}"
        for event in _ALL_EVENTS:
            entries = hooks[event]
            assert len(entries) == 1, f"{event}: expected 1 dispatcher entry, got {len(entries)}"
            assert f"/hooks/{event}/_dispatch.py" in entries[0]["bash"]
            assert f"/hooks/{event}/_dispatch.py" in entries[0]["powershell"]

    def test_only_advisory_pretooluse_registrations_are_absent(self):
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
            "invoke_correction_applier.py",
            "invoke_topical_memory_injection.py",
        )
        required_hard_gates = (
            "invoke_branch_context_guard.py",
            "invoke_branch_protection_guard.py",
            "invoke_security_commit_gate.py",
            "invoke_security_gate.py",
            "invoke_session_log_guard.py",
        )
        required_session_start = (
            "invoke_session_initialization_enforcer.py",
            "invoke_context_loader.py",
        )

        for manifest in manifests:
            serialized = json.dumps(manifest)
            assert all(script not in serialized for script in removed)
            assert all(script in serialized for script in required_hard_gates)

        serialized_settings = json.dumps(settings)
        assert all(script in serialized_settings for script in required_session_start)

        generated = json.loads(
            (_COPILOT / "hooks" / "PreToolUse" / "_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        serialized_generated = json.dumps(generated)
        assert all(script not in serialized_generated for script in removed)
        assert all(
            script.removesuffix(".py") in serialized_generated
            for script in required_hard_gates
        )
        session_start_manifest = json.loads(
            (_COPILOT / "hooks" / "SessionStart" / "_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        serialized_session_start = json.dumps(session_start_manifest)
        assert all(script in serialized_session_start for script in required_session_start)

    def test_session_start_enforcer_has_one_registration_per_manifest(self):
        script_name = "invoke_session_initialization_enforcer.py"
        settings = json.loads(
            (_REPO / ".claude" / "settings.json").read_text(encoding="utf-8")
        )
        settings_commands = [
            hook["command"]
            for group in settings["hooks"]["SessionStart"]
            for hook in group["hooks"]
        ]
        plugin_hooks = json.loads(
            (_REPO / ".claude" / "hooks" / "hooks.json").read_text(
                encoding="utf-8"
            )
        )
        plugin_commands = [
            hook["command"]
            for group in plugin_hooks["hooks"]["SessionStart"]
            for hook in group["hooks"]
        ]
        generated_manifest = json.loads(
            (_COPILOT / "hooks" / "SessionStart" / "_manifest.json").read_text(
                encoding="utf-8"
            )
        )

        assert sum(script_name in command for command in settings_commands) == 1
        assert sum(script_name in command for command in plugin_commands) == 1
        assert generated_manifest["shims"].count(script_name) == 1

    def test_one_session_start_origin_emits_branch_session_once(self):
        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = str(_REPO)
        env["CLAUDE_PLUGIN_ROOT"] = str(_COPILOT)
        env["COPILOT_PLUGIN_ROOT"] = str(_COPILOT)
        env["AI_AGENTS_PROJECT_REPO"] = "1"
        script = (
            _COPILOT
            / "hooks"
            / "SessionStart"
            / "invoke_session_initialization_enforcer.py"
        )

        process = subprocess.run(
            [sys.executable, "-u", str(script)],
            input=b"{}",
            capture_output=True,
            cwd=_REPO,
            env=env,
            timeout=15,
        )

        assert process.returncode == 0, process.stderr.decode(errors="replace")
        assert process.stdout.count(b"Branch: `") == 1
        assert process.stdout.count(b" | Session: ") == 1

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
            assert _hooks()[event][0]["timeoutSec"] == sum(manifest["timeouts"].values())
            for shim in manifest["shims"]:
                assert (event_dir / shim).is_file(), f"{event}: manifest shim {shim} missing"

    def test_session_end_skill_loader_is_shipped_but_not_dispatched(self):
        event_dir = _COPILOT / "hooks" / "SessionEnd"
        manifest = json.loads(
            (event_dir / "_manifest.json").read_text(encoding="utf-8")
        )
        canonical = _REPO / ".claude" / "hooks" / "Stop" / "skill_pattern_loader.py"
        shipped = event_dir / "skill_pattern_loader.py"

        assert shipped.is_file()
        assert "skill_pattern_loader.py" not in manifest["shims"]
        # The companion is copied verbatim (no matcher shim is injected for
        # unmatched hooks), so the shipped bytes must equal the canonical
        # source exactly, not merely both exist (#12).
        assert shipped.read_bytes() == canonical.read_bytes()

    def test_pretooluse_allows_non_matching_tool(self):
        proc = _run_entry(_GATING, {"tool_name": "____NoSuchTool____", "tool_input": {}})
        assert proc.returncode == 0, proc.stderr.decode()[:600]

    def test_pretooluse_denies_blocked_tool(self):
        # An unresolvable cwd trips branch protection fail-closed; the dispatcher
        # must deny (#2295 preserved end-to-end through consolidation).
        proc = _run_entry(
            _GATING,
            {
                "cwd": str(_REPO / "missing-dispatcher-test-repo"),
                "tool_name": "Bash",
                "tool_input": {
                    "command": "git push origin fix/workflow-local-test-secrets-2841"
                },
            },
        )
        assert proc.returncode != 0, "dispatcher allowed a tool a guard blocks"
        combined = proc.stdout + proc.stderr
        assert b"block" in combined.lower() or b"session" in combined.lower()

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

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

_REPO = Path(__file__).resolve().parents[2]
_COPILOT = _REPO / "src" / "copilot-cli"
_HOOKS_JSON = _COPILOT / "hooks" / "hooks.json"
_GATING = "PreToolUse"
_OBSERVE_EVENTS = ("PostToolUse", "SessionStart", "SessionEnd", "UserPromptSubmit")
_ALL_EVENTS = (_GATING, *_OBSERVE_EVENTS)


def _hooks() -> dict:
    return json.loads(_HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]


def _run_entry(event: str, payload: dict) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["CLAUDE_PLUGIN_ROOT"] = str(_COPILOT)
    env["COPILOT_PLUGIN_ROOT"] = str(_COPILOT)
    event_timeout_sec = int(_hooks()[event][0]["timeoutSec"])
    return subprocess.run(
        [sys.executable, "-u", str(_COPILOT / "hooks" / event / "_dispatch.py")],
        input=json.dumps(payload).encode(),
        capture_output=True,
        env=env,
        timeout=event_timeout_sec + 5,
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

    def test_pretooluse_allows_non_matching_tool(self):
        proc = _run_entry(_GATING, {"tool_name": "____NoSuchTool____", "tool_input": {}})
        assert proc.returncode == 0, proc.stderr.decode()[:600]

    def test_pretooluse_denies_blocked_tool(self):
        # Raw gh trips the skill-first guard; the dispatcher must deny (#2295
        # fail-closed preserved end-to-end through consolidation).
        proc = _run_entry(
            _GATING, {"tool_name": "Bash", "tool_input": {"command": "gh issue list"}}
        )
        assert proc.returncode != 0, "dispatcher allowed a tool a guard blocks"
        assert b"Raw" in proc.stdout or b"Blocked" in proc.stdout or b"skill" in proc.stderr.lower()

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

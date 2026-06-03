"""Committed-artifact regression for the Copilot PreToolUse dispatcher cutover.

ADR-068 / #2295. Asserts the generated src/copilot-cli/hooks/ tree consolidates
the tool-gating event (PreToolUse) to one dispatcher entry and that the
generated entrypoint runs the real guard set in one process with correct
allow/deny behavior. Observational events keep per-shim entries. Runs in CI
against the committed artifacts using this repo as the plugin root.
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


def _hooks() -> dict:
    return json.loads(_HOOKS_JSON.read_text())["hooks"]


def _run_entry(event: str, payload: dict) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["CLAUDE_PLUGIN_ROOT"] = str(_COPILOT)
    env["COPILOT_PLUGIN_ROOT"] = str(_COPILOT)
    return subprocess.run(
        [sys.executable, "-u", str(_COPILOT / "hooks" / event / "_dispatch.py")],
        input=json.dumps(payload).encode(),
        capture_output=True,
        env=env,
        timeout=60,
    )


class TestDispatcherArtifacts:
    def test_gating_event_is_one_dispatcher_entry(self):
        entries = _hooks()[_GATING]
        assert len(entries) == 1, f"{_GATING}: expected 1 dispatcher entry, got {len(entries)}"
        assert f"/hooks/{_GATING}/_dispatch.py" in entries[0]["bash"]
        assert f"/hooks/{_GATING}/_dispatch.py" in entries[0]["powershell"]

    def test_observational_events_stay_per_shim(self):
        # Only the tool-gating event is consolidated; the rest keep per-shim
        # entries so the host runs all observers (no short-circuit change).
        for event, entries in _hooks().items():
            if event == _GATING:
                continue
            assert not any("_dispatch.py" in e.get("bash", "") for e in entries), (
                f"{event}: unexpectedly consolidated"
            )

    def test_gating_manifest_and_entrypoint_present(self):
        event_dir = _COPILOT / "hooks" / _GATING
        assert (event_dir / "_dispatch.py").is_file()
        manifest = json.loads((event_dir / "_manifest.json").read_text())
        assert manifest["shims"], "empty manifest"
        assert set(manifest["timeouts"]) == set(manifest["shims"])
        assert _hooks()[_GATING][0]["timeoutSec"] == sum(manifest["timeouts"].values())
        for shim in manifest["shims"]:
            assert (event_dir / shim).is_file(), f"manifest shim {shim} missing on disk"

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

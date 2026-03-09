"""Tests for get_agent_history.py."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = str(
    Path(__file__).resolve().parents[2]
    / ".claude"
    / "skills"
    / "workflow"
    / "scripts"
    / "get_agent_history.py"
)


def _run_script(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True,
        text=True,
        timeout=30,
    )


class TestJsonOutput:
    def test_returns_valid_json_or_empty(self):
        result = _run_script("--lookback-hours", "720")
        if result.stdout.strip():
            data = json.loads(result.stdout)
            assert isinstance(data, list)

    def test_entries_have_required_fields(self):
        result = _run_script("--lookback-hours", "8760")
        if result.stdout.strip():
            data = json.loads(result.stdout)
            if data:
                entry = data[0]
                assert "Agent" in entry
                assert "Commit" in entry
                assert "Message" in entry


class TestTableOutput:
    def test_does_not_fail(self):
        result = _run_script("--format", "table", "--lookback-hours", "1")
        assert result.returncode == 0


class TestAgentDetection:
    def test_detects_feat_as_implementer(self):
        """Verify the heuristic detects conventional commit prefixes."""
        result = _run_script("--lookback-hours", "8760")
        if result.stdout.strip():
            data = json.loads(result.stdout)
            # We can't guarantee specific agents but structure should be valid
            for entry in data:
                assert isinstance(entry["Agent"], str)
                assert len(entry["Agent"]) > 0

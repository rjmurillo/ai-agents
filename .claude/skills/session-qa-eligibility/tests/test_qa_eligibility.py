#!/usr/bin/env python3
"""Tests for session-qa-eligibility test_investigation_eligibility.py script."""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import subprocess
from unittest import mock

_SCRIPT = os.path.join(
    os.path.dirname(__file__), "..", "scripts", "test_investigation_eligibility.py",
)


def _load_module():
    spec = importlib.util.spec_from_file_location("qa_eligibility_script", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestFileMatchesAllowlist:
    def test_agents_sessions(self):
        mod = _load_module()
        assert mod._file_matches_allowlist(".agents/sessions/2026-01-01-session-1.json")

    def test_agents_analysis(self):
        mod = _load_module()
        assert mod._file_matches_allowlist(".agents/analysis/report.md")

    def test_serena_memories(self):
        mod = _load_module()
        assert mod._file_matches_allowlist(".serena/memories/test.md")

    def test_code_file_rejected(self):
        mod = _load_module()
        assert not mod._file_matches_allowlist("scripts/main.py")

    def test_backslash_normalized(self):
        mod = _load_module()
        assert mod._file_matches_allowlist(".agents\\sessions\\log.json")


class TestMainFunction:
    def test_eligible_when_all_allowed(self, capsys):
        mod = _load_module()

        def mock_run(cmd, **kwargs):
            return subprocess.CompletedProcess(
                cmd, 0,
                stdout=".agents/sessions/log.json\n.serena/memories/test.md\n",
                stderr="",
            )

        with mock.patch("subprocess.run", side_effect=mock_run):
            result = mod.main()

        assert result == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Eligible"] is True

    def test_not_eligible_when_violation(self, capsys):
        mod = _load_module()

        def mock_run(cmd, **kwargs):
            return subprocess.CompletedProcess(
                cmd, 0,
                stdout=".agents/sessions/log.json\nscripts/main.py\n",
                stderr="",
            )

        with mock.patch("subprocess.run", side_effect=mock_run):
            result = mod.main()

        assert result == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Eligible"] is False
        assert "scripts/main.py" in output["Violations"]

    def test_always_exits_0(self, capsys):
        mod = _load_module()

        def mock_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 128, stdout="", stderr="error")

        with mock.patch("subprocess.run", side_effect=mock_run):
            result = mod.main()

        assert result == 0

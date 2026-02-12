#!/usr/bin/env python3
"""Tests for session skill test_investigation_eligibility.py."""

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
    spec = importlib.util.spec_from_file_location("test_investigation_eligibility", _SCRIPT)
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

    def test_agents_retrospective(self):
        mod = _load_module()
        assert mod._file_matches_allowlist(".agents/retrospective/retro.md")

    def test_serena_memories(self):
        mod = _load_module()
        assert mod._file_matches_allowlist(".serena/memories/test.md")

    def test_agents_security(self):
        mod = _load_module()
        assert mod._file_matches_allowlist(".agents/security/scan.md")

    def test_agents_memory(self):
        mod = _load_module()
        assert mod._file_matches_allowlist(".agents/memory/index.md")

    def test_agents_architecture_review(self):
        mod = _load_module()
        assert mod._file_matches_allowlist(".agents/architecture/REVIEW-ADR-034.md")

    def test_agents_critique(self):
        mod = _load_module()
        assert mod._file_matches_allowlist(".agents/critique/plan.md")

    def test_code_file_rejected(self):
        mod = _load_module()
        assert not mod._file_matches_allowlist("scripts/main.py")

    def test_src_file_rejected(self):
        mod = _load_module()
        assert not mod._file_matches_allowlist("src/MyClass.cs")

    def test_workflow_rejected(self):
        mod = _load_module()
        assert not mod._file_matches_allowlist(".github/workflows/ci.yml")

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
        assert output["Violations"] == []

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

    def test_git_error_returns_0_with_error_field(self, capsys):
        mod = _load_module()

        def mock_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 128, stdout="", stderr="fatal: not a git repo")

        with mock.patch("subprocess.run", side_effect=mock_run):
            result = mod.main()

        assert result == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Eligible"] is False
        assert "Error" in output

    def test_empty_staged_is_eligible(self, capsys):
        mod = _load_module()

        def mock_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with mock.patch("subprocess.run", side_effect=mock_run):
            result = mod.main()

        assert result == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Eligible"] is True

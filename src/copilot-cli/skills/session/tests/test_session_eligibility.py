#!/usr/bin/env python3
"""Tests for session skill test_investigation_eligibility.py script."""

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

    def test_agents_memory_episodes(self):
        mod = _load_module()
        assert mod._file_matches_allowlist(".agents/memory/episodes/episode-2026-01-01.json")

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
                stdout="A\t.agents/sessions/log.json\nM\t.serena/memories/test.md\n",
                stderr="",
            )

        with mock.patch("subprocess.run", side_effect=mock_run):
            result = mod.main([])

        assert result == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Eligible"] is True
        assert output["Violations"] == []

    def test_not_eligible_when_violation(self, capsys):
        mod = _load_module()

        def mock_run(cmd, **kwargs):
            return subprocess.CompletedProcess(
                cmd, 0,
                stdout="A\t.agents/sessions/log.json\nM\tscripts/main.py\n",
                stderr="",
            )

        with mock.patch("subprocess.run", side_effect=mock_run):
            result = mod.main([])

        assert result == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Eligible"] is False
        assert "scripts/main.py" in output["Violations"]

    def test_git_error_returns_0_with_error_field(self, capsys):
        mod = _load_module()

        def mock_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 128, stdout="", stderr="fatal: not a git repo")

        with mock.patch("subprocess.run", side_effect=mock_run):
            result = mod.main([])

        assert result == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Eligible"] is False
        assert "Error" in output

    def test_empty_staged_is_eligible(self, capsys):
        mod = _load_module()

        def mock_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with mock.patch("subprocess.run", side_effect=mock_run):
            result = mod.main([])

        assert result == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Eligible"] is True

    def test_base_ref_includes_committed_and_uncommitted_changes(self, capsys):
        mod = _load_module()
        outputs = {
            ("git", "diff", "--name-status", "--find-renames", "--no-ext-diff", "a" * 40 + "..HEAD", "--"): (
                "M\t.agents/analysis/report.md\n"
            ),
            ("git", "diff", "--cached", "--name-status", "--find-renames", "--no-ext-diff", "--"): (
                "A\t.agents/sessions/log.json\n"
            ),
            ("git", "diff", "--name-status", "--find-renames", "--no-ext-diff", "--"): (
                "M\t.serena/memories/test.md\n"
            ),
            ("git", "ls-files", "--others", "--exclude-standard"): (
                ".agents/retrospective/retro.md\n"
            ),
        }

        def mock_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 0, stdout=outputs[tuple(cmd)], stderr="")

        with mock.patch("subprocess.run", side_effect=mock_run):
            result = mod.main(["--base-ref", "a" * 40])

        assert result == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Eligible"] is True
        assert len(output["ChangedFiles"]) == 4
        assert output["StagedFiles"] == output["ChangedFiles"]

    def test_base_ref_rejects_renamed_code_source(self, capsys):
        mod = _load_module()

        def mock_run(cmd, **kwargs):
            stdout = ""
            if any(str(arg).endswith("..HEAD") for arg in cmd):
                stdout = "R100\tscripts/main.py\t.agents/analysis/main.md\n"
            return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

        with mock.patch("subprocess.run", side_effect=mock_run):
            result = mod.main(["--base-ref", "a" * 40])

        assert result == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Eligible"] is False
        assert output["Violations"] == ["scripts/main.py"]

    def test_explicit_head_ref_checks_only_committed_range(self, capsys):
        mod = _load_module()
        base_ref = "a" * 40
        head_ref = "b" * 40
        allowed_path = mod._ALLOWLIST_DISPLAY[1] + "report.md"

        def mock_run(cmd, **kwargs):
            assert cmd == [
                "git",
                "log",
                "--first-parent",
                "--no-merges",
                "--name-status",
                "--find-renames",
                "--no-ext-diff",
                "--format=",
                f"{base_ref}..{head_ref}",
                "--",
            ]
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=f"M\t{allowed_path}\n",
                stderr="",
            )

        with mock.patch("subprocess.run", side_effect=mock_run):
            result = mod.main(["--base-ref", base_ref, "--head-ref", head_ref])

        assert result == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Eligible"] is True
        assert output["ChangedFiles"] == [allowed_path]

    def test_invalid_base_ref_fails_closed(self, capsys):
        mod = _load_module()

        result = mod.main(["--base-ref=--option"])

        assert result == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Eligible"] is False
        assert "Invalid base ref" in output["Error"]

    def test_invalid_head_ref_fails_closed(self, capsys):
        mod = _load_module()

        result = mod.main(["--base-ref", "a" * 40, "--head-ref=--option"])

        assert result == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Eligible"] is False
        assert "Invalid head ref" in output["Error"]


class TestAllowlistIntegrity:
    def test_all_patterns_compile(self):
        import re
        mod = _load_module()
        for pattern in mod._ALLOWLIST_PATTERNS:
            re.compile(pattern)

    def test_patterns_and_display_aligned(self):
        mod = _load_module()
        assert len(mod._ALLOWLIST_PATTERNS) == len(mod._ALLOWLIST_DISPLAY)

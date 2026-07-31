"""Tests for agent-drift-detection CI scripts (issue #3521).

Covers:
  - check_plugin_lib_mirrors.py
  - show_drift_failure.py
  - write_drift_job_summary.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "ci"))

import check_plugin_lib_mirrors as cplm
import show_drift_failure as sdf
import write_drift_job_summary as wdjs

# ---------------------------------------------------------------------------
# check_plugin_lib_mirrors
# ---------------------------------------------------------------------------


class TestCheckPluginLibMirrors:
    def test_both_pass_returns_0(self) -> None:
        with patch("subprocess.run", return_value=MagicMock(returncode=0)):
            rc = cplm.main()
        assert rc == 0

    def test_mirror_fails_returns_mirror_rc(self) -> None:
        side_effects = [MagicMock(returncode=2), MagicMock(returncode=0)]
        with patch("subprocess.run", side_effect=side_effects):
            rc = cplm.main()
        assert rc == 2

    def test_build_fails_returns_build_rc(self) -> None:
        side_effects = [MagicMock(returncode=0), MagicMock(returncode=3)]
        with patch("subprocess.run", side_effect=side_effects):
            rc = cplm.main()
        assert rc == 3

    def test_both_fail_returns_mirror_rc(self) -> None:
        side_effects = [MagicMock(returncode=1), MagicMock(returncode=2)]
        with patch("subprocess.run", side_effect=side_effects):
            rc = cplm.main()
        assert rc == 1

    def test_calls_both_scripts(self) -> None:
        captured: list[list] = []

        def fake_run(cmd, **kwargs):
            captured.append(cmd)
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=fake_run):
            cplm.main()

        assert len(captured) == 2
        assert any("sync_plugin_lib.py" in str(c) for c in captured)
        assert any("build_all.py" in str(c) for c in captured)

    def test_both_scripts_called_with_check_flag(self) -> None:
        captured: list[list] = []

        def fake_run(cmd, **kwargs):
            captured.append(cmd)
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=fake_run):
            cplm.main()

        for cmd in captured:
            assert "--check" in cmd


# ---------------------------------------------------------------------------
# show_drift_failure
# ---------------------------------------------------------------------------


class TestShowDriftFailure:
    def test_prints_drift_header(self, capsys: pytest.CaptureFixture) -> None:
        with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")):
            sdf.show_drift_failure("success", "success", "success")
        out = capsys.readouterr().out
        assert "AGENT DRIFT DETECTED" in out

    def test_runs_generate_agents_on_validate_failure(self) -> None:
        calls_made: list[list] = []

        def fake_run(cmd, **kwargs):
            calls_made.append(cmd)
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=fake_run):
            sdf.show_drift_failure("failure", "success", "success")

        assert any("generate_agents.py" in str(c) for c in calls_made)

    def test_does_not_run_generate_agents_on_success(self) -> None:
        calls_made: list[list] = []

        def fake_run(cmd, **kwargs):
            calls_made.append(cmd)
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=fake_run):
            sdf.show_drift_failure("success", "success", "success")

        assert not any("generate_agents.py" in str(c) for c in calls_made)

    def test_runs_mirror_scripts_on_lib_mirror_failure(self) -> None:
        calls_made: list[list] = []

        def fake_run(cmd, **kwargs):
            calls_made.append(cmd)
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=fake_run):
            sdf.show_drift_failure("success", "failure", "success")

        assert any("sync_plugin_lib.py" in str(c) for c in calls_made)
        assert any("build_all.py" in str(c) for c in calls_made)

    def test_shows_changed_files(self, capsys: pytest.CaptureFixture) -> None:
        git_diff_result = MagicMock(returncode=0, stdout="src/file.ts\n", stderr="")
        other_result = MagicMock(returncode=0, stdout="", stderr="")

        def fake_run(cmd, **kwargs):
            if any("name-only" in part for part in cmd):
                return git_diff_result
            return other_result

        with patch("subprocess.run", side_effect=fake_run):
            sdf.show_drift_failure("success", "success", "success")

        out = capsys.readouterr().out
        assert "src/file.ts" in out
        assert "How to fix" in out

    def test_no_changed_files_no_remediation(self, capsys: pytest.CaptureFixture) -> None:
        def fake_run(cmd, **kwargs):
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=fake_run):
            sdf.show_drift_failure("success", "success", "success")

        out = capsys.readouterr().out
        assert "How to fix" not in out

    def test_main_reads_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("VALIDATE_CONCLUSION", "failure")
        monkeypatch.setenv("LIB_MIRROR_CONCLUSION", "success")
        monkeypatch.setenv("MANIFEST_PARITY_CONCLUSION", "success")
        calls_made: list[list] = []

        def fake_run(cmd, **kwargs):
            calls_made.append(cmd)
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=fake_run):
            rc = sdf.main()

        assert rc == sdf.EXIT_OK
        assert any("generate_agents.py" in str(c) for c in calls_made)


# ---------------------------------------------------------------------------
# write_drift_job_summary
# ---------------------------------------------------------------------------


class TestWriteDriftJobSummary:
    def test_passed_when_all_success(self) -> None:
        text = wdjs.build_summary("success", "success", "success")
        assert "Passed" in text
        assert "Failed" not in text

    def test_failed_when_any_not_success(self) -> None:
        text = wdjs.build_summary("failure", "success", "success")
        assert "Failed" in text
        assert "Passed" not in text

    def test_includes_monitored_paths(self) -> None:
        text = wdjs.build_summary("success", "success", "success")
        assert "templates/" in text
        assert "vs-code-agents" in text
        assert "copilot-cli" in text

    def test_main_writes_to_summary_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        monkeypatch.setenv("VALIDATE_CONCLUSION", "success")
        monkeypatch.setenv("LIB_MIRROR_CONCLUSION", "success")
        monkeypatch.setenv("MANIFEST_PARITY_CONCLUSION", "success")
        rc = wdjs.main()
        assert rc == wdjs.EXIT_OK
        content = summary.read_text()
        assert "Agent Drift Detection Passed" in content

    def test_main_writes_failure_summary(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        monkeypatch.setenv("VALIDATE_CONCLUSION", "failure")
        monkeypatch.setenv("LIB_MIRROR_CONCLUSION", "success")
        monkeypatch.setenv("MANIFEST_PARITY_CONCLUSION", "success")
        rc = wdjs.main()
        assert rc == wdjs.EXIT_OK
        content = summary.read_text()
        assert "Agent Drift Detection Failed" in content

    def test_main_prints_when_no_summary_env(
        self, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        monkeypatch.setenv("VALIDATE_CONCLUSION", "success")
        monkeypatch.setenv("LIB_MIRROR_CONCLUSION", "success")
        monkeypatch.setenv("MANIFEST_PARITY_CONCLUSION", "success")
        rc = wdjs.main()
        assert rc == wdjs.EXIT_OK
        out = capsys.readouterr().out
        assert "Agent Drift Detection Passed" in out

    def test_lib_mirror_failure_shows_failed(self) -> None:
        text = wdjs.build_summary("success", "failure", "success")
        assert "Failed" in text

    def test_manifest_parity_failure_shows_failed(self) -> None:
        text = wdjs.build_summary("success", "success", "failure")
        assert "Failed" in text

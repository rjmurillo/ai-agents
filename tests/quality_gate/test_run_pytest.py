"""Tests for scripts/quality_gate/run_pytest.py.

Pins the status/summary derivation of the extracted ``Run pytest`` workflow
step. The pytest subprocess and tool detection are mocked; no real test run
is launched.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.quality_gate import run_pytest as mod
from scripts.quality_gate.run_pytest import (
    build_pytest_command,
    environment_ready,
    main,
    run_pytest,
    summary_line,
    write_outputs,
)


# ---------------------------------------------------------------------------
# summary_line
# ---------------------------------------------------------------------------


class TestSummaryLine:
    def test_picks_last_matching_line(self) -> None:
        output = "collected 3 items\n2 passed, 1 failed in 0.5s\n"
        assert summary_line(output) == "2 passed, 1 failed in 0.5s"

    def test_default_when_no_match(self) -> None:
        assert summary_line("nothing here\nmove along\n") == "No test summary available"

    def test_matches_error_keyword(self) -> None:
        assert "error" in summary_line("1 error during collection\n")

    def test_strips_whitespace(self) -> None:
        assert summary_line("  5 passed in 1s  \n") == "5 passed in 1s"


# ---------------------------------------------------------------------------
# build_pytest_command
# ---------------------------------------------------------------------------


class TestBuildPytestCommand:
    def test_prefers_uv_when_present(self, monkeypatch) -> None:
        monkeypatch.setattr(mod.shutil, "which", lambda name: "/usr/bin/uv")
        cmd = build_pytest_command()
        assert cmd[:3] == ["uv", "run", "pytest"]
        assert "--tb=short" in cmd
        assert "-q" in cmd

    def test_falls_back_to_python_m_pytest(self, monkeypatch) -> None:
        monkeypatch.setattr(mod.shutil, "which", lambda name: None)
        cmd = build_pytest_command()
        assert cmd[1:3] == ["-m", "pytest"]
        assert cmd[0] == mod.sys.executable


# ---------------------------------------------------------------------------
# environment_ready
# ---------------------------------------------------------------------------


class TestEnvironmentReady:
    def test_ready_when_python_and_pyproject(self, tmp_path, monkeypatch) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]", encoding="utf-8")
        monkeypatch.setattr(mod.shutil, "which", lambda name: "/usr/bin/python")
        assert environment_ready(tmp_path) is True

    def test_not_ready_without_pyproject(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(mod.shutil, "which", lambda name: "/usr/bin/python")
        assert environment_ready(tmp_path) is False

    def test_not_ready_without_python(self, tmp_path, monkeypatch) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]", encoding="utf-8")
        monkeypatch.setattr(mod.shutil, "which", lambda name: None)
        assert environment_ready(tmp_path) is False


# ---------------------------------------------------------------------------
# run_pytest
# ---------------------------------------------------------------------------


class TestRunPytest:
    def test_pass_on_zero_exit(self, monkeypatch) -> None:
        def fake_run(cmd, timeout, capture_output, text, check):  # noqa: ANN001
            return subprocess.CompletedProcess(cmd, 0, stdout="5 passed in 1s\n", stderr="")

        monkeypatch.setattr(mod.subprocess, "run", fake_run)
        status, summary = run_pytest(["pytest"], 10)
        assert status == "PASS"
        assert summary == "5 passed in 1s"

    def test_fail_on_nonzero_exit(self, monkeypatch) -> None:
        def fake_run(cmd, timeout, capture_output, text, check):  # noqa: ANN001
            return subprocess.CompletedProcess(cmd, 1, stdout="1 failed in 1s\n", stderr="")

        monkeypatch.setattr(mod.subprocess, "run", fake_run)
        status, summary = run_pytest(["pytest"], 10)
        assert status == "FAIL"
        assert summary == "1 failed in 1s"

    def test_timeout_is_error(self, monkeypatch) -> None:
        def fake_run(cmd, timeout, capture_output, text, check):  # noqa: ANN001
            raise subprocess.TimeoutExpired(cmd, timeout)

        monkeypatch.setattr(mod.subprocess, "run", fake_run)
        status, summary = run_pytest(["pytest"], 5)
        assert status == "ERROR"
        assert "timed out" in summary

    def test_os_error_is_error_with_collapsed_newlines(self, monkeypatch) -> None:
        def fake_run(cmd, timeout, capture_output, text, check):  # noqa: ANN001
            raise OSError("line1\nline2")

        monkeypatch.setattr(mod.subprocess, "run", fake_run)
        status, summary = run_pytest(["pytest"], 5)
        assert status == "ERROR"
        assert "\n" not in summary


# ---------------------------------------------------------------------------
# write_outputs / main
# ---------------------------------------------------------------------------


class TestWriteOutputs:
    def test_writes_status_and_summary(self, tmp_path: Path) -> None:
        output = tmp_path / "out"
        output.touch()
        write_outputs(output, "PASS", "5 passed")
        text = output.read_text(encoding="utf-8")
        assert "pytest_status=PASS" in text
        assert "pytest_summary=5 passed" in text


class TestMain:
    def test_skipped_when_env_not_ready(self, tmp_path, monkeypatch) -> None:
        output = tmp_path / "gh_output"
        output.touch()
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.setattr(mod, "environment_ready", lambda root: False)
        rc = main(["--project-root", str(tmp_path)])
        assert rc == 0
        text = output.read_text(encoding="utf-8")
        assert "pytest_status=SKIPPED" in text
        assert "pytest_summary=Python test environment not available" in text

    def test_runs_when_env_ready(self, tmp_path, monkeypatch) -> None:
        output = tmp_path / "gh_output"
        output.touch()
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.setattr(mod, "environment_ready", lambda root: True)
        monkeypatch.setattr(mod, "run_pytest", lambda cmd, timeout: ("PASS", "9 passed"))
        rc = main(["--project-root", str(tmp_path)])
        assert rc == 0
        text = output.read_text(encoding="utf-8")
        assert "pytest_status=PASS" in text
        assert "pytest_summary=9 passed" in text

    def test_missing_github_output_returns_two(self, tmp_path, monkeypatch) -> None:
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        monkeypatch.setattr(mod, "environment_ready", lambda root: False)
        rc = main(["--project-root", str(tmp_path)])
        assert rc == 2

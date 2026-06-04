"""Tests for scripts/quality_gate/check_infrastructure_failures.py.

Pins the detection logic and the best-effort label-add behavior of the
extracted ``Check for infrastructure failures and add label`` workflow step.
The gh CLI is mocked at the subprocess boundary; no real calls are made.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.quality_gate import check_infrastructure_failures as mod
from scripts.quality_gate.check_infrastructure_failures import (
    detect_failures,
    main,
)


def _write_infra(results_dir: Path, agent: str, flag: str, retries: str | None = None) -> None:
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / f"{agent}-infrastructure-failure.txt").write_text(flag, encoding="utf-8")
    if retries is not None:
        (results_dir / f"{agent}-retry-count.txt").write_text(retries, encoding="utf-8")


# ---------------------------------------------------------------------------
# detect_failures
# ---------------------------------------------------------------------------


class TestDetectFailures:
    def test_no_files_no_failures(self, tmp_path: Path) -> None:
        assert detect_failures(tmp_path) == []

    def test_false_flag_not_detected(self, tmp_path: Path) -> None:
        _write_infra(tmp_path, "security", "false")
        assert detect_failures(tmp_path) == []

    def test_true_flag_detected_with_retry_count(self, tmp_path: Path) -> None:
        _write_infra(tmp_path, "security", "true", retries="3")
        findings = detect_failures(tmp_path)
        assert len(findings) == 1
        assert findings[0].agent == "security"
        assert findings[0].retry_count == 3

    def test_true_flag_missing_retry_file_defaults_zero(self, tmp_path: Path) -> None:
        _write_infra(tmp_path, "qa", "true")
        findings = detect_failures(tmp_path)
        assert findings[0].retry_count == 0

    def test_non_numeric_retry_defaults_zero(self, tmp_path: Path) -> None:
        _write_infra(tmp_path, "qa", "true", retries="oops")
        findings = detect_failures(tmp_path)
        assert findings[0].retry_count == 0

    def test_whitespace_flag_trims_to_false(self, tmp_path: Path) -> None:
        _write_infra(tmp_path, "analyst", "  true  ", retries="1")
        findings = detect_failures(tmp_path)
        assert findings[0].agent == "analyst"

    def test_multiple_failures_in_agent_order(self, tmp_path: Path) -> None:
        _write_infra(tmp_path, "devops", "true", retries="2")
        _write_infra(tmp_path, "security", "true", retries="1")
        agents = [f.agent for f in detect_failures(tmp_path)]
        # Canonical order: security precedes devops.
        assert agents == ["security", "devops"]


# ---------------------------------------------------------------------------
# main: no failures path
# ---------------------------------------------------------------------------


class TestMainNoFailures:
    def test_no_failures_returns_zero_without_gh(self, tmp_path, monkeypatch, capsys) -> None:
        called = {"run": False}

        def fake_run(*a, **k):  # noqa: ANN002, ANN003
            called["run"] = True
            return subprocess.CompletedProcess([], 0)

        monkeypatch.setattr(mod.subprocess, "run", fake_run)
        rc = main(["--results-dir", str(tmp_path)])
        assert rc == 0
        assert called["run"] is False
        assert "No infrastructure failures detected" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# main: failure path (gh mocked)
# ---------------------------------------------------------------------------


class TestMainWithFailures:
    def _seed_failure(self, tmp_path: Path) -> Path:
        results = tmp_path / "ai-review-results"
        _write_infra(results, "security", "true", retries="2")
        return results

    def test_adds_label_when_authenticated(self, tmp_path, monkeypatch, capsys) -> None:
        results = self._seed_failure(tmp_path)
        monkeypatch.setenv("PR_NUMBER", "123")
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
        calls: list[list[str]] = []

        def fake_run(cmd, timeout, check=False, capture_output=False):  # noqa: ANN001
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(mod.subprocess, "run", fake_run)
        rc = main(["--results-dir", str(results)])
        assert rc == 0
        # First call: gh auth status; second: gh pr edit --add-label.
        assert calls[0][:3] == ["gh", "auth", "status"]
        assert "--add-label" in calls[1]
        assert "infrastructure-failure" in calls[1]
        assert "Successfully added infrastructure-failure label" in capsys.readouterr().out

    def test_auth_failure_skips_label_returns_zero(self, tmp_path, monkeypatch, capsys) -> None:
        results = self._seed_failure(tmp_path)
        monkeypatch.setenv("PR_NUMBER", "123")
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")

        def fake_run(cmd, timeout, check=False, capture_output=False):  # noqa: ANN001
            # gh auth status fails.
            return subprocess.CompletedProcess(cmd, 1)

        monkeypatch.setattr(mod.subprocess, "run", fake_run)
        rc = main(["--results-dir", str(results)])
        assert rc == 0
        assert "gh CLI authentication failed" in capsys.readouterr().out

    def test_label_add_failure_returns_zero(self, tmp_path, monkeypatch, capsys) -> None:
        results = self._seed_failure(tmp_path)
        monkeypatch.setenv("PR_NUMBER", "123")
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")

        def fake_run(cmd, timeout, check=False, capture_output=False):  # noqa: ANN001
            if cmd[:3] == ["gh", "auth", "status"]:
                return subprocess.CompletedProcess(cmd, 0)
            return subprocess.CompletedProcess(cmd, 1)  # label add fails

        monkeypatch.setattr(mod.subprocess, "run", fake_run)
        rc = main(["--results-dir", str(results)])
        assert rc == 0
        assert "Failed to add infrastructure-failure label" in capsys.readouterr().out

    def test_auth_timeout_returns_zero(self, tmp_path, monkeypatch, capsys) -> None:
        results = self._seed_failure(tmp_path)
        monkeypatch.setenv("PR_NUMBER", "123")
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")

        def fake_run(cmd, timeout, check=False, capture_output=False):  # noqa: ANN001
            raise subprocess.TimeoutExpired(cmd, timeout)

        monkeypatch.setattr(mod.subprocess, "run", fake_run)
        rc = main(["--results-dir", str(results)])
        assert rc == 0
        assert "gh auth status timed out" in capsys.readouterr().out

    def test_emits_notice_per_failed_agent(self, tmp_path, monkeypatch, capsys) -> None:
        results = self._seed_failure(tmp_path)
        monkeypatch.setenv("PR_NUMBER", "123")
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
        monkeypatch.setattr(
            mod.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess([], 0)
        )
        main(["--results-dir", str(results)])
        out = capsys.readouterr().out
        assert "::notice::Infrastructure failure detected for security agent (retries: 2)" in out

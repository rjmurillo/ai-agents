"""Tests for scripts/quality_gate/check_failed_agents.py.

Pins the failure-detection behavior of the extracted ``Check for failed
agents`` workflow step.
"""

from __future__ import annotations

from pathlib import Path

from scripts.quality_gate.check_failed_agents import (
    collect_results,
    find_failures,
    main,
    write_has_failures,
)

_ALL_ENV_KEYS = [
    "SECURITY_RESULT",
    "QA_RESULT",
    "ANALYST_RESULT",
    "ARCHITECT_RESULT",
    "DEVOPS_RESULT",
    "ROADMAP_RESULT",
    "RELIABILITY_RESULT",
    "OBSERVABILITY_RESULT",
    "AGENT_SAFETY_RESULT",
    "DECISION_RIGOR_RESULT",
]


def _all_env(value: str) -> dict[str, str]:
    return {key: value for key in _ALL_ENV_KEYS}


# ---------------------------------------------------------------------------
# collect_results
# ---------------------------------------------------------------------------


class TestCollectResults:
    def test_returns_ten_agents_in_canonical_order(self) -> None:
        results = collect_results(_all_env("success"))
        names = [name for name, _ in results]
        assert names == [
            "Security",
            "QA",
            "Analyst",
            "Architect",
            "DevOps",
            "Roadmap",
            "Reliability",
            "Observability",
            "Agent Safety",
            "Decision Rigor",
        ]

    def test_missing_env_yields_empty_string(self) -> None:
        results = collect_results({})
        assert all(result == "" for _, result in results)
        assert len(results) == 10


# ---------------------------------------------------------------------------
# find_failures
# ---------------------------------------------------------------------------


class TestFindFailures:
    def test_no_failures_when_all_success(self) -> None:
        results = collect_results(_all_env("success"))
        assert find_failures(results) == []

    def test_detects_failure_result(self) -> None:
        env = _all_env("success")
        env["SECURITY_RESULT"] = "failure"
        results = collect_results(env)
        assert find_failures(results) == ["Security"]

    def test_detects_cancelled_result(self) -> None:
        env = _all_env("success")
        env["QA_RESULT"] = "cancelled"
        results = collect_results(env)
        assert find_failures(results) == ["QA"]

    def test_skipped_is_not_a_failure(self) -> None:
        env = _all_env("skipped")
        results = collect_results(env)
        assert find_failures(results) == []

    def test_multiple_failures_preserve_order(self) -> None:
        env = _all_env("success")
        env["DEVOPS_RESULT"] = "failure"
        env["SECURITY_RESULT"] = "cancelled"
        results = collect_results(env)
        assert find_failures(results) == ["Security", "DevOps"]


# ---------------------------------------------------------------------------
# write_has_failures
# ---------------------------------------------------------------------------


class TestWriteHasFailures:
    def test_writes_true(self, tmp_path: Path) -> None:
        output = tmp_path / "out"
        output.touch()
        write_has_failures(output, True)
        assert output.read_text(encoding="utf-8") == "has_failures=true\n"

    def test_writes_false(self, tmp_path: Path) -> None:
        output = tmp_path / "out"
        output.touch()
        write_has_failures(output, False)
        assert output.read_text(encoding="utf-8") == "has_failures=false\n"


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


class TestMain:
    def test_all_success_writes_false(self, tmp_path, monkeypatch) -> None:
        output = tmp_path / "gh_output"
        output.touch()
        for key in _ALL_ENV_KEYS:
            monkeypatch.setenv(key, "success")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        rc = main([])
        assert rc == 0
        assert "has_failures=false" in output.read_text(encoding="utf-8")

    def test_failure_writes_true_and_annotates(self, tmp_path, monkeypatch, capsys) -> None:
        output = tmp_path / "gh_output"
        output.touch()
        for key in _ALL_ENV_KEYS:
            monkeypatch.setenv(key, "success")
        monkeypatch.setenv("ANALYST_RESULT", "failure")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        rc = main([])
        assert rc == 0
        assert "has_failures=true" in output.read_text(encoding="utf-8")
        captured = capsys.readouterr()
        assert "::error::Analyst agent failed with result: failure" in captured.out
        assert "::warning::Failed agents: Analyst" in captured.out

    def test_failure_does_not_fail_step(self, tmp_path, monkeypatch) -> None:
        # The original block exits 0 even when agents failed.
        output = tmp_path / "gh_output"
        output.touch()
        for key in _ALL_ENV_KEYS:
            monkeypatch.setenv(key, "failure")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        rc = main([])
        assert rc == 0

    def test_missing_github_output_returns_two(self, monkeypatch) -> None:
        for key in _ALL_ENV_KEYS:
            monkeypatch.setenv(key, "success")
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        rc = main([])
        assert rc == 2

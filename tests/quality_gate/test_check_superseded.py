"""Tests for scripts/quality_gate/check_superseded.py.

Pins the supersession-detection behavior that keeps a concurrency-cancelled
``AI PR Quality Gate`` run from leaving a stale blocking status on the PR head
(Issue #2347).

Decision rule under test: a run is SUPERSEDED when at least one review job is
``cancelled`` AND no review job is ``failure``. A genuine ``failure`` always
keeps the gate blocking so a real problem is never masked by a coincident
cancellation.
"""

from __future__ import annotations

from pathlib import Path

from scripts.quality_gate.check_superseded import (
    collect_results,
    is_superseded,
    main,
    write_superseded,
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
    def test_returns_ten_results_in_canonical_order(self) -> None:
        env = _all_env("success")
        env["SECURITY_RESULT"] = "cancelled"
        env["DECISION_RIGOR_RESULT"] = "failure"
        results = collect_results(env)
        assert len(results) == 10
        assert results[0] == "cancelled"
        assert results[-1] == "failure"

    def test_missing_env_yields_empty_string(self) -> None:
        results = collect_results({})
        assert results == [""] * 10


# ---------------------------------------------------------------------------
# is_superseded
# ---------------------------------------------------------------------------


class TestIsSuperseded:
    def test_cancelled_with_success_is_superseded(self) -> None:
        # Run interrupted mid-flight: some reviews finished, no genuine failure.
        results = ["cancelled"] + ["success"] * 9
        assert is_superseded(results) is True

    def test_all_cancelled_is_superseded(self) -> None:
        assert is_superseded(["cancelled"] * 10) is True

    def test_cancelled_with_skipped_is_superseded(self) -> None:
        results = ["cancelled"] + ["skipped"] * 9
        assert is_superseded(results) is True

    def test_cancelled_with_failure_is_not_superseded(self) -> None:
        # A genuine failure must still block, even alongside a cancellation.
        results = ["cancelled", "failure"] + ["success"] * 8
        assert is_superseded(results) is False

    def test_all_success_is_not_superseded(self) -> None:
        assert is_superseded(["success"] * 10) is False

    def test_all_skipped_is_not_superseded(self) -> None:
        assert is_superseded(["skipped"] * 10) is False

    def test_only_failure_is_not_superseded(self) -> None:
        results = ["failure"] + ["success"] * 9
        assert is_superseded(results) is False

    def test_all_empty_is_not_superseded(self) -> None:
        # Empty strings (no result reported) are neither cancelled nor failure.
        assert is_superseded([""] * 10) is False


# ---------------------------------------------------------------------------
# write_superseded
# ---------------------------------------------------------------------------


class TestWriteSuperseded:
    def test_writes_true(self, tmp_path: Path) -> None:
        output = tmp_path / "out"
        output.touch()
        write_superseded(output, True)
        assert output.read_text(encoding="utf-8") == "superseded=true\n"

    def test_writes_false(self, tmp_path: Path) -> None:
        output = tmp_path / "out"
        output.touch()
        write_superseded(output, False)
        assert output.read_text(encoding="utf-8") == "superseded=false\n"


# ---------------------------------------------------------------------------
# main (CLI / exit codes)
# ---------------------------------------------------------------------------


class TestMain:
    def test_superseded_run_writes_true_and_notices(
        self, tmp_path, monkeypatch, capsys
    ) -> None:
        output = tmp_path / "gh_output"
        output.touch()
        for key in _ALL_ENV_KEYS:
            monkeypatch.setenv(key, "success")
        monkeypatch.setenv("QA_RESULT", "cancelled")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        rc = main([])
        assert rc == 0
        assert "superseded=true" in output.read_text(encoding="utf-8")
        captured = capsys.readouterr()
        assert "::notice::Run superseded" in captured.out

    def test_genuine_failure_writes_false(self, tmp_path, monkeypatch) -> None:
        output = tmp_path / "gh_output"
        output.touch()
        for key in _ALL_ENV_KEYS:
            monkeypatch.setenv(key, "success")
        monkeypatch.setenv("ANALYST_RESULT", "cancelled")
        monkeypatch.setenv("DEVOPS_RESULT", "failure")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        rc = main([])
        assert rc == 0
        assert "superseded=false" in output.read_text(encoding="utf-8")

    def test_normal_run_writes_false(self, tmp_path, monkeypatch) -> None:
        output = tmp_path / "gh_output"
        output.touch()
        for key in _ALL_ENV_KEYS:
            monkeypatch.setenv(key, "success")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        rc = main([])
        assert rc == 0
        assert "superseded=false" in output.read_text(encoding="utf-8")

    def test_superseded_run_does_not_fail_step(self, tmp_path, monkeypatch) -> None:
        output = tmp_path / "gh_output"
        output.touch()
        for key in _ALL_ENV_KEYS:
            monkeypatch.setenv(key, "cancelled")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        rc = main([])
        assert rc == 0

    def test_missing_github_output_returns_two(self, monkeypatch) -> None:
        for key in _ALL_ENV_KEYS:
            monkeypatch.setenv(key, "cancelled")
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        rc = main([])
        assert rc == 2

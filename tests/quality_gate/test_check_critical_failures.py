"""Tests for scripts/quality_gate/check_critical_failures.py.

Pins the gate-decision logic of the extracted ``Check for Critical Failures``
workflow step: missing verdicts block, blocking final verdicts block, UNKNOWN
blocks (stricter than canonical FAIL_VERDICTS), clean verdicts pass.
"""

from __future__ import annotations

import pytest

from scripts.quality_gate.check_critical_failures import (
    BLOCKING_VERDICTS,
    collect_verdicts,
    find_blocking,
    find_missing,
    main,
)

_VERDICT_KEYS = [
    "SECURITY_VERDICT",
    "QA_VERDICT",
    "ANALYST_VERDICT",
    "ARCHITECT_VERDICT",
    "DEVOPS_VERDICT",
    "ROADMAP_VERDICT",
    "RELIABILITY_VERDICT",
    "OBSERVABILITY_VERDICT",
    "AGENT_SAFETY_VERDICT",
    "DECISION_RIGOR_VERDICT",
]


def _all_pass_env(final: str = "PASS") -> dict[str, str]:
    env = {key: "PASS" for key in _VERDICT_KEYS}
    env["FINAL_VERDICT"] = final
    return env


# ---------------------------------------------------------------------------
# BLOCKING_VERDICTS
# ---------------------------------------------------------------------------


class TestBlockingVerdicts:
    def test_matches_original_workflow_set(self) -> None:
        assert BLOCKING_VERDICTS == {
            "CRITICAL_FAIL",
            "REJECTED",
            "FAIL",
            "NEEDS_REVIEW",
            "NON_COMPLIANT",
            "UNKNOWN",
        }

    def test_pass_and_warn_not_blocking(self) -> None:
        assert "PASS" not in BLOCKING_VERDICTS
        assert "WARN" not in BLOCKING_VERDICTS


# ---------------------------------------------------------------------------
# collect_verdicts
# ---------------------------------------------------------------------------


class TestCollectVerdicts:
    def test_ten_agents_in_canonical_order(self) -> None:
        verdicts = collect_verdicts(_all_pass_env())
        assert len(verdicts) == 10
        assert verdicts[0][0].endswith("Security")
        assert verdicts[-1][0].endswith("Decision Rigor")

    def test_missing_env_yields_empty(self) -> None:
        verdicts = collect_verdicts({})
        assert all(v == "" for _, v in verdicts)


# ---------------------------------------------------------------------------
# find_missing / find_blocking
# ---------------------------------------------------------------------------


class TestFindMissing:
    def test_no_missing_when_all_present(self) -> None:
        assert find_missing(collect_verdicts(_all_pass_env())) == []

    def test_whitespace_is_missing(self) -> None:
        env = _all_pass_env()
        env["QA_VERDICT"] = "   "
        missing = find_missing(collect_verdicts(env))
        assert any("QA" in name for name in missing)

    def test_empty_is_missing(self) -> None:
        env = _all_pass_env()
        env["SECURITY_VERDICT"] = ""
        missing = find_missing(collect_verdicts(env))
        assert any("Security" in name for name in missing)


class TestFindBlocking:
    @pytest.mark.parametrize(
        "verdict", ["CRITICAL_FAIL", "REJECTED", "FAIL", "NEEDS_REVIEW", "NON_COMPLIANT", "UNKNOWN"]
    )
    def test_each_blocking_verdict_detected(self, verdict: str) -> None:
        env = _all_pass_env()
        env["ANALYST_VERDICT"] = verdict
        blocking = find_blocking(collect_verdicts(env))
        assert any(verdict in entry for entry in blocking)

    def test_pass_not_blocking(self) -> None:
        assert find_blocking(collect_verdicts(_all_pass_env())) == []


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


class TestMain:
    def test_all_pass_returns_zero(self, monkeypatch) -> None:
        for key, value in _all_pass_env("PASS").items():
            monkeypatch.setenv(key, value)
        rc = main([])
        assert rc == 0

    def test_warn_final_passes(self, monkeypatch) -> None:
        env = _all_pass_env("WARN")
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        rc = main([])
        assert rc == 0

    def test_blocking_final_verdict_returns_one(self, monkeypatch, capsys) -> None:
        env = _all_pass_env("CRITICAL_FAIL")
        env["SECURITY_VERDICT"] = "CRITICAL_FAIL"
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        rc = main([])
        assert rc == 1
        captured = capsys.readouterr()
        assert "AI Quality Gate FAILED" in captured.out

    def test_unknown_final_blocks(self, monkeypatch) -> None:
        # Stricter than canonical FAIL_VERDICTS: UNKNOWN must block (#1934).
        env = _all_pass_env("UNKNOWN")
        env["ANALYST_VERDICT"] = "UNKNOWN"
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        rc = main([])
        assert rc == 1

    def test_missing_verdict_returns_one(self, monkeypatch, capsys) -> None:
        env = _all_pass_env("PASS")
        env["QA_VERDICT"] = ""
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        # Ensure the empty value is actually set (monkeypatch.setenv with "" is fine).
        monkeypatch.setenv("QA_VERDICT", "")
        rc = main([])
        assert rc == 1
        captured = capsys.readouterr()
        assert "missing verdicts" in captured.out
        assert "No verdict received" in captured.out

    def test_missing_takes_precedence_over_pass_final(self, monkeypatch) -> None:
        # Even with a PASS final verdict, a missing per-agent verdict fails.
        env = _all_pass_env("PASS")
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        monkeypatch.setenv("DEVOPS_VERDICT", "")
        rc = main([])
        assert rc == 1

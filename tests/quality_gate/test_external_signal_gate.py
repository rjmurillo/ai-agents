"""Tests for scripts/quality_gate/external_signal_gate.py (Issue #2108).

Pins the signal-building adapter that feeds the gate aggregator: pytest status
mapping, agent verdict aliasing, and the closed-loop guarantee (#1855) that
PASS is refused without an external signal.
"""

from __future__ import annotations

import pytest

from scripts.quality_gate.external_signal_gate import (
    agent_signal,
    build_signals,
    main,
    pytest_signal,
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


# ---------------------------------------------------------------------------
# pytest_signal
# ---------------------------------------------------------------------------


class TestPytestSignal:
    @pytest.mark.parametrize(
        "status,expected",
        [
            ("PASS", "external:pytest=PASS"),
            ("FAIL", "external:pytest=FAIL"),
            ("ERROR", "external:pytest=UNKNOWN"),
            ("SKIPPED", "external:pytest=UNKNOWN"),
        ],
    )
    def test_maps_each_status(self, status: str, expected: str) -> None:
        assert pytest_signal(status) == expected

    def test_unknown_status_is_unknown(self) -> None:
        assert pytest_signal("bogus") == "external:pytest=UNKNOWN"

    def test_case_insensitive(self) -> None:
        assert pytest_signal("pass") == "external:pytest=PASS"


# ---------------------------------------------------------------------------
# agent_signal
# ---------------------------------------------------------------------------


class TestAgentSignal:
    def test_pass_through_known_verdict(self) -> None:
        assert agent_signal("security", "PASS") == "llm:security=PASS"

    def test_non_compliant_aliases_to_fail(self) -> None:
        assert agent_signal("qa", "NON_COMPLIANT") == "llm:qa=FAIL"

    def test_empty_verdict_is_unknown(self) -> None:
        assert agent_signal("analyst", "") == "llm:analyst=UNKNOWN"

    def test_critical_fail_passes_through(self) -> None:
        assert agent_signal("security", "CRITICAL_FAIL") == "llm:security=CRITICAL_FAIL"


# ---------------------------------------------------------------------------
# build_signals
# ---------------------------------------------------------------------------


class TestBuildSignals:
    def test_first_signal_is_external_pytest(self) -> None:
        signals = build_signals({"PYTEST_STATUS": "PASS"})
        assert signals[0] == "external:pytest=PASS"

    def test_includes_ten_agent_signals(self) -> None:
        env = {"PYTEST_STATUS": "PASS"}
        for key in _VERDICT_KEYS:
            env[key] = "PASS"
        signals = build_signals(env)
        # 1 pytest + 10 agents.
        assert len(signals) == 11
        assert any(s.startswith("llm:security=") for s in signals)
        assert any(s.startswith("llm:decision-rigor=") for s in signals)


# ---------------------------------------------------------------------------
# main: end-to-end through gate_aggregator
# ---------------------------------------------------------------------------


def _set_all(monkeypatch, verdict: str, pytest_status: str) -> None:
    monkeypatch.setenv("PYTEST_STATUS", pytest_status)
    for key in _VERDICT_KEYS:
        monkeypatch.setenv(key, verdict)


class TestMain:
    def test_pass_with_external_pytest_pass(self, monkeypatch, capsys) -> None:
        _set_all(monkeypatch, "PASS", "PASS")
        rc = main([])
        assert rc == 0
        assert "PASS" in capsys.readouterr().out

    def test_blocking_agent_verdict_fails(self, monkeypatch, capsys) -> None:
        _set_all(monkeypatch, "PASS", "PASS")
        monkeypatch.setenv("SECURITY_VERDICT", "CRITICAL_FAIL")
        rc = main([])
        assert rc == 1
        assert "CRITICAL_FAIL" in capsys.readouterr().out

    def test_non_compliant_agent_blocks(self, monkeypatch) -> None:
        _set_all(monkeypatch, "PASS", "PASS")
        monkeypatch.setenv("QA_VERDICT", "NON_COMPLIANT")
        rc = main([])
        assert rc == 1

    def test_closed_loop_refused_when_pytest_skipped(self, monkeypatch, capsys) -> None:
        # SKIPPED -> external:pytest=UNKNOWN, so no usable external signal; the
        # aggregator must refuse PASS (closed-loop, #1855).
        _set_all(monkeypatch, "PASS", "SKIPPED")
        rc = main([])
        assert rc == 1
        out = capsys.readouterr().out
        assert "NEEDS_REVIEW" in out

    def test_warn_agent_downgrades_to_warn(self, monkeypatch, capsys) -> None:
        _set_all(monkeypatch, "PASS", "PASS")
        monkeypatch.setenv("ANALYST_VERDICT", "WARN")
        rc = main([])
        # WARN still exits 0 (gate_aggregator treats PASS/WARN as success).
        assert rc == 0
        assert "WARN" in capsys.readouterr().out

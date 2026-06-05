"""Tests for scripts/quality_gate/spec_external_signal_gate.py (Issue #2108).

Pins the signal-building adapter that feeds the gate aggregator for the
spec-validation workflow: deterministic acceptance-criteria mapping, agent
verdict aliasing, and the closed-loop guarantee (#1855) that PASS is refused
without a usable external signal.
"""

from __future__ import annotations

from scripts.quality_gate.spec_external_signal_gate import (
    acceptance_signal,
    acceptance_verdict,
    agent_signal,
    build_signals,
    main,
)

_BODY_ALL_CHECKED = """
## Acceptance Criteria

- [x] wire the aggregator into the spec workflow
- [x] add tests for the adapter
"""

_BODY_UNCHECKED = """
## Acceptance Criteria

- [x] wire the aggregator into the spec workflow
- [ ] add tests for the adapter
"""

_BODY_NO_CRITERIA = """
## Summary

This PR has no acceptance section.
"""


# ---------------------------------------------------------------------------
# acceptance_verdict
# ---------------------------------------------------------------------------


class TestAcceptanceVerdict:
    def test_all_checked_is_pass(self) -> None:
        assert acceptance_verdict(_BODY_ALL_CHECKED) == "PASS"

    def test_unchecked_is_fail(self) -> None:
        assert acceptance_verdict(_BODY_UNCHECKED) == "FAIL"

    def test_no_criteria_is_unknown(self) -> None:
        assert acceptance_verdict(_BODY_NO_CRITERIA) == "UNKNOWN"

    def test_empty_body_is_unknown(self) -> None:
        assert acceptance_verdict("") == "UNKNOWN"


class TestAcceptanceSignal:
    def test_prefixes_external_acceptance_criteria(self) -> None:
        assert (
            acceptance_signal(_BODY_ALL_CHECKED)
            == "external:acceptance-criteria=PASS"
        )

    def test_unchecked_signal_is_fail(self) -> None:
        assert (
            acceptance_signal(_BODY_UNCHECKED) == "external:acceptance-criteria=FAIL"
        )

    def test_no_criteria_signal_is_unknown(self) -> None:
        assert (
            acceptance_signal(_BODY_NO_CRITERIA)
            == "external:acceptance-criteria=UNKNOWN"
        )


# ---------------------------------------------------------------------------
# agent_signal
# ---------------------------------------------------------------------------


class TestAgentSignal:
    def test_pass_through_known_verdict(self) -> None:
        assert agent_signal("trace", "PASS") == "llm:trace=PASS"

    def test_compliant_aliases_to_pass(self) -> None:
        assert agent_signal("trace", "COMPLIANT") == "llm:trace=PASS"

    def test_non_compliant_aliases_to_fail(self) -> None:
        assert agent_signal("completeness", "NON_COMPLIANT") == "llm:completeness=FAIL"

    def test_needs_review_aliases_to_fail(self) -> None:
        assert agent_signal("trace", "NEEDS_REVIEW") == "llm:trace=FAIL"

    def test_partial_aliases_to_warn(self) -> None:
        assert agent_signal("completeness", "PARTIAL") == "llm:completeness=WARN"

    def test_empty_verdict_is_unknown(self) -> None:
        assert agent_signal("trace", "") == "llm:trace=UNKNOWN"

    def test_critical_fail_passes_through(self) -> None:
        assert agent_signal("trace", "CRITICAL_FAIL") == "llm:trace=CRITICAL_FAIL"

    def test_case_insensitive(self) -> None:
        assert agent_signal("trace", "compliant") == "llm:trace=PASS"


# ---------------------------------------------------------------------------
# build_signals
# ---------------------------------------------------------------------------


class TestBuildSignals:
    def test_first_signal_is_external_acceptance(self, tmp_path) -> None:
        body_file = tmp_path / "body.md"
        body_file.write_text(_BODY_ALL_CHECKED, encoding="utf-8")
        env = {
            "PR_BODY_FILE": str(body_file),
            "TRACE_VERDICT": "PASS",
            "COMPLETENESS_VERDICT": "PASS",
        }
        signals = build_signals(env)
        assert signals[0] == "external:acceptance-criteria=PASS"

    def test_includes_two_agent_signals(self, tmp_path) -> None:
        body_file = tmp_path / "body.md"
        body_file.write_text(_BODY_ALL_CHECKED, encoding="utf-8")
        env = {
            "PR_BODY_FILE": str(body_file),
            "TRACE_VERDICT": "COMPLIANT",
            "COMPLETENESS_VERDICT": "COMPLIANT",
        }
        signals = build_signals(env)
        # 1 acceptance + 2 agents.
        assert len(signals) == 3
        assert any(s.startswith("llm:trace=") for s in signals)
        assert any(s.startswith("llm:completeness=") for s in signals)

    def test_missing_body_file_is_unknown(self) -> None:
        env = {
            "PR_BODY_FILE": "/nonexistent/path/body.md",
            "TRACE_VERDICT": "PASS",
            "COMPLETENESS_VERDICT": "PASS",
        }
        signals = build_signals(env)
        assert signals[0] == "external:acceptance-criteria=UNKNOWN"

    def test_unset_body_file_is_unknown(self) -> None:
        signals = build_signals({"TRACE_VERDICT": "PASS"})
        assert signals[0] == "external:acceptance-criteria=UNKNOWN"

    def test_non_utf8_body_file_is_unknown(self, tmp_path) -> None:
        # A body file that is not valid UTF-8 must degrade to UNKNOWN, not crash
        # the observe step with UnicodeDecodeError.
        body_file = tmp_path / "body.md"
        body_file.write_bytes(b"\xff\xfe acceptance criteria \x80\x81")
        env = {
            "PR_BODY_FILE": str(body_file),
            "TRACE_VERDICT": "PASS",
            "COMPLETENESS_VERDICT": "PASS",
        }
        signals = build_signals(env)
        assert signals[0] == "external:acceptance-criteria=UNKNOWN"


# ---------------------------------------------------------------------------
# main: end-to-end through gate_aggregator
# ---------------------------------------------------------------------------


def _write_body(tmp_path, body: str) -> str:
    body_file = tmp_path / "body.md"
    body_file.write_text(body, encoding="utf-8")
    return str(body_file)


class TestMain:
    def test_pass_with_external_acceptance_pass(
        self, monkeypatch, capsys, tmp_path
    ) -> None:
        monkeypatch.setenv("PR_BODY_FILE", _write_body(tmp_path, _BODY_ALL_CHECKED))
        monkeypatch.setenv("TRACE_VERDICT", "COMPLIANT")
        monkeypatch.setenv("COMPLETENESS_VERDICT", "COMPLIANT")
        rc = main([])
        assert rc == 0
        assert "PASS" in capsys.readouterr().out

    def test_acceptance_fail_blocks(self, monkeypatch, capsys, tmp_path) -> None:
        monkeypatch.setenv("PR_BODY_FILE", _write_body(tmp_path, _BODY_UNCHECKED))
        monkeypatch.setenv("TRACE_VERDICT", "COMPLIANT")
        monkeypatch.setenv("COMPLETENESS_VERDICT", "COMPLIANT")
        rc = main([])
        assert rc == 1
        assert "FAIL" in capsys.readouterr().out

    def test_non_compliant_agent_blocks(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setenv("PR_BODY_FILE", _write_body(tmp_path, _BODY_ALL_CHECKED))
        monkeypatch.setenv("TRACE_VERDICT", "NON_COMPLIANT")
        monkeypatch.setenv("COMPLETENESS_VERDICT", "COMPLIANT")
        rc = main([])
        assert rc == 1

    def test_needs_review_agent_blocks(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setenv("PR_BODY_FILE", _write_body(tmp_path, _BODY_ALL_CHECKED))
        monkeypatch.setenv("TRACE_VERDICT", "COMPLIANT")
        monkeypatch.setenv("COMPLETENESS_VERDICT", "NEEDS_REVIEW")
        rc = main([])
        assert rc == 1

    def test_partial_agent_warns(self, monkeypatch, capsys, tmp_path) -> None:
        monkeypatch.setenv("PR_BODY_FILE", _write_body(tmp_path, _BODY_ALL_CHECKED))
        monkeypatch.setenv("TRACE_VERDICT", "COMPLIANT")
        monkeypatch.setenv("COMPLETENESS_VERDICT", "PARTIAL")
        rc = main([])
        # WARN still exits 0 (gate_aggregator treats PASS/WARN as success).
        assert rc == 0
        assert "WARN" in capsys.readouterr().out

    def test_closed_loop_refused_when_no_criteria(
        self, monkeypatch, capsys, tmp_path
    ) -> None:
        # No acceptance criteria -> external:acceptance-criteria=UNKNOWN, so no
        # usable external signal; the aggregator must refuse PASS (#1855).
        monkeypatch.setenv("PR_BODY_FILE", _write_body(tmp_path, _BODY_NO_CRITERIA))
        monkeypatch.setenv("TRACE_VERDICT", "COMPLIANT")
        monkeypatch.setenv("COMPLETENESS_VERDICT", "COMPLIANT")
        rc = main([])
        assert rc == 1
        assert "NEEDS_REVIEW" in capsys.readouterr().out

    def test_closed_loop_refused_when_body_missing(
        self, monkeypatch, capsys
    ) -> None:
        monkeypatch.delenv("PR_BODY_FILE", raising=False)
        monkeypatch.setenv("TRACE_VERDICT", "COMPLIANT")
        monkeypatch.setenv("COMPLETENESS_VERDICT", "COMPLIANT")
        rc = main([])
        assert rc == 1
        assert "NEEDS_REVIEW" in capsys.readouterr().out

"""Tests for scripts/quality_gate/external_signal_gate.py (Issue #2108).

Pins the signal-building adapter that feeds the gate aggregator: pytest status
mapping, agent verdict aliasing, and the closed-loop guarantee (#1855) that
PASS is refused without an external signal.
"""

from __future__ import annotations

import pytest

from scripts.ai_review_common.verdict import _KNOWN_VERDICT_TOKENS
from scripts.external_signals.gate_aggregator import KNOWN_VERDICTS, parse_signal
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

    def test_needs_review_aliases_to_fail(self) -> None:
        assert agent_signal("qa", "NEEDS_REVIEW") == "llm:qa=FAIL"

    def test_compliant_aliases_to_pass(self) -> None:
        assert agent_signal("qa", "COMPLIANT") == "llm:qa=PASS"

    def test_partial_aliases_to_warn(self) -> None:
        assert agent_signal("qa", "PARTIAL") == "llm:qa=WARN"

    def test_empty_verdict_is_unknown(self) -> None:
        assert agent_signal("analyst", "") == "llm:analyst=UNKNOWN"

    def test_critical_fail_passes_through(self) -> None:
        assert agent_signal("security", "CRITICAL_FAIL") == "llm:security=CRITICAL_FAIL"

    def test_did_not_run_aliases_to_unknown(self) -> None:
        # Regression for the gate crash in run 30840235175: DID_NOT_RUN reached
        # parse_signal unaliased and raised, so the observe-mode gate exited 2
        # with no verdict. UNKNOWN matches how verdict.merge_verdicts and
        # check_critical_failures.BLOCKING_VERDICTS already treat the token.
        assert agent_signal("qa", "DID_NOT_RUN") == "llm:qa=UNKNOWN"

    def test_did_not_run_is_aliased_not_merely_caught_by_the_fallback(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # The assert above passes either way, because the fallback also yields
        # UNKNOWN. Deleting the alias entry left the whole suite green, which
        # made the entry untested. The two paths differ in one observable way:
        # a decided mapping is silent, a gap in the table warns. Assert the
        # silence, so removing the alias fails here.
        agent_signal("qa", "DID_NOT_RUN")
        assert capsys.readouterr().err == ""

    def test_unrecognized_token_falls_back_to_unknown(self) -> None:
        # Fail closed. A token nobody taught the adapter must still yield a
        # verdict the aggregator can parse, never an exit-2 crash.
        assert agent_signal("qa", "SOMETHING_NEW") == "llm:qa=UNKNOWN"

    def test_unrecognized_token_warns_so_drift_is_visible(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Failing closed silently would hide the next instance of exactly this
        # bug: a producer grows a verdict the adapter never learned, the gate
        # quietly blocks, and nobody learns why.
        agent_signal("qa", "SOMETHING_NEW")
        err = capsys.readouterr().err
        assert "SOMETHING_NEW" in err
        assert "_AGENT_VERDICT_ALIAS" in err

    def test_the_drift_warning_uses_the_annotation_channel(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Pinned separately from the test above, which passes on a bare stderr
        # line. This path degrades rather than failing, so nothing makes a
        # human open the log; the annotation is what puts the drift in the run
        # summary. Without this assertion, dropping the prefix is invisible.
        agent_signal("qa", "SOMETHING_NEW")
        assert capsys.readouterr().err.startswith("::warning::")

    def test_known_aggregator_tokens_do_not_warn(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Negative control for the warning: a token gate_aggregator already
        # accepts is not drift and must stay quiet, or the log fills with noise
        # on every run and the real warning gets skimmed past.
        agent_signal("qa", "PASS")
        agent_signal("security", "CRITICAL_FAIL")
        assert capsys.readouterr().err == ""

    def test_fallback_does_not_swallow_known_tokens(self) -> None:
        # Negative control for the fallback above: it must not flatten every
        # verdict to UNKNOWN. If it did, the two asserts here would fail.
        assert agent_signal("qa", "FAIL") == "llm:qa=FAIL"
        assert agent_signal("qa", "WARN") == "llm:qa=WARN"

    @pytest.mark.parametrize("token", sorted(_KNOWN_VERDICT_TOKENS))
    def test_every_repo_verdict_token_is_parseable(
        self, token: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The adapter is total over the repo verdict vocabulary.

        gate_aggregator accepts a deliberately narrow token set. This adapter
        is the only thing standing between the wider vocabulary in
        scripts/ai_review_common/verdict.py and a parse_signal ValueError that
        kills the gate. DID_NOT_RUN was added to three modules by #2818/#2821
        and missed here, which is what this guard exists to catch next time.

        The stderr assertion is the load-bearing half. Parseability alone
        cannot fail: the catch-all fallback coerces anything unrecognized to
        UNKNOWN, so a new repo token that nobody aliased would still parse and
        this test would still pass while the adapter silently dropped it. That
        is precisely the DID_NOT_RUN regression above, and the fallback made
        the original guard blind to a repeat. Requiring silence restores it,
        because an unaliased token that gate_aggregator does not accept takes
        the warning branch.
        """
        spec = agent_signal("qa", token)
        parsed = parse_signal(spec)
        assert parsed.verdict in KNOWN_VERDICTS
        assert capsys.readouterr().err == "", (
            f"repo verdict token {token!r} reached the drift fallback."
            " Add it to _AGENT_VERDICT_ALIAS in"
            " scripts/quality_gate/external_signal_gate.py."
        )


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

    def test_needs_review_agent_blocks(self, monkeypatch) -> None:
        _set_all(monkeypatch, "PASS", "PASS")
        monkeypatch.setenv("QA_VERDICT", "NEEDS_REVIEW")
        rc = main([])
        assert rc == 1

    def test_compliant_agent_passes(self, monkeypatch, capsys) -> None:
        _set_all(monkeypatch, "COMPLIANT", "PASS")
        rc = main([])
        assert rc == 0
        assert "PASS" in capsys.readouterr().out

    def test_partial_agent_warns(self, monkeypatch, capsys) -> None:
        _set_all(monkeypatch, "PARTIAL", "PASS")
        rc = main([])
        assert rc == 0
        assert "WARN" in capsys.readouterr().out

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

    def test_did_not_run_blocks_instead_of_crashing(self, monkeypatch, capsys) -> None:
        # End-to-end repro of run 30840235175, where QA reported DID_NOT_RUN
        # and this adapter exited 2 with no verdict. Exit 1 with NEEDS_REVIEW
        # is the correct outcome: the agent never ran, so the gate must refuse
        # to pass, but it still has to say so.
        _set_all(monkeypatch, "PASS", "PASS")
        monkeypatch.setenv("QA_VERDICT", "DID_NOT_RUN")
        rc = main([])
        assert rc == 1
        out = capsys.readouterr().out
        assert "NEEDS_REVIEW" in out
        assert "llm:qa=UNKNOWN" in out or '"qa"' in out

"""Tests for scripts.external_signals.gate_aggregator."""

from __future__ import annotations

import pytest

from scripts.external_signals import gate_aggregator as ga


def _parse(*specs: str):
    return [ga.parse_signal(s) for s in specs]


def test_parse_signal_round_trip():
    s = ga.parse_signal("external:pytest=PASS")
    assert s.kind == "external" and s.name == "pytest" and s.verdict == "PASS"


@pytest.mark.parametrize(
    "spec",
    ["no-equals", "external=PASS", "weird:thing=PASS", "external:=PASS", "external:x=BOGUS"],
)
def test_parse_signal_rejects_garbage(spec: str):
    with pytest.raises(ValueError):
        ga.parse_signal(spec)


def test_blocking_severity_wins_even_with_external_pass():
    sigs = _parse("external:pytest=PASS", "llm:security=CRITICAL_FAIL")
    verdict, reason = ga.aggregate(sigs)
    assert verdict == "CRITICAL_FAIL"
    assert "llm:security" in reason


def test_closed_loop_refused_when_only_llm_signals():
    sigs = _parse("llm:qa=PASS", "llm:critic=PASS")
    verdict, reason = ga.aggregate(sigs)
    assert verdict == "NEEDS_REVIEW"
    assert reason.startswith("closed-loop")


def test_pass_requires_known_external_pass():
    sigs = _parse("external:pytest=UNKNOWN", "llm:qa=PASS")
    verdict, _ = ga.aggregate(sigs)
    assert verdict == "NEEDS_REVIEW"


def test_warn_when_warning_present():
    sigs = _parse("external:pytest=PASS", "llm:qa=WARN")
    verdict, _ = ga.aggregate(sigs)
    assert verdict == "WARN"


def test_pass_when_external_passes_and_no_warnings():
    sigs = _parse("external:pytest=PASS", "external:codeql=PASS", "llm:qa=PASS")
    verdict, reason = ga.aggregate(sigs)
    assert verdict == "PASS"
    assert reason == "all-clear"


def test_empty_signals_is_needs_review():
    verdict, reason = ga.aggregate([])
    assert verdict == "NEEDS_REVIEW"
    assert reason == "no-signals"


def test_cli_closed_loop_exits_nonzero(capsys: pytest.CaptureFixture[str]):
    rc = ga.main(["--signal", "llm:qa=PASS", "--json"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "NEEDS_REVIEW" in out
    assert "closed-loop" in out


def test_cli_pass_when_external_present(capsys: pytest.CaptureFixture[str]):
    rc = ga.main([
        "--signal", "external:pytest=PASS",
        "--signal", "llm:qa=PASS",
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "VERDICT: PASS" in out


def test_cli_bad_signal_returns_two(capsys: pytest.CaptureFixture[str]):
    rc = ga.main(["--signal", "not-a-signal"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "signal must be" in err

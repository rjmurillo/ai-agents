"""Unit tests for Copilot CLI model-substitution detection.

A silently substituted model is a billing defect: the workflow asked for the
cheap tier, Copilot served the session default, and the exit code stayed 0.
"""

from __future__ import annotations

import pytest

from scripts.ci import _copilot_model_fallback as fallback


@pytest.mark.parametrize(
    ("stream", "expected"),
    [
        ('claude-sonnet-4.5 not available; using "claude-opus-5" instead', "claude-opus-5"),
        ("Model not available; using claude-opus-5 instead.", "claude-opus-5"),
        ("NOT AVAILABLE; USING 'gpt-5.4' INSTEAD", "gpt-5.4"),
        ("not available;   using   claude-haiku-4.5   instead", "claude-haiku-4.5"),
    ],
)
def test_detects_substitution(capsys, stream, expected):
    assert fallback.report_model_fallback("claude-haiku-4.5", stream) == expected
    captured = capsys.readouterr().out
    assert "::warning::" in captured
    assert "claude-haiku-4.5" in captured
    assert expected in captured


@pytest.mark.parametrize(
    "stream",
    [
        "VERDICT: PASS\nMESSAGE: looks fine",
        "warning: rate limit reached, retrying",
        "resource not accessible by integration",
        "the model is not available",
    ],
)
def test_ignores_unrelated_output(capsys, stream):
    assert fallback.report_model_fallback("claude-haiku-4.5", stream) is None
    assert "::warning::" not in capsys.readouterr().out


def test_handles_empty_streams(capsys):
    assert fallback.report_model_fallback("claude-haiku-4.5", "", "") is None
    assert capsys.readouterr().out == ""


def test_handles_no_streams(capsys):
    assert fallback.report_model_fallback("claude-haiku-4.5") is None
    assert capsys.readouterr().out == ""


def test_scans_later_streams_when_the_first_is_clean(capsys):
    substitute = fallback.report_model_fallback(
        "claude-haiku-4.5",
        "VERDICT: PASS",
        'not available; using "claude-opus-5" instead',
    )
    assert substitute == "claude-opus-5"
    assert "::warning::" in capsys.readouterr().out


def test_reports_the_first_match_only(capsys):
    substitute = fallback.report_model_fallback(
        "claude-haiku-4.5",
        'not available; using "claude-opus-5" instead',
        'not available; using "gpt-5.4" instead',
    )
    assert substitute == "claude-opus-5"
    assert capsys.readouterr().out.count("::warning::") == 1

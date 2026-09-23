"""Unit tests for Copilot CLI model selection and substitution detection.

A silently substituted model is a billing defect: the workflow asked for the
cheap tier, Copilot served the session default, and the exit code stayed 0.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from scripts.ci import _copilot_model as fallback
from scripts.ci import invoke_copilot_cli as invoke


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


def test_default_model_is_the_cheapest_served_tier():
    """The driver's floor, not just the action input default.

    An unset or empty COPILOT_MODEL used to send `--model ""` to the CLI.
    """
    assert fallback.DEFAULT_COPILOT_MODEL == "gpt-5.6-luna"


def test_default_model_is_not_a_rolling_alias():
    """Bare aliases are not valid Copilot model ids and fall back silently.

    Measured in `.project-toolkit/analysis/2026-08-12-adr-080-copilot-model-resolution.md`.
    """
    assert fallback.DEFAULT_COPILOT_MODEL not in {"haiku", "sonnet", "opus", "auto", ""}


def test_parse_config_floors_an_unset_model_to_the_cheap_default(tmp_path):
    config = invoke.parse_config(
        {
            "AI_REVIEW_OUTPUT_FILE": str(tmp_path / "out.txt"),
            "GITHUB_OUTPUT": str(tmp_path / "gh.txt"),
            "TIMEOUT_MINUTES": "2",
        }
    )

    assert config.copilot_model == invoke.DEFAULT_COPILOT_MODEL


def test_parse_config_floors_an_empty_model_to_the_cheap_default(tmp_path):
    """A composite action input passed explicitly-empty overrides its own default."""
    config = invoke.parse_config(
        {
            "AI_REVIEW_OUTPUT_FILE": str(tmp_path / "out.txt"),
            "GITHUB_OUTPUT": str(tmp_path / "gh.txt"),
            "TIMEOUT_MINUTES": "2",
            "COPILOT_MODEL": "",
        }
    )

    assert config.copilot_model == invoke.DEFAULT_COPILOT_MODEL


def test_parse_config_keeps_an_explicit_model_override(tmp_path):
    config = invoke.parse_config(
        {
            "AI_REVIEW_OUTPUT_FILE": str(tmp_path / "out.txt"),
            "GITHUB_OUTPUT": str(tmp_path / "gh.txt"),
            "TIMEOUT_MINUTES": "2",
            "COPILOT_MODEL": "claude-opus-5",
        }
    )

    assert config.copilot_model == "claude-opus-5"


def test_cli_never_receives_an_empty_model_flag(tmp_path):
    argv_seen: list[Sequence[str]] = []

    def runner(argv: Sequence[str]) -> invoke.CommandResult:
        argv_seen.append(argv)
        return invoke.CommandResult(returncode=0, stdout="VERDICT: PASS", stderr="")

    config = invoke.parse_config(
        {
            "AI_REVIEW_OUTPUT_FILE": str(tmp_path / "out.txt"),
            "GITHUB_OUTPUT": str(tmp_path / "gh.txt"),
            "TIMEOUT_MINUTES": "2",
        }
    )
    invoke.invoke_with_retry(
        config=config,
        full_prompt="prompt",
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    argv = list(argv_seen[0])
    model_value = argv[argv.index("--model") + 1]
    assert model_value == invoke.DEFAULT_COPILOT_MODEL
    assert model_value != ""

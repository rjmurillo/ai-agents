from __future__ import annotations

import pytest

from scripts.ci import establish_ai_review_deadline as deadline


def test_resolve_deadline_uses_minimum_model_budget():
    assert deadline.resolve_deadline({"TIMEOUT_MINUTES": "2"}, now=100.0) == 670.0


def test_resolve_deadline_uses_larger_configured_model_budget():
    assert deadline.resolve_deadline({"TIMEOUT_MINUTES": "8"}, now=100.0) == 850.0


def test_resolve_deadline_preserves_inherited_deadline():
    assert (
        deadline.resolve_deadline(
            {
                "TIMEOUT_MINUTES": "8",
                "INHERITED_DEADLINE_EPOCH": "1234.5",
            },
            now=100.0,
        )
        == 1234.5
    )


@pytest.mark.parametrize("timeout", ["", "-1", "abc", "1.5"])
def test_resolve_deadline_rejects_invalid_timeout(timeout):
    with pytest.raises(ValueError, match="timeout-minutes must be a non-negative integer"):
        deadline.resolve_deadline({"TIMEOUT_MINUTES": timeout}, now=100.0)


@pytest.mark.parametrize("inherited", ["-1", "1e10", "inf", "-inf", "nan", "1."])
def test_resolve_deadline_rejects_invalid_inherited_value(inherited):
    with pytest.raises(ValueError, match="AI_REVIEW_ACTION_DEADLINE_EPOCH must be numeric"):
        deadline.resolve_deadline(
            {
                "TIMEOUT_MINUTES": "5",
                "INHERITED_DEADLINE_EPOCH": inherited,
            },
            now=100.0,
        )


def test_main_writes_deadline_output(tmp_path, monkeypatch):
    output = tmp_path / "github-output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setenv("TIMEOUT_MINUTES", "5")
    monkeypatch.setenv("INHERITED_DEADLINE_EPOCH", "1234")

    assert deadline.main() == deadline.EXIT_OK
    assert output.read_text(encoding="utf-8") == "deadline_epoch=1234.000000\n"


def test_main_returns_config_error_without_github_output(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)

    assert deadline.main() == deadline.EXIT_CONFIG
    assert "GITHUB_OUTPUT is required" in capsys.readouterr().err

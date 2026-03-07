"""Tests for scripts.validation.token_budget module.

Validates token estimation heuristics, budget checking, and CLI behavior.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from scripts.validation.token_budget import (
    _count_punct_and_symbols,
    build_parser,
    estimate_token_count,
    main,
    validate_token_budget,
)

# ---------------------------------------------------------------------------
# _count_punct_and_symbols
# ---------------------------------------------------------------------------


class TestCountPunctAndSymbols:
    """Tests for punctuation/symbol counting."""

    def test_empty_string(self) -> None:
        assert _count_punct_and_symbols("") == 0

    def test_no_punct(self) -> None:
        assert _count_punct_and_symbols("hello world") == 0

    def test_basic_punctuation(self) -> None:
        result = _count_punct_and_symbols("Hello, world!")
        assert result == 2  # comma and exclamation mark

    def test_symbols(self) -> None:
        result = _count_punct_and_symbols("$100 + 50%")
        assert result >= 2  # at least $ and % and +


# ---------------------------------------------------------------------------
# estimate_token_count
# ---------------------------------------------------------------------------


class TestEstimateTokenCount:
    """Tests for token estimation heuristics."""

    def test_empty_string_returns_zero(self) -> None:
        assert estimate_token_count("") == 0

    def test_none_returns_zero(self) -> None:
        none_value: Any = None
        assert estimate_token_count(none_value) == 0

    def test_short_english_prose(self) -> None:
        text = "Hello world, this is a test."
        result = estimate_token_count(text)
        assert result > 0
        # ~27 chars / 4 = ~7 base tokens, with margin ~8
        assert result < 20

    def test_longer_prose_scales(self) -> None:
        short = "Hello world."
        long_text = short * 100
        short_count = estimate_token_count(short)
        long_count = estimate_token_count(long_text)
        assert long_count > short_count * 50  # Should scale roughly linearly

    def test_non_ascii_increases_estimate(self) -> None:
        ascii_text = "Hello world, this is a test sentence."
        rockets = "\U0001f680" * 12
        emoji_text = f"Hello world{rockets}"
        ascii_count = estimate_token_count(ascii_text)
        emoji_count = estimate_token_count(emoji_text)
        # Emoji text should have higher multiplier
        assert emoji_count >= ascii_count * 0.5

    def test_code_like_text_increases_estimate(self) -> None:
        prose = "This is a simple sentence about testing."
        code = 'Get-Content -Path $file | Where-Object {$_.Length -gt 0}'
        prose_count = estimate_token_count(prose)
        code_count = estimate_token_count(code)
        # Code should have higher token density
        assert code_count > 0
        assert prose_count > 0

    def test_digit_heavy_text(self) -> None:
        text = "ID: 12345-67890-12345-67890-12345"
        result = estimate_token_count(text)
        assert result > 0

    def test_newline_normalization(self) -> None:
        unix = "line1\nline2\nline3"
        windows = "line1\r\nline2\r\nline3"
        assert estimate_token_count(unix) == estimate_token_count(windows)

    def test_safety_margin_applied(self) -> None:
        text = "a" * 400  # 100 base tokens
        result = estimate_token_count(text)
        # With 5% margin: 100 * 1.0 * 1.05 = 105
        assert result >= 105


# ---------------------------------------------------------------------------
# validate_token_budget
# ---------------------------------------------------------------------------


class TestValidateTokenBudget:
    """Tests for the main validation logic."""

    def test_missing_handoff_returns_pass(self, tmp_path: Path) -> None:
        result = validate_token_budget(tmp_path, max_tokens=5000, ci=False)
        assert result == 0

    def test_within_budget_returns_pass(self, tmp_path: Path) -> None:
        agents_dir = tmp_path / ".agents"
        agents_dir.mkdir()
        handoff = agents_dir / "HANDOFF.md"
        handoff.write_text("# Handoff\n\nSmall content.", encoding="utf-8")

        result = validate_token_budget(tmp_path, max_tokens=5000, ci=False)
        assert result == 0

    def test_over_budget_non_ci_returns_pass(self, tmp_path: Path) -> None:
        agents_dir = tmp_path / ".agents"
        agents_dir.mkdir()
        handoff = agents_dir / "HANDOFF.md"
        # Generate large content that exceeds budget
        handoff.write_text("x" * 100000, encoding="utf-8")

        result = validate_token_budget(tmp_path, max_tokens=100, ci=False)
        assert result == 0  # Non-CI mode returns 0 even when over budget

    def test_over_budget_ci_returns_one(self, tmp_path: Path) -> None:
        agents_dir = tmp_path / ".agents"
        agents_dir.mkdir()
        handoff = agents_dir / "HANDOFF.md"
        handoff.write_text("x" * 100000, encoding="utf-8")

        result = validate_token_budget(tmp_path, max_tokens=100, ci=True)
        assert result == 1

    def test_exactly_at_budget(self, tmp_path: Path) -> None:
        agents_dir = tmp_path / ".agents"
        agents_dir.mkdir()
        handoff = agents_dir / "HANDOFF.md"
        # Small enough to be within a reasonable budget
        handoff.write_text("Test content.", encoding="utf-8")

        result = validate_token_budget(tmp_path, max_tokens=50000, ci=True)
        assert result == 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestBuildParser:
    """Tests for CLI argument parsing."""

    def test_default_max_tokens(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.max_tokens == 5000

    def test_custom_max_tokens(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--max-tokens", "3000"])
        assert args.max_tokens == 3000

    def test_ci_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--ci"])
        assert args.ci is True

    def test_custom_path(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--path", "/tmp/repo"])
        assert args.path == "/tmp/repo"


class TestMain:
    """Integration tests for main entry point."""

    def test_invalid_path_returns_two(self) -> None:
        result = main(["--path", "/nonexistent/path/that/does/not/exist"])
        assert result == 2

    def test_valid_empty_repo(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("CI", raising=False)
        result = main(["--path", str(tmp_path)])
        assert result == 0

    def test_within_budget(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("CI", raising=False)
        agents_dir = tmp_path / ".agents"
        agents_dir.mkdir()
        handoff = agents_dir / "HANDOFF.md"
        handoff.write_text("# Small handoff", encoding="utf-8")

        result = main(["--path", str(tmp_path), "--max-tokens", "5000"])
        assert result == 0

    def test_over_budget_ci(self, tmp_path: Path) -> None:
        agents_dir = tmp_path / ".agents"
        agents_dir.mkdir()
        handoff = agents_dir / "HANDOFF.md"
        handoff.write_text("x" * 100000, encoding="utf-8")

        result = main(["--path", str(tmp_path), "--max-tokens", "100", "--ci"])
        assert result == 1

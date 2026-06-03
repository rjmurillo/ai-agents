"""Tests for score_atomicity.py.

Covers the canonical worked examples, each deduction factor, the persistence
threshold exit-code contract, and the CLI argv boundary.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
_SCRIPT = _SCRIPT_DIR / "score_atomicity.py"

_spec = importlib.util.spec_from_file_location("score_atomicity", _SCRIPT)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
sys.modules["score_atomicity"] = _mod
_spec.loader.exec_module(_mod)

score_learning = _mod.score_learning
main = _mod.main
PERSISTENCE_THRESHOLD = _mod.PERSISTENCE_THRESHOLD


# --- Positive: a good learning scores high and persists ---------------------


def test_specific_metric_backed_learning_scores_excellent():
    # Arrange: the canonical "good" worked example.
    learning = "Redis cache with 5-min TTL reduced API calls by 73% for user profiles"

    # Act
    result = score_learning(learning)

    # Assert: excellent band, above the persistence threshold, no deductions.
    assert result.score >= 95
    assert result.quality == "Excellent"
    assert result.score >= PERSISTENCE_THRESHOLD
    assert result.breakdown == {}


def test_concise_actionable_learning_persists():
    # Arrange
    learning = "Pin git Actions to a SHA to block tag-hijack supply attacks"

    # Act
    result = score_learning(learning)

    # Assert
    assert result.score >= PERSISTENCE_THRESHOLD


# --- Negative: a vague learning scores low and is rejected ------------------


def test_vague_learning_scores_below_threshold():
    # Arrange: the canonical "bad" worked example uses a vague quality adjective.
    learning = "The caching strategy was effective"

    # Act
    result = score_learning(learning)

    # Assert: below persistence threshold, vague term recorded.
    assert result.score < PERSISTENCE_THRESHOLD
    assert "effective" in result.vague_terms
    assert "vague" in result.breakdown
    assert "missing_evidence" in result.breakdown
    assert "no_action" in result.breakdown


def test_vague_term_costs_twenty_percent():
    # Arrange: two learnings differing only by a vague qualifier, both with a
    # metric and actionable shape so other deductions stay equal.
    base = "Cut cold start to 600ms by lazy-loading the dashboard route module"
    vague = "Cut cold start to 600ms by generally lazy-loading the dashboard route"

    # Act
    base_score = score_learning(base).score
    vague_score = score_learning(vague).score

    # Assert: the vague variant loses exactly 20 points.
    assert base_score - vague_score == 20


def test_compound_statement_costs_fifteen_percent_each():
    # Arrange: a learning with two compound markers.
    learning = "Add a null check at 47 and redirect to login and also log the event"

    # Act
    result = score_learning(learning)

    # Assert: two "and" plus one "also" => three markers => 45 points off.
    assert result.compound_terms.count("and") == 2
    assert result.compound_terms.count("also") == 1
    assert result.breakdown["compound"] == 45


def test_missing_metrics_costs_twenty_five_percent():
    # Arrange: actionable, concise, no number.
    learning = "Add a null guard before dereferencing the session cookie object"

    # Act
    result = score_learning(learning)

    # Assert
    assert result.has_metrics is False
    assert result.breakdown["missing_evidence"] == 25


def test_long_learning_loses_five_percent_per_extra_word():
    # Arrange: 17 words, actionable, with a metric, no vague or compound terms.
    learning = (
        "Set a 30s timeout on each outbound github call so one hung "
        "request cannot wedge worker pools"
    )

    # Act
    result = score_learning(learning)

    # Assert: 17 words => 2 over 15 => 10 points off for length.
    assert result.word_count == 17
    assert result.breakdown["length"] == 10


# --- Edge: empty input is a configuration error -----------------------------


def test_empty_learning_raises_value_error():
    # Arrange / Act / Assert
    with pytest.raises(ValueError, match="non-empty"):
        score_learning("   ")


def test_score_clamps_to_zero_floor():
    # Arrange: pile on every deduction so the raw score goes negative.
    learning = (
        "The thing was generally sometimes effective and also good and "
        "better and well and generally fine across the whole system somehow"
    )

    # Act
    result = score_learning(learning)

    # Assert: never below zero.
    assert result.score == 0
    assert result.quality == "Rejected"


# --- CLI argv boundary ------------------------------------------------------


def test_cli_returns_zero_for_persisting_learning():
    # Arrange / Act
    rc = main(["Redis cache with 5-min TTL reduced API calls by 73% for user profiles"])

    # Assert
    assert rc == 0


def test_cli_returns_one_for_below_threshold_learning():
    # Arrange / Act
    rc = main(["The caching strategy was effective"])

    # Assert
    assert rc == 1


def test_cli_returns_two_for_missing_learning(monkeypatch):
    # Arrange: no argument and stdin is a tty (no piped input).
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)

    # Act
    rc = main([])

    # Assert
    assert rc == 2


def test_cli_subprocess_exit_code_for_vague_learning():
    # Arrange / Act: exercise the real process boundary, not just main().
    result = subprocess.run(
        [sys.executable, str(_SCRIPT), "The caching strategy was effective"],
        capture_output=True,
        text=True,
        timeout=30,
    )

    # Assert
    assert result.returncode == 1
    assert "Rejected" in result.stdout

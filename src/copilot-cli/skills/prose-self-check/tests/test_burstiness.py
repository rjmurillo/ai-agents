"""Behavioral tests for the Layer 3 burstiness proxy (issue #2728).

Covers positive (flat rhythm flagged), negative (varied rhythm clean), and edge
cases (empty input, single sentence, below-threshold count, bad path / CLI exit
codes). Tests follow Arrange/Act/Assert, one behavior per test.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "burstiness.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("burstiness", _SCRIPT)
    assert spec and spec.loader, "could not load burstiness.py"
    module = importlib.util.module_from_spec(spec)
    # Register before exec so dataclass resolution (Python 3.14) can find the
    # module via sys.modules during class processing.
    sys.modules["burstiness"] = module
    spec.loader.exec_module(module)
    return module


burstiness = _load_module()


def test_flat_rhythm_is_flagged() -> None:
    # Arrange: five sentences all five words long -> zero variance.
    text = " ".join(["one two three four five."] * 5)

    # Act
    stats = burstiness.analyze(text)

    # Assert
    assert stats.sentence_count == 5
    assert stats.coefficient_of_variation == 0.0
    assert stats.flat_rhythm_warning is True


def test_varied_rhythm_is_clean() -> None:
    # Arrange: deliberately mixed sentence lengths.
    text = (
        "Short. "
        "This sentence carries quite a few more words than the first one did. "
        "Mid length sentence here now. "
        "Tiny. "
        "Another long sentence with enough words to push the variance well up above the flat threshold today."
    )

    # Act
    stats = burstiness.analyze(text)

    # Assert
    assert stats.sentence_count == 5
    assert stats.coefficient_of_variation > burstiness.FLAT_RHYTHM_CV_THRESHOLD
    assert stats.flat_rhythm_warning is False


def test_below_min_sentences_does_not_warn() -> None:
    # Arrange: three uniform sentences, under MIN_SENTENCES_FOR_RHYTHM.
    text = "one two three. four five six. seven eight nine."

    # Act
    stats = burstiness.analyze(text)

    # Assert: variance is flat but too few sentences to judge, so no warning.
    assert stats.sentence_count == 3
    assert stats.flat_rhythm_warning is False


def test_empty_text_is_safe() -> None:
    # Arrange / Act
    stats = burstiness.analyze("")

    # Assert
    assert stats.sentence_count == 0
    assert stats.word_count == 0
    assert stats.mean_sentence_length == 0.0
    assert stats.flat_rhythm_warning is False


def test_single_sentence_has_zero_stddev() -> None:
    # Arrange / Act
    stats = burstiness.analyze("Just one sentence here.")

    # Assert
    assert stats.sentence_count == 1
    assert stats.stddev_sentence_length == 0.0
    assert stats.flat_rhythm_warning is False


def test_concreteness_counts_numbers_paths_entities() -> None:
    # Arrange: 1 number, 1 path, 1 multi-word entity.
    text = "The fix lands in scripts/run.py and drops latency by 42 percent. New York shipped it."

    # Act
    stats = burstiness.analyze(text)

    # Assert: at least the three concrete tokens are counted.
    assert stats.concreteness_count >= 3


def test_empty_prose_has_zero_concreteness() -> None:
    # Arrange / Act
    stats = burstiness.analyze("we should think about leveraging the synergy here.")

    # Assert
    assert stats.concreteness_count == 0


def test_main_exits_zero_on_valid_file(tmp_path: Path, capsys) -> None:
    # Arrange
    target = tmp_path / "art.md"
    target.write_text("one two three four five. " * 5, encoding="utf-8")

    # Act
    code = burstiness.main([str(target)])

    # Assert
    assert code == 0
    assert "sentences:" in capsys.readouterr().out


def test_main_json_output_is_valid(tmp_path: Path, capsys) -> None:
    # Arrange
    target = tmp_path / "art.md"
    target.write_text("Short. A much longer sentence than the first one here today.", encoding="utf-8")

    # Act
    code = burstiness.main([str(target), "--json"])

    # Assert
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert "coefficient_of_variation" in payload
    assert "flat_rhythm_warning" in payload


def test_main_exits_two_on_missing_file(capsys) -> None:
    # Arrange / Act
    code = burstiness.main(["/no/such/file/here.md"])

    # Assert
    assert code == 2
    assert "error:" in capsys.readouterr().err

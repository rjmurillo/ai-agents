#!/usr/bin/env python3
"""Layer 3 burstiness and concreteness proxy for the prose-self-check skill.

Computes sentence-length variance (burstiness) and a concreteness count
(numbers, file paths, capitalized multi-word entities) for a prose artifact.
Flat rhythm is the #2 reader-cited AI tell and is invisible to keyword passes;
this script surfaces it as a proxy, not a hard gate.

This is a proxy. A low coefficient of variation is a prompt to vary sentence
rhythm, not proof of AI authorship. The skill's four-layer judgment is the gate.

EXIT CODES (ADR-035):
  0  - Analyzed successfully (with or without a flat-rhythm warning)
  2  - Configuration or input error (missing file, unreadable path)

Refs: Issue #2728 (prose-self-check skill, Option A).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

# A coefficient of variation (stddev / mean) at or below this threshold marks
# flat rhythm. Human prose typically varies more; uniform AI prose clusters
# tightly. Calibrated as a proxy, not a precise classifier.
FLAT_RHYTHM_CV_THRESHOLD = 0.35

# Below this sentence count, variance is not meaningful, so no warning fires.
MIN_SENTENCES_FOR_RHYTHM = 4

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"\b[\w']+\b")
_NUMBER = re.compile(r"\b\d[\d,.]*\b")
_PATH = re.compile(r"[\w./-]+/[\w./-]+|\b[\w-]+\.(?:py|md|json|ya?ml|ts|js|cs|ps1|txt)\b")
_ENTITY = re.compile(r"\b(?:[A-Z][a-z0-9]+){1,}(?:\s+[A-Z][a-z0-9]+)+\b")


@dataclass(frozen=True)
class ProseStats:
    """Layer 3 proxy metrics for a prose artifact."""

    sentence_count: int
    word_count: int
    mean_sentence_length: float
    stddev_sentence_length: float
    coefficient_of_variation: float
    flat_rhythm_warning: bool
    concreteness_count: int


def _sentence_lengths(text: str) -> list[int]:
    """Return the word count of each non-empty sentence in ``text``."""
    sentences = [s for s in _SENTENCE_SPLIT.split(text.strip()) if s.strip()]
    return [len(_WORD.findall(s)) for s in sentences if _WORD.findall(s)]


def _mean(values: list[int]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _stddev(values: list[int], mean: float) -> float:
    """Population standard deviation. Zero for fewer than two values."""
    if len(values) < 2:
        return 0.0
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return variance**0.5


def _concreteness_count(text: str) -> int:
    """Count numbers, file paths, and multi-word capitalized entities.

    Near-zero concreteness usually signals fluent filler (feeds Layer 4).
    """
    return (
        len(_NUMBER.findall(text))
        + len(_PATH.findall(text))
        + len(_ENTITY.findall(text))
    )


def analyze(text: str) -> ProseStats:
    """Compute Layer 3 proxy metrics for ``text``.

    A flat-rhythm warning fires when there are enough sentences to judge
    variance AND the coefficient of variation sits at or below the threshold.
    """
    lengths = _sentence_lengths(text)
    mean = _mean(lengths)
    stddev = _stddev(lengths, mean)
    cv = stddev / mean if mean else 0.0
    flat = len(lengths) >= MIN_SENTENCES_FOR_RHYTHM and cv <= FLAT_RHYTHM_CV_THRESHOLD
    return ProseStats(
        sentence_count=len(lengths),
        word_count=sum(lengths),
        mean_sentence_length=round(mean, 2),
        stddev_sentence_length=round(stddev, 2),
        coefficient_of_variation=round(cv, 3),
        flat_rhythm_warning=flat,
        concreteness_count=_concreteness_count(text),
    )


def _read_target(raw: str) -> str:
    """Read the target file, raising FileNotFoundError on a missing path."""
    path = Path(raw)
    if not path.is_file():
        raise FileNotFoundError(f"not a file: {raw}")
    return path.read_text(encoding="utf-8")


def _render_human(stats: ProseStats) -> str:
    lines = [
        f"sentences:        {stats.sentence_count}",
        f"words:            {stats.word_count}",
        f"mean length:      {stats.mean_sentence_length}",
        f"stddev length:    {stats.stddev_sentence_length}",
        f"variation (CV):   {stats.coefficient_of_variation}",
        f"concreteness:     {stats.concreteness_count}",
    ]
    if stats.flat_rhythm_warning:
        lines.append(
            "WARNING: flat rhythm (low sentence-length variance). "
            "Vary it: break some sentences up, run others together."
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Layer 3 burstiness/concreteness proxy for prose-self-check."
    )
    parser.add_argument("file", help="path to the prose artifact to analyze")
    parser.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        text = _read_target(args.file)
    except (FileNotFoundError, OSError, UnicodeDecodeError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 2

    stats = analyze(text)
    if args.json:
        print(json.dumps(asdict(stats), indent=2))
    else:
        print(_render_human(stats))
    return 0


if __name__ == "__main__":
    sys.exit(main())

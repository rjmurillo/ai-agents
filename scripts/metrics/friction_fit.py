#!/usr/bin/env python3
"""Reproduce the REQ-048 AC-19 friction-score fit: nested CV, then a final tune.

Searches integer signal weights and a threshold ``T`` for the config with the
best Wilson lower bound on precision. A *firing unit* is the first Stop of a
session whose weighted score reaches ``T``. Precision is ``worth_it`` labels
over firing units.

The weight keys are the names in ``scripts.failure_classifier.FRICTION_WEIGHTS``.
Each maps to a per-Stop field in ``sessions.jsonl``:

    tool_error        <- tool_error
    permission_denial <- denial_v2
    stop_feedback     <- stop_feedback
    error_streak      <- error_streak_max

These fields are the shipped signals: the replay that wrote ``sessions.jsonl``
calls the shipped classifier functions, and parity against them was 0
mismatches. This script re-scores those counts; it never re-derives a signal.
``failed_retry`` and ``edit_churn`` stay at weight 0, as in the shipped table.

Grid: tool_error 0..1, permission_denial 0..3, stop_feedback 0..3,
error_streak 0..1, T 6..25. Selection key, best first: Wilson lower bound,
precision, firing units, lower total weight, lower T. A config with any
unlabeled firing unit is ineligible, so a missing label never counts as a miss.

EXIT CODES (ADR-035):
    0 - Success
    2 - Invalid arguments or input (missing or malformed file)
"""

from __future__ import annotations

import argparse
import csv
import functools
import itertools
import json
import math
import random
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if (_PROJECT_ROOT / "scripts" / "validation" / "models.py").is_file() and str(
    _PROJECT_ROOT
) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.failure_classifier import FRICTION_WEIGHTS  # noqa: E402

EXIT_OK = 0
EXIT_CONFIG = 2
FOLDS = 5
Z95 = 1.96
WORTH_IT = "worth_it"
TUNE_SPLIT = "tune"

# (FRICTION_WEIGHTS key, per-Stop field in sessions.jsonl, highest weight tried)
SIGNALS: tuple[tuple[str, str, int], ...] = (
    ("tool_error", "tool_error", 1),
    ("permission_denial", "denial_v2", 3),
    ("stop_feedback", "stop_feedback", 3),
    ("error_streak", "error_streak_max", 1),
)
SIGNAL_NAMES: tuple[str, ...] = tuple(name for name, _, _ in SIGNALS)
THRESHOLDS = range(6, 26)

Unit = tuple[str, int]
Weights = tuple[int, ...]
Counts = tuple[int, ...]
Pre = dict[str, list[tuple[int, Counts]]]


class InputError(Exception):
    """A missing or malformed input file."""


def wilson_bounds(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """The Wilson score interval for ``k`` successes in ``n`` trials."""
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    radius = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (centre - radius) / denom, (centre + radius) / denom


def wilson_lower(k: int, n: int, z: float = Z95) -> float:
    return wilson_bounds(k, n, z)[0]


def weighted_sum(weights: Mapping[str, int], counts: Mapping[str, int]) -> int:
    """The shipped score shape: sum of ``weights[name] * counts[name]``.

    Keys must be ``FRICTION_WEIGHTS`` names; an unknown key raises KeyError.
    """
    unknown = (set(weights) | set(counts)) - set(FRICTION_WEIGHTS)
    if unknown:
        raise KeyError(f"not a FRICTION_WEIGHTS signal: {sorted(unknown)}")
    return sum(weights.get(name, 0) * counts.get(name, 0) for name in FRICTION_WEIGHTS)


def stop_score(weights: Weights, counts: Counts) -> int:
    """``weighted_sum`` over positional ``SIGNALS`` order, for the search hot path.

    A test pins this equal to ``weighted_sum`` and to the shipped
    ``friction_score`` so the two cannot drift.
    """
    return sum(w * c for w, c in zip(weights, counts, strict=True))


def firing_unit(
    stops: Sequence[tuple[int, Counts]], weights: Weights, threshold: int
) -> int | None:
    """The index of the first Stop scoring at or above ``threshold``, else None."""
    for index, counts in stops:
        if stop_score(weights, counts) >= threshold:
            return index
    return None


def firing_units(pre: Pre, keys: Iterable[str], weights: Weights, threshold: int) -> list[Unit]:
    units: list[Unit] = []
    for key in keys:
        index = firing_unit(pre[key], weights, threshold)
        if index is not None:
            units.append((key, index))
    return units


def tally(
    pre: Pre, labels: Mapping[Unit, str], keys: Iterable[str], weights: Weights, threshold: int
) -> tuple[int, int, int]:
    """Return (firing units, worth_it units, unlabeled units)."""
    units = firing_units(pre, keys, weights, threshold)
    worth = sum(labels.get(unit) == WORTH_IT for unit in units)
    return len(units), worth, sum(unit not in labels for unit in units)


@functools.cache
def weight_grid() -> tuple[Weights, ...]:
    ranges = [range(top + 1) for _, _, top in SIGNALS]
    return tuple(w for w in itertools.product(*ranges) if any(w))


def best_config(
    pre: Pre, labels: Mapping[Unit, str], keys: Sequence[str], min_units: int
) -> tuple[tuple[float, float, int, int, int], Weights, int] | None:
    """The eligible config with the best selection key, or None.

    A config with no firing units is never eligible, whatever ``min_units`` is.
    """
    best: tuple[tuple[float, float, int, int, int], Weights, int] | None = None
    for weights, threshold in itertools.product(weight_grid(), THRESHOLDS):
        n, worth, unlabeled = tally(pre, labels, keys, weights, threshold)
        if n == 0 or n < min_units or unlabeled:
            continue
        rank = (wilson_lower(worth, n), worth / n, n, -sum(weights), -threshold)
        if best is None or rank > best[0]:
            best = (rank, weights, threshold)
    return best


def make_folds(keys: Sequence[str], seed: int) -> list[list[str]]:
    shuffled = list(keys)
    random.Random(seed).shuffle(shuffled)
    return [shuffled[i::FOLDS] for i in range(FOLDS)]


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in _read_text(path).splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except ValueError as error:
                raise InputError(f"{path}: bad JSON line: {error}") from error
    return rows


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise InputError(f"cannot read {path}: {error.strerror or error}") from error
    except UnicodeDecodeError as error:
        raise InputError(f"cannot read {path}: not valid UTF-8: {error.reason}") from error


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _stop_row(path: Path, key: str, stop: object) -> tuple[int, tuple[int, ...]]:
    where = f"{path}: session {key}"
    if not isinstance(stop, dict):
        raise InputError(f"{where}: stop is not an object")
    if not _is_int(stop.get("index")):
        raise InputError(f"{where}: stop 'index' missing or not an int")
    counts: list[int] = []
    for _, field, _ in SIGNALS:
        if not _is_int(stop.get(field)):
            raise InputError(f"{where}: stop field {field!r} missing or not an int")
        counts.append(stop[field])
    return stop["index"], tuple(counts)


def _session_rows(path: Path) -> dict[str, dict[str, Any]]:
    sessions: dict[str, dict[str, Any]] = {}
    for number, row in enumerate(_load_jsonl(path), start=1):
        if not isinstance(row, dict):
            raise InputError(f"{path}: row {number} is not an object")
        session_id = row.get("session_id")
        if not isinstance(session_id, str):
            raise InputError(f"{path}: row {number} has no string 'session_id'")
        sessions[session_id] = row
    return sessions


def load_pre(path: Path, keys: Iterable[str]) -> Pre:
    """Per-session (stop index, signal counts) rows for the tuning sessions."""
    sessions = _session_rows(path)
    wanted = list(keys)
    missing = [key for key in wanted if key not in sessions]
    if missing:
        raise InputError(f"{path}: {len(missing)} tuning sessions absent, e.g. {missing[0]}")
    pre: Pre = {}
    for key in wanted:
        stops = sessions[key].get("stops")
        if not isinstance(stops, list):
            raise InputError(f"{path}: session {key} has no 'stops' list")
        pre[key] = [_stop_row(path, key, stop) for stop in stops]
    return pre


def load_tune_keys(path: Path) -> list[str]:
    try:
        keys = json.loads(_read_text(path))["tune"]
        if not all(isinstance(key, str) for key in keys):
            raise TypeError("every tune entry must be a string")
        return sorted(keys)
    except (ValueError, KeyError, TypeError) as error:
        raise InputError(f"{path}: no 'tune' list: {error}") from error


def load_labels(path: Path) -> dict[Unit, str]:
    """Labels for the tuning split, keyed by (session_id, stop)."""
    labels: dict[Unit, str] = {}
    try:
        for row in csv.DictReader(_read_text(path).splitlines()):
            if row["split"] == TUNE_SPLIT:
                labels[(row["session_id"], int(row["stop"]))] = row["label"]
    except (KeyError, ValueError, TypeError) as error:
        raise InputError(f"{path}: need columns split,session_id,stop,label: {error}") from error
    return labels


def _fmt_weights(weights: Weights) -> str:
    return " ".join(f"{name}={value}" for name, value in zip(SIGNAL_NAMES, weights, strict=True))


def cross_validate(
    pre: Pre, labels: Mapping[Unit, str], keys: Sequence[str], seed: int, min_train: int
) -> tuple[int, int]:
    """Print each fold's choice; return pooled out-of-fold (worth_it, firing units)."""
    folds = make_folds(keys, seed)
    pooled_k = pooled_n = 0
    for i, test in enumerate(folds):
        train = [key for j, fold in enumerate(folds) if j != i for key in fold]
        best = best_config(pre, labels, train, min_train)
        if best is None:
            raise InputError(f"fold {i}: no eligible config at min-train {min_train}")
        rank, weights, threshold = best
        n, worth, unlabeled = tally(pre, labels, test, weights, threshold)
        pooled_k, pooled_n = pooled_k + worth, pooled_n + n
        print(
            f"fold {i} {_fmt_weights(weights)} T={threshold} "
            f"train_prec={rank[1]:.2f} train_n={rank[2]} test={worth}/{n} unlabeled={unlabeled}"
        )
    return pooled_k, pooled_n


def run(args: argparse.Namespace) -> int:
    keys = load_tune_keys(args.split)
    pre = load_pre(args.sessions, keys)
    labels = load_labels(args.labels)
    k, n = cross_validate(pre, labels, keys, args.fold_seed, args.min_train)
    low, high = wilson_bounds(k, n)
    print(
        f"CV pooled {k}/{n} precision={k / max(n, 1):.3f} "
        f"wilson95_lb={low:.3f} wilson95_ub={high:.3f}"
    )
    final = best_config(pre, labels, keys, args.min_final)
    if final is None:
        raise InputError(f"no eligible final config at min-final {args.min_final}")
    _, weights, threshold = final
    n, worth, unlabeled = tally(pre, labels, keys, weights, threshold)
    low, high = wilson_bounds(worth, n)
    print(
        f"final {_fmt_weights(weights)} T={threshold} tune={worth}/{n} "
        f"precision={worth / n:.3f} wilson95_lb={low:.3f} wilson95_ub={high:.3f} "
        f"unlabeled={unlabeled}"
    )
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("--sessions", required=True, type=Path, help="sessions.jsonl")
    parser.add_argument("--split", required=True, type=Path, help="split.json with a 'tune' list")
    parser.add_argument(
        "--labels", required=True, type=Path, help="CSV: split,session_id,stop,label"
    )
    parser.add_argument("--fold-seed", type=int, default=48002)
    parser.add_argument("--min-train", type=int, default=14, help="min firing units per CV train")
    parser.add_argument("--min-final", type=int, default=20, help="min firing units, final fit")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except InputError as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_CONFIG


if __name__ == "__main__":
    sys.exit(main())

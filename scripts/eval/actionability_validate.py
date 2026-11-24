"""Row validation shared by the corpus, predict, and score code.

A corpus row or prediction record with a missing or wrong-typed field becomes a
``RecordError`` that names the row position, its id, and the field. Callers map it to
exit 2. The message never carries the offending value, because a field can hold a secret.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import Any

from scripts.eval.actionability_labels import SPLIT_DEV, SPLIT_HELDOUT, SPLIT_OUTSIDE

SPLITS = (SPLIT_DEV, SPLIT_HELDOUT, SPLIT_OUTSIDE)

Check = tuple[str, Callable[[object], bool], str]


class RecordError(ValueError):
    """A record failed a check. Maps to exit code 2."""


def is_str(value: object) -> bool:
    return isinstance(value, str)


def is_list_of_str(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def finite_number(value: object) -> bool:
    """True for a real int or float that is finite. A bool is not a number here."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    try:
        return math.isfinite(float(value))
    except OverflowError:
        return False


def is_nonempty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def is_str_or_none(value: object) -> bool:
    return value is None or isinstance(value, str)


def is_bool_or_none(value: object) -> bool:
    return value is None or isinstance(value, bool)


def is_number_or_none(value: object) -> bool:
    return value is None or finite_number(value)


def is_int(value: object) -> bool:
    """True for a real int. A bool is not one here."""
    return isinstance(value, int) and not isinstance(value, bool)


def is_int_or_none(value: object) -> bool:
    return value is None or (isinstance(value, int) and not isinstance(value, bool))


# (key, predicate, description). Checked against ``record.get(key)``, so an absent key
# fails unless None is allowed. A label of None is handled later as "unlabeled".
SCORE_CORPUS_CHECKS = (
    ("id", is_nonempty_str, "a non-empty string"),
    ("split", lambda v: v in SPLITS, f"one of {', '.join(SPLITS)}"),
    ("in_band", lambda v: isinstance(v, bool), "a bool"),
    ("heuristic_score", finite_number, "a finite number"),
    ("label", is_str_or_none, "a string or null"),
    ("pr_number", is_int, "an int"),
    ("corpus_seed", is_int_or_none, "an int or null"),
    ("corpus_head_sha", is_str_or_none, "a string or null"),
)
PREDICTION_CHECKS = (
    ("id", is_nonempty_str, "a non-empty string"),
    ("status", lambda v: isinstance(v, str), "a string"),
    ("is_actionable", is_bool_or_none, "a bool or null"),
    ("confidence", is_number_or_none, "a finite number or null"),
    ("latency_s", is_number_or_none, "a finite number or null"),
    ("provider", is_str_or_none, "a string or null"),
    ("model", is_str_or_none, "a string or null"),
    ("prompt_sha256", is_str_or_none, "a string or null"),
)


# Fields that predict sends and that the secret scan reads (body, replies, path).
SENT_ROW_CHECKS: tuple[Check, ...] = (
    ("id", is_nonempty_str, "a non-empty string"),
    ("body", is_str, "a string"),
    ("thread_replies", is_list_of_str, "a list of strings"),
    ("path", is_str_or_none, "a string or null"),
)

# Fetch-hunks reads and rewrites every row, so it also needs the hunk fields.
HUNK_ROW_CHECKS: tuple[Check, ...] = (
    *SENT_ROW_CHECKS,
    ("diff_hunk", is_str_or_none, "a string or null"),
    ("hunk_status", is_str_or_none, "a string or null"),
)


def validate_records(
    records: Sequence[dict[str, Any]],
    checks: Sequence[Check],
    where: str,
    numbers: Sequence[int] | None = None,
) -> None:
    """Raise RecordError naming the first record and key that breaks a check.

    Checked against ``record.get(key)``, so an absent key fails unless None is allowed.
    ``numbers`` gives each record's 1-based position in the file it came from, for callers
    that validate only a selection of its rows.
    """
    for offset, record in enumerate(records):
        index = numbers[offset] if numbers is not None else offset + 1
        for key, accepts, description in checks:
            if not accepts(record.get(key)):
                record_id = record.get("id")
                named = f" ({record_id})" if isinstance(record_id, str) and record_id else ""
                raise RecordError(f"{where} row {index}{named}: {key} must be {description}")

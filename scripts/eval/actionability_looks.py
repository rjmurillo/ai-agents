"""The verdict rule and the two looks of the actionability eval.

Split out of ``actionability_score.py``, which re-exports every name here. Owner decision D1
(spec, Eval method and kill criterion 2): pass needs a gap of at least ``PASS_GAP`` with an
interval above zero, fail needs an interval wholly under ``PASS_GAP``, and everything else is
inconclusive. An inconclusive look 1 may take one extension, look 2, which is always final.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from scripts.eval.actionability_labels import SPLIT_HELDOUT

PASS_GAP = 0.10

# Both looks use the same interval. Alpha 0.05 is split over the two looks, 0.025 each, so each
# look is a two-sided 97.5 percent interval: the 1.25th to 98.75th percentile. Look 1 uses it
# too, so the total error stays at 0.05 whether or not the extension is taken.
LOOKS = (1, 2)

# Spec, Eval method: "On a look-1 inconclusive, label 100 more band items once".
LOOK2_MIN_ADDED_BAND_ROWS = 100


def verdict(gap: float, ci_low: float, ci_high: float) -> str:
    """Apply the verdict rule: pass, fail, or inconclusive.

    Fail needs ``ci_high < PASS_GAP``: only an interval that lies wholly under the bar proves
    the gain is below it. A small gap whose interval still reaches the bar is inconclusive.
    """
    if gap >= PASS_GAP and ci_low > 0:
        return "pass"
    if ci_high < PASS_GAP:
        return "fail"
    return "inconclusive"


def kill_criterion_2(result: str, look: int) -> str:
    """fired only on fail. Inconclusive is pending at look 1 and not fired at look 2."""
    if result == "fail":
        return "fired"
    if result == "inconclusive" and look == LOOKS[0]:
        return "pending"
    return "not_fired"


def is_final(result: str, look: int) -> bool:
    """A result is final unless it is inconclusive at look 1, which may take the one extension."""
    return result != "inconclusive" or look == LOOKS[-1]


def heldout_band_row_count(rows: Sequence[Mapping[str, Any]]) -> int:
    """Heldout band rows in the corpus, unsure ones included: the rows a labeler had to read."""
    return sum(1 for r in rows if r["split"] == SPLIT_HELDOUT and r["in_band"])

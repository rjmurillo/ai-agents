"""Enrollment-cost contract for a discovered `/review` axis.

`resources/axis-selection.md` says what enrolling an axis costs, and the cost
depends on how the axis is meant to be reached. An axis intended for risk mode
needs a `_RISK_TABLE` or `_EFFECT_TABLE` entry. An axis intended to be reachable
only through `--deep` or `--pin` needs the prompt file alone.

Without this module the doc claim is unenforced, and the cheapest way to satisfy
a "every axis needs a table entry" reading is to invent an unrelated risk rule
for a deep-only axis, which then fires on changes it was never meant to review.

Kept out of ``test_select_axes_contract.py`` because that module is already over
the 500-line taste limit.
"""

from __future__ import annotations

import sys
from pathlib import Path

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(
    ".claude/skills/review/scripts/select_axes.py",
    module_name="review_select_axes_enrollment",
)

REFERENCES_DIR = PROJECT_ROOT / ".claude" / "skills" / "review" / "references"

# A discovered axis that deliberately carries no risk or effect mapping. The
# name is not a real prompt stem, so a table entry for it cannot exist.
DEEP_ONLY_AXIS = "enrollment-probe-axis"

# The shipped set is used verbatim, plus the probe. A reduced candidate set
# would leave a matched category demanding an absent axis, which fail-closes the
# run and selects everything, hiding the behavior under test.
SHIPPED = tuple(mod.discover_canonical_axes(REFERENCES_DIR))
CANDIDATES = (*SHIPPED, DEEP_ONLY_AXIS)

# A path that classifies cleanly, so a skip is the routing decision rather than
# the fail-closed fallback an unclassified path triggers.
CLASSIFIED_PATH = "src/app/widget.py"


def select(candidates: tuple[str, ...] = CANDIDATES, **kwargs: object) -> dict:
    return mod.select_axes(
        changed_paths=[CLASSIFIED_PATH],
        canonical_candidates=candidates,
        **kwargs,
    )


def _risk_table_axes() -> set[str]:
    """Every axis name reachable through `_RISK_TABLE`, canonical or local.

    Rows of `_RISK_TABLE` are `(category, predicate, canonical_axes,
    local_axes)`.
    """
    return {axis for row in mod._RISK_TABLE for axis in (*row[2], *row[3])}


def _effect_table_axes() -> set[str]:
    """Every axis name reachable through `_EFFECT_TABLE`, canonical or local.

    Values of `_EFFECT_TABLE` are `(canonical_axes, local_axes)`.
    """
    return {
        axis for canonical, local in mod._EFFECT_TABLE.values() for axis in (*canonical, *local)
    }


class TestDeepOnlyAxisNeedsNoTableEntry:
    """A table-less discovered axis stays reachable through --deep and --pin."""

    def test_probe_axis_is_absent_from_both_tables(self):
        """Negative control: the premise of every other test in this class.

        If someone maps this name, the tests below would pass for the wrong
        reason, so assert the gap directly.
        """
        assert DEEP_ONLY_AXIS not in _risk_table_axes()
        assert DEEP_ONLY_AXIS not in _effect_table_axes()

    def test_classified_run_skips_it_with_a_reason(self):
        """No table entry means skipped on a normal run, and skipped is not PASS."""
        result = select()
        assert DEEP_ONLY_AXIS not in result["canonical_selected"]
        assert result["skipped"][DEEP_ONLY_AXIS]

    def test_classified_run_does_not_call_it_unresolved(self):
        """A deliberate skip is not a missing prompt, so it must not fail closed.

        `unresolved_axes` is for an axis the change demanded that has no prompt.
        Reporting a deep-only axis there would turn every classified run red.
        """
        result = select()
        assert DEEP_ONLY_AXIS not in result["unresolved_axes"]
        assert result["fail_closed"] is False

    def test_adding_it_changes_nothing_else(self):
        """Negative control: the probe is inert, not globally suppressing.

        Same path, with and without the probe in the candidate set. If the
        selection differed, the skip above would prove nothing about enrollment.
        """
        with_probe = select()
        without_probe = select(candidates=SHIPPED)
        assert with_probe["canonical_selected"] == without_probe["canonical_selected"]
        assert with_probe["canonical_selected"], "a classified source path selected no axis"

    def test_deep_selects_it_without_a_table_entry(self):
        result = select(deep=True)
        assert DEEP_ONLY_AXIS in result["canonical_selected"]

    def test_pin_selects_it_without_a_table_entry(self):
        result = select(pinned=[DEEP_ONLY_AXIS])
        assert DEEP_ONLY_AXIS in result["canonical_selected"]
        assert "pinned" in result["selection_reasons"][DEEP_ONLY_AXIS]

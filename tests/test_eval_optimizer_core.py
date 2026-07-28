"""Tests for scripts/eval/_optimizer_core.py (Issue #3422).

Pure-function tests. The module under test performs no I/O and makes no API
calls, so nothing here is mocked; every case is exercised directly.

Coverage obligation per .agents/governance/TESTING-RIGOR.md: positive, negative,
and edge cases per public function, every raise branch, every conditional
branch that changes user-facing output.
"""

from __future__ import annotations

import math
import os
import subprocess
import sys
import time
from decimal import localcontext
from fractions import Fraction
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_EVAL_DIR = _REPO_ROOT / "scripts" / "eval"
# Scope the mutation to the module load and remove it afterward so a sibling
# test cannot pick up an importable name it never asked for, and so repeated
# imports cannot stack duplicate entries.
_path_added = str(_EVAL_DIR) not in sys.path
if _path_added:
    sys.path.insert(0, str(_EVAL_DIR))

from _optimizer_core import (  # noqa: E402
    AmbiguousAnchorError,
    AnchorNotFoundError,
    BudgetExceededError,
    MissingResultError,
    Patch,
    PatchShapeError,
    ProtectedSectionError,
    SplitTooSmallError,
    apply_patches,
    buffer_contains,
    edit_budget,
    gate,
    guard_refusal,
    mcnemar_exact,
    patch_fingerprint,
    score,
    split_fingerprint,
    split_tasks,
)

if _path_added and str(_EVAL_DIR) in sys.path:
    sys.path.remove(str(_EVAL_DIR))

FENCE_START = "<!-- SLOW_UPDATE_START -->"
FENCE_END = "<!-- SLOW_UPDATE_END -->"


def _ids(n: int, prefix: str = "F") -> list[str]:
    return [f"{prefix}{i:03d}" for i in range(1, n + 1)]


def _half_up_fraction(total: int, ratio: str) -> int:
    value = Fraction(total) * Fraction(ratio)
    return (value + Fraction(1, 2)).numerator // (value + Fraction(1, 2)).denominator


# ---------------------------------------------------------------------------
# split_tasks
# ---------------------------------------------------------------------------


class TestSplitTasks:
    def test_partitions_every_task_exactly_once(self):
        ids = _ids(10)
        split = split_tasks(ids, seed="s", sel_ratio=0.4)
        combined = list(split.opt) + list(split.sel) + list(split.test)
        assert sorted(combined) == sorted(ids)
        assert len(set(combined)) == len(ids)

    def test_sel_count_is_exact_not_approximate(self):
        """A hash-bucketing split can hand a 10-task set a 1-task gate."""
        split = split_tasks(_ids(10), seed="s", sel_ratio=0.4)
        assert len(split.sel) == 4
        assert len(split.opt) == 6

    def test_string_ratio_rounds_half_up_via_decimal_parsing(self):
        split = split_tasks(_ids(25), seed="s", sel_ratio="0.58", min_sel=0)
        assert len(split.sel) == 15
        assert len(split.opt) == 10

    def test_ratio_sizing_ignores_decimal_context_precision(self):
        with localcontext() as context:
            context.prec = 2
            split = split_tasks(_ids(25), seed="s", sel_ratio="0.58", min_sel=0)
        assert len(split.sel) == 15
        assert len(split.opt) == 10

    @pytest.mark.parametrize("total", range(1, 31))
    @pytest.mark.parametrize("ratio", ["0.01", "0.1", "0.25", "0.33", "0.5", "0.58", "0.99"])
    def test_ratio_sizing_matches_exact_fraction_half_up(self, total, ratio):
        expected = _half_up_fraction(total, ratio)
        if expected == 0:
            with pytest.raises(SplitTooSmallError, match="at least one"):
                split_tasks(_ids(total), seed="s", sel_ratio=ratio, min_sel=0)
            return
        if total - expected < 1:
            with pytest.raises(ValueError, match="leaves no opt tasks"):
                split_tasks(_ids(total), seed="s", sel_ratio=ratio, min_sel=0)
            return
        split = split_tasks(_ids(total), seed="s", sel_ratio=ratio, min_sel=0)
        assert len(split.sel) == expected

    def test_is_deterministic_across_calls(self):
        a = split_tasks(_ids(20), seed="seed-1", sel_ratio=0.3)
        b = split_tasks(_ids(20), seed="seed-1", sel_ratio=0.3)
        assert a.sel == b.sel
        assert a.opt == b.opt

    def test_input_order_does_not_change_the_split(self):
        forward = split_tasks(_ids(20), seed="s", sel_ratio=0.3)
        backward = split_tasks(list(reversed(_ids(20))), seed="s", sel_ratio=0.3)
        assert forward.sel == backward.sel
        assert forward.opt == backward.opt

    def test_different_seeds_produce_different_splits(self):
        a = split_tasks(_ids(20), seed="seed-a", sel_ratio=0.3)
        b = split_tasks(_ids(20), seed="seed-b", sel_ratio=0.3)
        assert a.sel != b.sel

    def test_three_way_split_reserves_test_tasks(self):
        split = split_tasks(_ids(20), seed="s", sel_ratio=0.3, test_ratio=0.2)
        assert len(split.sel) == 6
        assert len(split.test) == 4
        assert len(split.opt) == 10
        assert not set(split.test) & set(split.sel)

    def test_test_split_is_empty_by_default(self):
        assert split_tasks(_ids(10), seed="s").test == ()

    def test_fingerprint_is_stable_for_same_inputs(self):
        a = split_tasks(_ids(10), seed="s", sel_ratio=0.4)
        b = split_tasks(_ids(10), seed="s", sel_ratio=0.4)
        assert a.fingerprint == b.fingerprint

    def test_fingerprint_changes_when_a_task_is_added(self):
        """Adding fixtures after a losing gate must invalidate the incumbent."""
        before = split_tasks(_ids(10), seed="s", sel_ratio=0.4)
        after = split_tasks(_ids(11), seed="s", sel_ratio=0.4)
        assert before.fingerprint != after.fingerprint

    def test_fingerprint_changes_when_ratio_changes(self):
        a = split_tasks(_ids(20), seed="s", sel_ratio=0.3)
        b = split_tasks(_ids(20), seed="s", sel_ratio=0.5)
        assert a.fingerprint != b.fingerprint

    def test_fingerprint_changes_when_seed_changes(self):
        a = split_tasks(_ids(20), seed="s1", sel_ratio=0.3)
        b = split_tasks(_ids(20), seed="s2", sel_ratio=0.3)
        assert a.fingerprint != b.fingerprint

    # -- negative -----------------------------------------------------------

    def test_rejects_empty_task_list(self):
        with pytest.raises(ValueError, match="at least one task"):
            split_tasks([], seed="s")

    def test_rejects_duplicate_task_ids(self):
        with pytest.raises(ValueError, match="duplicate"):
            split_tasks(["A", "B", "A"], seed="s")

    def test_rejects_an_empty_task_id(self):
        with pytest.raises(ValueError, match="non-empty"):
            split_tasks(["A", "", "C", "D"], seed="s")

    def test_rejects_blank_task_id(self):
        with pytest.raises(ValueError, match="whitespace|non-empty"):
            split_tasks(["A", "   "], seed="s")

    def test_rejects_empty_seed(self):
        with pytest.raises(ValueError, match="seed"):
            split_tasks(_ids(10), seed="")

    @pytest.mark.parametrize("ratio", [0.0, 1.0, -0.1, 1.5])
    def test_rejects_out_of_range_sel_ratio(self, ratio):
        with pytest.raises(ValueError, match="sel_ratio"):
            split_tasks(_ids(20), seed="s", sel_ratio=ratio)

    @pytest.mark.parametrize("ratio", ["nan", "Infinity", "not-a-ratio"])
    def test_rejects_invalid_decimal_sel_ratio(self, ratio):
        with pytest.raises(ValueError, match="sel_ratio"):
            split_tasks(_ids(20), seed="s", sel_ratio=ratio)

    @pytest.mark.parametrize("ratio", ["nan", "Infinity", "not-a-ratio"])
    def test_rejects_invalid_decimal_test_ratio(self, ratio):
        with pytest.raises(ValueError, match="test_ratio"):
            split_tasks(_ids(20), seed="s", test_ratio=ratio)

    @pytest.mark.parametrize("ratio", [-0.1, 1.0, 1.5])
    def test_rejects_out_of_range_test_ratio(self, ratio):
        with pytest.raises(ValueError, match="test_ratio"):
            split_tasks(_ids(20), seed="s", test_ratio=ratio)

    def test_rejects_ratios_that_leave_no_opt_tasks(self):
        with pytest.raises(ValueError, match="opt"):
            split_tasks(_ids(20), seed="s", sel_ratio=0.6, test_ratio=0.4)

    def test_rejects_a_rounding_that_starves_the_opt_group(self):
        """Ratios summing below 1 can still round away every optimize task."""
        with pytest.raises(ValueError, match="leaves no opt tasks"):
            split_tasks(_ids(2), seed="s", sel_ratio=0.4, test_ratio=0.4, min_sel=0)

    def test_refuses_a_gate_too_small_to_mean_anything(self):
        with pytest.raises(SplitTooSmallError, match="min_sel"):
            split_tasks(_ids(4), seed="s", sel_ratio=0.25, min_sel=3)

    def test_split_too_small_error_names_the_shortfall(self):
        with pytest.raises(SplitTooSmallError) as excinfo:
            split_tasks(_ids(4), seed="s", sel_ratio=0.25, min_sel=3)
        message = str(excinfo.value)
        assert "1" in message
        assert "3" in message

    def test_rejects_negative_min_sel(self):
        with pytest.raises(ValueError, match="min_sel"):
            split_tasks(_ids(10), seed="s", min_sel=-1)

    # -- edge ---------------------------------------------------------------

    def test_min_sel_zero_allows_a_degenerate_gate(self):
        """Explicitly opting out of the floor is allowed; it is not the default."""
        split = split_tasks(_ids(4), seed="s", sel_ratio=0.25, min_sel=0)
        assert len(split.sel) == 1

    def test_zero_test_ratio_still_reserves_no_tasks(self):
        split = split_tasks(_ids(25), seed="s", sel_ratio="0.5", test_ratio="0.0")
        assert len(split.sel) == 13
        assert split.test == ()
        assert len(split.opt) == 12

    @pytest.mark.parametrize("ratio", ["1e20000000", "1e-20000000", "-1e20000000"])
    def test_rejects_absurd_decimal_exponents_before_fraction_conversion(self, ratio):
        with pytest.raises(ValueError, match="decimal ratio"):
            split_tasks(_ids(25), seed="s", sel_ratio=ratio, min_sel=0)

    def test_rejects_absurd_decimal_coefficients_before_fraction_conversion(self):
        ratio = "0." + "1" * 65
        with pytest.raises(ValueError, match="coefficient digits") as excinfo:
            split_tasks(_ids(25), seed="s", sel_ratio=ratio, min_sel=0)
        assert len(str(excinfo.value)) < 200

    def test_accepts_the_largest_allowed_decimal_coefficient(self):
        ratio = "0." + "1" * 64
        split = split_tasks(_ids(25), seed="s", sel_ratio=ratio, min_sel=0)
        assert len(split.sel) == 3

    def test_million_digit_ratio_rejection_has_a_subprocess_deadline(self):
        script = """
import sys
from _optimizer_core import split_tasks

try:
    split_tasks([f"t{i}" for i in range(25)], seed="s", sel_ratio="0." + "1" * 1_000_000, min_sel=0)
except ValueError as exc:
    print(len(str(exc)))
    sys.exit(0)
sys.exit(1)
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            check=False,
            capture_output=True,
            cwd=_REPO_ROOT,
            env={**os.environ, "PYTHONPATH": str(_EVAL_DIR)},
            text=True,
            timeout=2,
        )
        assert result.returncode == 0
        assert int(result.stdout.strip()) < 200

    def test_semantic_ratio_errors_truncate_long_values(self):
        ratio = "0." + "0" * 125
        with pytest.raises(ValueError, match="strictly between 0 and 1") as excinfo:
            split_tasks(_ids(25), seed="s", sel_ratio=ratio, min_sel=0)
        assert len(str(excinfo.value)) < 200

    def test_ratio_sum_error_truncates_both_values(self):
        sel_ratio = "0." + "9" * 64
        test_ratio = "0." + "1" * 64
        with pytest.raises(ValueError, match="leave at least one opt task") as excinfo:
            split_tasks(_ids(25), seed="s", sel_ratio=sel_ratio, test_ratio=test_ratio, min_sel=0)
        assert len(str(excinfo.value)) < 200

    def test_one_task_cannot_leave_an_opt_task_after_rounding(self):
        with pytest.raises(ValueError, match="leaves no opt tasks"):
            split_tasks(_ids(1), seed="s", sel_ratio="0.5", min_sel=0)

    def test_ratio_one_is_rejected_before_rounding(self):
        with pytest.raises(ValueError, match="sel_ratio"):
            split_tasks(_ids(25), seed="s", sel_ratio="1.0")

    def test_smallest_viable_set_splits(self):
        split = split_tasks(_ids(4), seed="s", sel_ratio=0.75, min_sel=3)
        assert len(split.sel) == 3
        assert len(split.opt) == 1

    def test_task_ids_with_edge_whitespace_are_rejected(self):
        """Silently stripping an id makes it stop matching the result map.

        The result mapping is keyed by the id the scorer emitted. If the split
        rewrites " A " to "A", every later lookup raises MissingResultError far
        from the cause. Refusing the input names the problem at its source.
        """
        with pytest.raises(ValueError, match="whitespace"):
            split_tasks([" A ", "B", "C", "D"], seed="s", sel_ratio=0.5, min_sel=1)

    def test_rejects_ids_that_collide_after_stripping(self):
        with pytest.raises(ValueError, match="whitespace"):
            split_tasks(["A", " A "], seed="s", min_sel=1)

    def test_refuses_to_produce_an_empty_held_out_group(self):
        """min_sel=0 must not be a route to a gate that holds nothing out.

        An empty sel group is not a lenient gate, it is no gate: score() would
        raise on the empty sequence and the caller would read a crash instead
        of a verdict.
        """
        with pytest.raises(SplitTooSmallError, match="at least one"):
            split_tasks(_ids(20), seed="s", sel_ratio=0.01, min_sel=0)


# ---------------------------------------------------------------------------
# edit_budget
# ---------------------------------------------------------------------------


class TestEditBudget:
    def test_first_step_gets_the_maximum(self):
        assert edit_budget(0, 10, max_edits=5, min_edits=1) == 5

    def test_final_step_gets_the_minimum(self):
        assert edit_budget(10, 10, max_edits=5, min_edits=1) == 1

    def test_decays_monotonically(self):
        budgets = [edit_budget(t, 10, max_edits=8, min_edits=1) for t in range(11)]
        assert budgets == sorted(budgets, reverse=True)

    def test_midpoint_is_near_the_average(self):
        assert edit_budget(5, 10, max_edits=5, min_edits=1) == 3

    def test_steps_past_total_clamp_to_minimum(self):
        assert edit_budget(50, 10, max_edits=5, min_edits=1) == 1

    def test_equal_bounds_produce_a_flat_budget(self):
        assert [edit_budget(t, 4, max_edits=2, min_edits=2) for t in range(5)] == [2] * 5

    # -- negative -----------------------------------------------------------

    def test_rejects_negative_step(self):
        with pytest.raises(ValueError, match="step"):
            edit_budget(-1, 10)

    @pytest.mark.parametrize("total", [0, -3])
    def test_rejects_non_positive_total(self, total):
        with pytest.raises(ValueError, match="total"):
            edit_budget(0, total)

    def test_rejects_min_above_max(self):
        with pytest.raises(ValueError, match="min_edits"):
            edit_budget(0, 10, max_edits=2, min_edits=5)

    def test_rejects_min_below_one(self):
        with pytest.raises(ValueError, match="min_edits"):
            edit_budget(0, 10, max_edits=5, min_edits=0)

    # -- edge ---------------------------------------------------------------

    def test_single_step_run_yields_the_maximum(self):
        assert edit_budget(0, 1, max_edits=4, min_edits=1) == 4

    def test_budget_never_drops_below_the_floor(self):
        assert all(edit_budget(t, 7, max_edits=3, min_edits=1) >= 1 for t in range(8))


# ---------------------------------------------------------------------------
# apply_patches
# ---------------------------------------------------------------------------


class TestSmuggledFenceMarkers:
    """Regression cover for a protection bypass found in adversarial review.

    The document splitter normalized lone carriage returns into newlines, but
    the marker check normalized only CRLF. A patch carrying
    "START\\rhidden\\rEND" therefore looked like one harmless line at check
    time and became a real fence the next time the file was read, hiding the
    smuggled region from every later edit.
    """

    def test_a_crlf_smuggled_marker_is_rejected(self):
        patch = Patch("append", None, f"{FENCE_START}\r\nhidden\r\n{FENCE_END}")
        with pytest.raises(ProtectedSectionError):
            apply_patches("body\n", [patch], budget=1)

    def test_a_lone_carriage_return_smuggled_marker_is_rejected(self):
        patch = Patch("append", None, f"{FENCE_START}\rhidden\r{FENCE_END}")
        with pytest.raises(ProtectedSectionError):
            apply_patches("body\n", [patch], budget=1)

    def test_a_lone_carriage_return_start_marker_alone_is_rejected(self):
        patch = Patch("append", None, f"tail\r{FENCE_START}")
        with pytest.raises(ProtectedSectionError):
            apply_patches("body\n", [patch], budget=1)

    def test_ordinary_carriage_return_text_still_applies(self):
        """The fix must not reject text that merely contains a stray CR."""
        out = apply_patches("body\n", [Patch("append", None, "one\rtwo")], budget=1)
        assert out == "body\none\ntwo\n"


class TestMalformedPatchFields:
    """A patch is agent-authored JSON, so wrong field types are expected."""

    def test_a_non_string_text_is_a_patch_shape_error(self):
        with pytest.raises(PatchShapeError):
            apply_patches("body\n", [Patch("append", None, 42)], budget=1)

    def test_a_non_string_anchor_is_a_patch_shape_error(self):
        with pytest.raises(PatchShapeError):
            apply_patches("alpha\n", [Patch("replace", 7, "x")], budget=1)

    def test_a_non_string_op_is_a_patch_shape_error(self):
        with pytest.raises(PatchShapeError):
            apply_patches("body\n", [Patch(3, None, "x")], budget=1)


class TestApplyPatches:
    def test_append_adds_to_the_end(self):
        out = apply_patches("line one\n", [Patch("append", None, "line two")], budget=1)
        assert out == "line one\nline two\n"

    def test_insert_after_places_text_below_the_anchor(self):
        doc = "alpha\nbeta\ngamma\n"
        out = apply_patches(doc, [Patch("insert_after", "beta", "inserted")], budget=1)
        assert out == "alpha\nbeta\ninserted\ngamma\n"

    def test_replace_swaps_the_anchor_line(self):
        doc = "alpha\nbeta\ngamma\n"
        out = apply_patches(doc, [Patch("replace", "beta", "BETA")], budget=1)
        assert out == "alpha\nBETA\ngamma\n"

    def test_delete_removes_the_anchor_line(self):
        doc = "alpha\nbeta\ngamma\n"
        out = apply_patches(doc, [Patch("delete", "beta", None)], budget=1)
        assert out == "alpha\ngamma\n"

    def test_applies_several_patches_in_one_pass(self):
        doc = "alpha\nbeta\ngamma\n"
        patches = [Patch("replace", "alpha", "ALPHA"), Patch("delete", "gamma", None)]
        assert apply_patches(doc, patches, budget=2) == "ALPHA\nbeta\n"

    def test_multiline_patch_text_is_inserted_whole(self):
        doc = "alpha\nbeta\n"
        out = apply_patches(doc, [Patch("insert_after", "alpha", "one\ntwo")], budget=1)
        assert out == "alpha\none\ntwo\nbeta\n"

    def test_empty_patch_list_returns_the_document_unchanged(self):
        doc = "alpha\nbeta\n"
        assert apply_patches(doc, [], budget=3) == doc

    def test_anchor_matching_ignores_surrounding_whitespace(self):
        doc = "alpha\n   beta   \ngamma\n"
        out = apply_patches(doc, [Patch("replace", "beta", "BETA")], budget=1)
        assert out == "alpha\nBETA\ngamma\n"

    def test_later_patch_can_anchor_on_text_an_earlier_patch_added(self):
        doc = "alpha\n"
        patches = [Patch("append", None, "beta"), Patch("replace", "beta", "BETA")]
        assert apply_patches(doc, patches, budget=2) == "alpha\nBETA\n"

    # -- budget -------------------------------------------------------------

    def test_refuses_more_patches_than_the_budget(self):
        patches = [Patch("append", None, "a"), Patch("append", None, "b")]
        with pytest.raises(BudgetExceededError, match="2"):
            apply_patches("doc\n", patches, budget=1)

    def test_budget_exactly_met_is_allowed(self):
        patches = [Patch("append", None, "a"), Patch("append", None, "b")]
        assert apply_patches("doc\n", patches, budget=2) == "doc\na\nb\n"

    def test_rejects_negative_budget(self):
        with pytest.raises(ValueError, match="budget"):
            apply_patches("doc\n", [], budget=-1)

    # -- anchors ------------------------------------------------------------

    def test_refuses_an_anchor_that_is_not_present(self):
        with pytest.raises(AnchorNotFoundError, match="nowhere"):
            apply_patches("alpha\n", [Patch("replace", "nowhere", "x")], budget=1)

    def test_refuses_an_ambiguous_anchor(self):
        doc = "dup\nmiddle\ndup\n"
        with pytest.raises(AmbiguousAnchorError, match="2"):
            apply_patches(doc, [Patch("replace", "dup", "x")], budget=1)

    def test_ambiguity_is_detected_after_earlier_patches_apply(self):
        doc = "alpha\nbeta\n"
        patches = [Patch("append", None, "beta"), Patch("replace", "beta", "x")]
        with pytest.raises(AmbiguousAnchorError):
            apply_patches(doc, patches, budget=2)

    # -- patch shape --------------------------------------------------------

    def test_rejects_an_unknown_operation(self):
        with pytest.raises(PatchShapeError, match="rewrite"):
            apply_patches("doc\n", [Patch("rewrite", None, "x")], budget=1)

    @pytest.mark.parametrize("op", ["insert_after", "replace", "delete"])
    def test_rejects_a_missing_anchor(self, op):
        with pytest.raises(PatchShapeError, match="anchor"):
            apply_patches("doc\n", [Patch(op, None, "x")], budget=1)

    @pytest.mark.parametrize("op", ["insert_after", "replace", "append"])
    def test_rejects_missing_text(self, op):
        anchor = None if op == "append" else "doc"
        with pytest.raises(PatchShapeError, match="text"):
            apply_patches("doc\n", [Patch(op, anchor, None)], budget=1)

    def test_rejects_a_blank_anchor(self):
        with pytest.raises(PatchShapeError, match="anchor"):
            apply_patches("doc\n", [Patch("replace", "   ", "x")], budget=1)

    def test_delete_ignores_a_text_field(self):
        doc = "alpha\nbeta\n"
        assert apply_patches(doc, [Patch("delete", "beta", "ignored")], budget=1) == "alpha\n"

    # -- protected fence ----------------------------------------------------

    def test_refuses_to_replace_a_line_inside_the_fence(self):
        doc = f"alpha\n{FENCE_START}\nrail\n{FENCE_END}\nomega\n"
        with pytest.raises(ProtectedSectionError, match="rail"):
            apply_patches(doc, [Patch("replace", "rail", "x")], budget=1)

    def test_refuses_to_delete_a_line_inside_the_fence(self):
        doc = f"alpha\n{FENCE_START}\nrail\n{FENCE_END}\nomega\n"
        with pytest.raises(ProtectedSectionError):
            apply_patches(doc, [Patch("delete", "rail", None)], budget=1)

    def test_refuses_to_insert_inside_the_fence(self):
        doc = f"alpha\n{FENCE_START}\nrail\n{FENCE_END}\nomega\n"
        with pytest.raises(ProtectedSectionError):
            apply_patches(doc, [Patch("insert_after", "rail", "x")], budget=1)

    def test_refuses_to_anchor_on_the_fence_markers(self):
        doc = f"alpha\n{FENCE_START}\nrail\n{FENCE_END}\nomega\n"
        with pytest.raises(ProtectedSectionError):
            apply_patches(doc, [Patch("delete", FENCE_START, None)], budget=1)

    def test_allows_edits_outside_the_fence(self):
        doc = f"alpha\n{FENCE_START}\nrail\n{FENCE_END}\nomega\n"
        out = apply_patches(doc, [Patch("replace", "omega", "OMEGA")], budget=1)
        assert "rail" in out
        assert out.endswith("OMEGA\n")

    def test_append_lands_outside_a_closed_fence(self):
        doc = f"alpha\n{FENCE_START}\nrail\n{FENCE_END}\n"
        out = apply_patches(doc, [Patch("append", None, "added")], budget=1)
        assert out.endswith(f"{FENCE_END}\nadded\n")

    def test_refuses_to_append_into_an_unclosed_fence(self):
        doc = f"alpha\n{FENCE_START}\nrail\n"
        with pytest.raises(ProtectedSectionError, match="unclosed"):
            apply_patches(doc, [Patch("append", None, "added")], budget=1)

    def test_refuses_a_document_with_an_unbalanced_fence(self):
        doc = f"alpha\nrail\n{FENCE_END}\n"
        with pytest.raises(ProtectedSectionError, match="unbalanced"):
            apply_patches(doc, [Patch("replace", "rail", "x")], budget=1)

    def test_refuses_a_nested_fence(self):
        doc = f"{FENCE_START}\n{FENCE_START}\nrail\n{FENCE_END}\n{FENCE_END}\n"
        with pytest.raises(ProtectedSectionError, match="nested"):
            apply_patches(doc, [Patch("append", None, "x")], budget=1)

    def test_protects_a_second_fence_block(self):
        doc = (
            f"a\n{FENCE_START}\nfirst\n{FENCE_END}\n"
            f"b\n{FENCE_START}\nsecond\n{FENCE_END}\nc\n"
        )
        with pytest.raises(ProtectedSectionError, match="second"):
            apply_patches(doc, [Patch("replace", "second", "x")], budget=1)

    def test_patch_text_may_not_smuggle_in_a_fence_marker(self):
        with pytest.raises(ProtectedSectionError, match="marker"):
            apply_patches("alpha\n", [Patch("append", None, FENCE_START)], budget=1)

    # -- edge ---------------------------------------------------------------

    def test_empty_document_accepts_an_append(self):
        assert apply_patches("", [Patch("append", None, "first")], budget=1) == "first\n"

    def test_document_without_a_trailing_newline_is_normalized(self):
        assert apply_patches("alpha", [Patch("append", None, "beta")], budget=1) == "alpha\nbeta\n"

    def test_crlf_line_endings_are_handled(self):
        out = apply_patches("alpha\r\nbeta\r\n", [Patch("delete", "beta", None)], budget=1)
        assert out == "alpha\n"

    def test_deleting_the_only_line_yields_an_empty_document(self):
        assert apply_patches("only\n", [Patch("delete", "only", None)], budget=1) == ""


# ---------------------------------------------------------------------------
# score
# ---------------------------------------------------------------------------


class TestMcnemarExact:
    """One-sided exact McNemar test on the paired held-out outcomes.

    The gate compares the same task ids before and after an edit, so the two
    scores are paired, not independent. Tasks whose outcome did not move carry
    no information about the edit. Only the discordant pairs do: b tasks that
    went fail to pass, c that went pass to fail. Under the null that the edit
    is neutral, b is Binomial(b + c, 0.5), and the one-sided p is
    P(X >= b). Exact, so it stays valid at the small task counts this repo's
    eval sets actually have.
    """

    def test_a_clean_sweep_of_three_is_one_eighth(self):
        inc = {"A": False, "B": False, "C": False}
        cand = {"A": True, "B": True, "C": True}
        b, c, p = mcnemar_exact(inc, cand, ["A", "B", "C"])
        assert (b, c) == (3, 0)
        assert p == pytest.approx(0.125)

    def test_no_discordant_pairs_is_p_one(self):
        """Nothing moved, so the data cannot argue against the null."""
        inc = {"A": True, "B": False}
        cand = {"A": True, "B": False}
        b, c, p = mcnemar_exact(inc, cand, ["A", "B"])
        assert (b, c) == (0, 0)
        assert p == 1.0

    def test_a_regression_is_not_significant(self):
        inc = {"A": True, "B": True}
        cand = {"A": False, "B": False}
        b, c, p = mcnemar_exact(inc, cand, ["A", "B"])
        assert (b, c) == (0, 2)
        assert p == 1.0

    def test_one_flip_each_way_is_p_one(self):
        inc = {"A": True, "B": False}
        cand = {"A": False, "B": True}
        b, c, p = mcnemar_exact(inc, cand, ["A", "B"])
        assert (b, c) == (1, 1)
        assert p == pytest.approx(0.75)

    def test_five_clean_flips_clears_the_conventional_floor(self):
        ids = ["A", "B", "C", "D", "E"]
        inc = dict.fromkeys(ids, False)
        cand = dict.fromkeys(ids, True)
        b, c, p = mcnemar_exact(inc, cand, ids)
        assert (b, c) == (5, 0)
        assert p == pytest.approx(0.03125)
        assert p <= 0.05

    def test_three_flips_cannot_clear_the_conventional_floor(self):
        """Documents the real resolution limit of a 3-task held-out group."""
        ids = ["A", "B", "C"]
        b, c, p = mcnemar_exact(dict.fromkeys(ids, False), dict.fromkeys(ids, True), ids)
        assert p > 0.05

    def test_unchanged_tasks_do_not_dilute_the_result(self):
        inc = {"A": False, "B": True, "C": True, "D": True}
        cand = {"A": True, "B": True, "C": True, "D": True}
        b, c, p = mcnemar_exact(inc, cand, ["A", "B", "C", "D"])
        assert (b, c) == (1, 0)
        assert p == pytest.approx(0.5)

    def test_an_empty_task_list_is_p_one(self):
        assert mcnemar_exact({}, {}, []) == (0, 0, 1.0)

    def _all_flip(self, n):
        ids = [f"t{i}" for i in range(n)]
        return mcnemar_exact(dict.fromkeys(ids, False), dict.fromkeys(ids, True), ids)

    def test_a_p_that_underflows_the_float_stays_above_zero(self):
        """`tail / 2**n` underflows at n=1075, and zero is never the true value.

        The tail always contains the k=b term, so `tail` is at least 1 and the
        exact probability is strictly positive for every input. Only the float
        conversion loses it. Reporting 0.0 mattered because `--max-p 0` is the
        strictest bar the flag can express, and `0.0 <= 0` reads as satisfied,
        so the strictest possible bar accepted rather than rejected.
        """
        _, _, p = self._all_flip(1075)
        assert p > 0.0

    def test_the_underflow_floor_is_the_smallest_positive_float(self):
        _, _, p = self._all_flip(1075)
        assert p == math.nextafter(0.0, 1.0)

    def test_one_below_the_underflow_boundary_is_untouched(self):
        """n=1074 still converts exactly, so the clamp must not reach it."""
        _, _, p = self._all_flip(1074)
        assert p == 5e-324

    def test_a_p_well_inside_the_float_range_is_untouched(self):
        _, _, p = self._all_flip(1000)
        assert p == pytest.approx(9.332636185032189e-302)

    def test_the_strictest_expressible_bar_now_rejects(self):
        """The behaviour the clamp exists for, stated as the caller sees it."""
        _, _, p = self._all_flip(1100)
        assert not p <= 0

    def test_a_missing_incumbent_result_raises(self):
        with pytest.raises(MissingResultError):
            mcnemar_exact({}, {"A": True}, ["A"])

    def test_a_missing_candidate_result_raises(self):
        with pytest.raises(MissingResultError):
            mcnemar_exact({"A": True}, {}, ["A"])


class TestScore:
    def test_counts_the_passing_fraction(self):
        results = {"A": True, "B": False, "C": True, "D": True}
        assert score(results, ["A", "B", "C", "D"]) == 0.75

    def test_scores_only_the_requested_ids(self):
        results = {"A": True, "B": False, "C": False}
        assert score(results, ["A"]) == 1.0

    def test_all_failing_scores_zero(self):
        assert score({"A": False, "B": False}, ["A", "B"]) == 0.0

    def test_refuses_a_missing_result(self):
        """A silently-absent task must not be scored as anything."""
        with pytest.raises(MissingResultError, match="B"):
            score({"A": True}, ["A", "B"])

    def test_missing_result_error_lists_every_gap(self):
        with pytest.raises(MissingResultError) as excinfo:
            score({"A": True}, ["A", "B", "C"])
        assert "B" in str(excinfo.value)
        assert "C" in str(excinfo.value)

    def test_rejects_an_empty_id_list(self):
        with pytest.raises(ValueError, match="at least one task"):
            score({"A": True}, [])

    def test_rejects_a_non_boolean_result(self):
        with pytest.raises(TypeError, match="bool"):
            score({"A": 1}, ["A"])

    def test_duplicate_ids_do_not_double_count(self):
        assert score({"A": True, "B": False}, ["A", "B", "A"]) == 0.5


# ---------------------------------------------------------------------------
# gate
# ---------------------------------------------------------------------------


class TestGuardRefusal:
    """The two refusals a caller can decide before spending the held-out group.

    A gate that scores first and refuses second has already read the sel group,
    which is the exact cost the refusal exists to avoid. Asking first makes the
    refusal free.
    """

    def test_a_clean_call_is_permitted(self):
        assert guard_refusal(sel_consultations=1, max_consultations=5) is None

    def test_no_bookkeeping_at_all_is_permitted(self):
        assert guard_refusal() is None

    def test_a_moved_fingerprint_refuses(self):
        reason = guard_refusal(split_fingerprint="a", incumbent_fingerprint="b")
        assert reason is not None
        assert "fingerprint" in reason

    def test_matching_fingerprints_are_permitted(self):
        assert guard_refusal(split_fingerprint="a", incumbent_fingerprint="a") is None

    def test_an_unknown_incumbent_fingerprint_cannot_refuse(self):
        assert guard_refusal(split_fingerprint="a", incumbent_fingerprint=None) is None

    def test_an_exhausted_budget_refuses(self):
        reason = guard_refusal(sel_consultations=5, max_consultations=5)
        assert reason is not None
        assert "exhausted" in reason

    def test_the_fingerprint_check_runs_first(self):
        reason = guard_refusal(
            sel_consultations=9,
            max_consultations=1,
            split_fingerprint="a",
            incumbent_fingerprint="b",
        )
        assert reason is not None
        assert "fingerprint" in reason


class TestGateRegressionGuard:
    """An aggregate win must not hide a held-out task that stopped passing.

    ADR-057 blocks every pass-to-fail transition rather than netting them
    against gains. An aggregate-only gate accepts an edit that fixes two tasks
    and breaks one, which is exactly the trade ADR-057 refuses. The gate takes
    the discordant counts so it can refuse on the broken task.
    """

    def test_rejects_a_net_win_that_breaks_a_passing_task(self):
        result = gate(0.8, 0.6, discordant_loss=1)
        assert result.decision == "REJECT"
        assert "regress" in result.reason

    def test_names_how_many_tasks_broke(self):
        result = gate(0.8, 0.6, discordant_loss=2)
        assert "2" in result.reason

    def test_accepts_a_win_with_no_regression(self):
        assert gate(0.8, 0.6, discordant_loss=0).decision == "ACCEPT"

    def test_defaults_to_no_regression_when_counts_are_unknown(self):
        """Per-task detail is optional, so the aggregate path must still work."""
        assert gate(0.8, 0.6).decision == "ACCEPT"

    def test_rejects_a_negative_discordant_loss(self):
        with pytest.raises(ValueError, match="discordant_loss"):
            gate(0.8, 0.6, discordant_loss=-1)

    def test_a_regression_still_counts_as_compared(self):
        """The scores were weighed, so the consultation was spent."""
        assert gate(0.8, 0.6, discordant_loss=1).compared is True

    def test_there_is_no_override_for_a_broken_task(self):
        """This test used to assert an `allow_regressions` bypass existed.

        ADR-057 says its gate "has no mechanism to accept a justified
        regression". A bypass here was a weaker rule wearing the same name,
        and an agent driving the loop could set it with no human ever seeing
        the broken task. The parameter is gone; a net gain never buys one.
        """
        with pytest.raises(TypeError):
            gate(0.8, 0.6, discordant_loss=1, allow_regressions=True)
        assert gate(0.8, 0.6, discordant_loss=1).decision == "REJECT"

    def test_the_fingerprint_guard_still_wins_over_the_regression_guard(self):
        result = gate(
            0.8,
            0.6,
            discordant_loss=1,
            split_fingerprint="a",
            incumbent_fingerprint="b",
        )
        assert result.compared is False
        assert "fingerprint" in result.reason


class TestGate:
    def test_a_strict_win_is_accepted(self):
        assert gate(0.8, 0.6).decision == "ACCEPT"

    def test_a_tie_is_rejected(self):
        result = gate(0.6, 0.6)
        assert result.decision == "REJECT"
        assert "tie" in result.reason

    def test_a_regression_is_rejected(self):
        result = gate(0.4, 0.6)
        assert result.decision == "REJECT"
        assert "regress" in result.reason

    def test_carries_both_scores(self):
        result = gate(0.8, 0.6)
        assert result.candidate == 0.8
        assert result.incumbent == 0.6

    def test_a_hair_above_the_incumbent_still_wins(self):
        assert gate(0.6000001, 0.6).decision == "ACCEPT"

    def test_reports_how_many_times_the_split_was_consulted(self):
        assert gate(0.8, 0.6, sel_consultations=4).sel_consultations == 4

    def test_a_scored_comparison_reports_compared(self):
        assert gate(0.8, 0.6).compared is True

    def test_a_tie_still_counts_as_a_comparison(self):
        assert gate(0.6, 0.6).compared is True

    def test_a_regression_still_counts_as_a_comparison(self):
        assert gate(0.4, 0.6).compared is True

    def test_a_fingerprint_refusal_did_not_compare(self):
        """No comparison happened, so the caller must not burn a consultation."""
        result = gate(0.9, 0.1, split_fingerprint="a", incumbent_fingerprint="b")
        assert result.decision == "REJECT"
        assert result.compared is False

    def test_an_exhausted_refusal_did_not_compare(self):
        result = gate(0.9, 0.1, sel_consultations=3, max_consultations=3)
        assert result.decision == "REJECT"
        assert result.compared is False

    def test_refuses_once_the_split_is_exhausted(self):
        """Gating N times on one split selects on it N times."""
        result = gate(0.9, 0.1, sel_consultations=10, max_consultations=10)
        assert result.decision == "REJECT"
        assert "exhausted" in result.reason

    def test_allows_the_last_consultation_before_the_limit(self):
        assert gate(0.9, 0.1, sel_consultations=9, max_consultations=10).decision == "ACCEPT"

    def test_unlimited_consultations_by_default(self):
        assert gate(0.9, 0.1, sel_consultations=999).decision == "ACCEPT"

    def test_refuses_a_changed_split_fingerprint(self):
        """Adding fixtures after a loss must not resurrect the incumbent."""
        result = gate(0.9, 0.1, split_fingerprint="abc", incumbent_fingerprint="xyz")
        assert result.decision == "REJECT"
        assert "fingerprint" in result.reason

    def test_matching_fingerprints_pass_through(self):
        result = gate(0.9, 0.1, split_fingerprint="abc", incumbent_fingerprint="abc")
        assert result.decision == "ACCEPT"

    @pytest.mark.parametrize("value", [-0.1, 1.1])
    def test_rejects_an_out_of_range_candidate(self, value):
        with pytest.raises(ValueError, match="candidate"):
            gate(value, 0.5)

    @pytest.mark.parametrize("value", [-0.1, 1.1])
    def test_rejects_an_out_of_range_incumbent(self, value):
        with pytest.raises(ValueError, match="incumbent"):
            gate(0.5, value)

    def test_rejects_negative_consultations(self):
        with pytest.raises(ValueError, match="sel_consultations"):
            gate(0.8, 0.6, sel_consultations=-1)

    def test_rejects_a_non_positive_consultation_limit(self):
        with pytest.raises(ValueError, match="max_consultations"):
            gate(0.8, 0.6, max_consultations=0)


# ---------------------------------------------------------------------------
# patch_fingerprint / buffer_contains
# ---------------------------------------------------------------------------


class TestPatchFingerprint:
    def test_same_patches_fingerprint_alike(self):
        a = [Patch("replace", "x", "y")]
        b = [Patch("replace", "x", "y")]
        assert patch_fingerprint(a) == patch_fingerprint(b)

    def test_order_changes_the_fingerprint(self):
        """Patches apply sequentially, so order is part of the edit's identity.

        Appending "one" then "two" produces a different document from "two"
        then "one". Treating them as the same edit would let one rejection ban
        the other, and a banned edit can never be re-proposed.
        """
        a = [Patch("append", None, "one"), Patch("append", None, "two")]
        b = [Patch("append", None, "two"), Patch("append", None, "one")]
        assert patch_fingerprint(a) != patch_fingerprint(b)

    def test_whitespace_reflow_changes_the_fingerprint(self):
        """Whitespace is content here: a newline splits one line into two."""
        a = [Patch("replace", "x", "hello  world")]
        b = [Patch("replace", "x", "hello\n world ")]
        assert patch_fingerprint(a) != patch_fingerprint(b)

    def test_line_endings_alone_do_not_change_the_fingerprint(self):
        """CRLF is transport, not content, so it is normalized away."""
        a = [Patch("replace", "x", "one\r\ntwo")]
        b = [Patch("replace", "x", "one\ntwo")]
        assert patch_fingerprint(a) == patch_fingerprint(b)

    def test_a_lone_carriage_return_is_normalized_too(self):
        a = [Patch("replace", "x", "one\rtwo")]
        b = [Patch("replace", "x", "one\ntwo")]
        assert patch_fingerprint(a) == patch_fingerprint(b)

    def test_different_text_changes_the_fingerprint(self):
        a = [Patch("replace", "x", "one")]
        b = [Patch("replace", "x", "two")]
        assert patch_fingerprint(a) != patch_fingerprint(b)

    def test_different_op_changes_the_fingerprint(self):
        a = [Patch("replace", "x", "one")]
        b = [Patch("insert_after", "x", "one")]
        assert patch_fingerprint(a) != patch_fingerprint(b)

    def test_different_anchor_changes_the_fingerprint(self):
        a = [Patch("replace", "x", "one")]
        b = [Patch("replace", "y", "one")]
        assert patch_fingerprint(a) != patch_fingerprint(b)

    def test_rejects_an_empty_patch_list(self):
        with pytest.raises(ValueError, match="at least one patch"):
            patch_fingerprint([])

    def test_fingerprint_is_a_hex_digest(self):
        value = patch_fingerprint([Patch("append", None, "x")])
        assert len(value) == 64
        assert all(char in "0123456789abcdef" for char in value)


class TestBufferContains:
    def test_finds_a_previously_rejected_edit(self):
        patches = [Patch("replace", "x", "y")]
        buffer = [{"fingerprint": patch_fingerprint(patches), "note": "lost"}]
        assert buffer_contains(buffer, patches) is True

    def test_reports_a_novel_edit(self):
        buffer = [{"fingerprint": patch_fingerprint([Patch("append", None, "other")])}]
        assert buffer_contains(buffer, [Patch("replace", "x", "y")]) is False

    def test_an_empty_buffer_contains_nothing(self):
        assert buffer_contains([], [Patch("append", None, "x")]) is False

    def test_does_not_match_across_reordering(self):
        """Reordered patches build a different document, so they are a different edit."""
        stored = [Patch("append", None, "one"), Patch("append", None, "two")]
        buffer = [{"fingerprint": patch_fingerprint(stored)}]
        reordered = [Patch("append", None, "two"), Patch("append", None, "one")]
        assert buffer_contains(buffer, reordered) is False

    def test_ignores_buffer_entries_without_a_fingerprint(self):
        buffer = [{"note": "malformed"}, {"fingerprint": None}]
        assert buffer_contains(buffer, [Patch("append", None, "x")]) is False

    def test_rejects_an_empty_patch_list(self):
        with pytest.raises(ValueError, match="at least one patch"):
            buffer_contains([], [])


class TestSplitFingerprint:
    """The fingerprint has to be recomputable from a split file's own contents.

    Before this existed, the only drift check compared a split file's stored
    fingerprint against a value the caller passed on the command line. A caller
    who omitted the flag got no check, and a stored fingerprint was trusted
    even when the group membership beside it had been edited. Both holes close
    only if a reader can recompute the value instead of trusting it.
    """

    def test_matches_what_split_tasks_recorded(self):
        ids = _ids(10)
        split = split_tasks(ids, seed="s", sel_ratio=0.4, test_ratio=0.2)
        assert (
            split_fingerprint(ids, seed="s", sel_ratio=0.4, test_ratio=0.2)
            == split.fingerprint
        )

    def test_numeric_and_string_ratios_fingerprint_identically(self):
        ids = _ids(10)
        assert split_fingerprint(ids, seed="s", sel_ratio=0.4) == split_fingerprint(
            ids, seed="s", sel_ratio="0.4"
        )

    def test_task_order_does_not_matter(self):
        ids = _ids(6)
        assert split_fingerprint(ids, seed="s", sel_ratio=0.5) == split_fingerprint(
            list(reversed(ids)), seed="s", sel_ratio=0.5
        )

    def test_an_added_task_changes_it(self):
        ids = _ids(6)
        assert split_fingerprint(ids, seed="s", sel_ratio=0.5) != split_fingerprint(
            [*ids, "extra"], seed="s", sel_ratio=0.5
        )

    def test_a_different_seed_changes_it(self):
        ids = _ids(6)
        assert split_fingerprint(ids, seed="a", sel_ratio=0.5) != split_fingerprint(
            ids, seed="b", sel_ratio=0.5
        )

    def test_a_different_ratio_changes_it(self):
        ids = _ids(6)
        assert split_fingerprint(ids, seed="s", sel_ratio=0.5) != split_fingerprint(
            ids, seed="s", sel_ratio=0.4
        )
        assert split_fingerprint(ids, seed="s", sel_ratio=0.5) != split_fingerprint(
            ids, seed="s", sel_ratio=0.5, test_ratio=0.2
        )

    def test_an_empty_task_set_still_hashes(self):
        """It is a hash, not a validator. split_tasks owns the size rules."""
        assert len(split_fingerprint([], seed="s", sel_ratio=0.5)) == 64


class TestGuardRefusalValidatesItsOwnCap:
    """A nonsense cap must be refused, not silently mean "always exhausted".

    `gate()` rejects a cap below one, but callers reach `guard_refusal` first
    so they can ask before scoring anything. Without the same check there, a
    typo like `--max-consultations -1` reads as a permanently exhausted budget
    and looks exactly like legitimate discipline.
    """

    @pytest.mark.parametrize("cap", [0, -1, -100])
    def test_a_cap_below_one_is_refused(self, cap):
        with pytest.raises(ValueError, match="must be positive"):
            guard_refusal(sel_consultations=0, max_consultations=cap)

    def test_a_positive_cap_is_accepted(self):
        assert guard_refusal(sel_consultations=0, max_consultations=1) is None

    def test_no_cap_is_accepted(self):
        assert guard_refusal(sel_consultations=99, max_consultations=None) is None

    @pytest.mark.parametrize("spent", [-1, -7])
    def test_a_negative_spend_is_refused(self, spent):
        """A negative count is a corrupt ledger, not an unspent budget.

        Reading one as "less than the cap" would hand back consultations the
        group already spent, which is the budget defect this whole mechanism
        exists to prevent, arriving through arithmetic instead of through a
        flag.
        """
        with pytest.raises(ValueError, match="must be non-negative"):
            guard_refusal(sel_consultations=spent, max_consultations=3)

    def test_a_zero_spend_is_accepted(self):
        assert guard_refusal(sel_consultations=0, max_consultations=3) is None


class TestSignificanceCanBeEnforcedNotJustReported:
    """`max_p` turns the reported McNemar tail into a refusal.

    Motivated by a live run (see scripts/eval/README.md, "What a live run
    measured"): scoring the same rule text twice flipped 5 of 24 tasks, and
    the held-out group moved 6/10 -> 7/10 with no input change at all. A
    strictly-greater rule alone therefore accepts scorer variance. `p_value`
    was already computed and printed; it just could not refuse anything.

    Default stays None so a small held-out group, which cannot reach a
    conventional floor, is still informative rather than unpassable.
    """

    def test_a_gain_whose_tail_exceeds_the_bar_is_refused(self):
        result = gate(0.8, 0.6, p_value=0.25, max_p=0.05, max_consultations=1)
        assert result.decision == "REJECT"
        assert "0.25" in result.reason and "0.05" in result.reason

    def test_the_same_gain_is_accepted_when_no_bar_is_set(self):
        assert gate(0.8, 0.6, p_value=0.25).decision == "ACCEPT"

    def test_a_gain_whose_tail_clears_the_bar_is_accepted(self):
        assert (
            gate(0.8, 0.6, p_value=0.002, max_p=0.05, max_consultations=5).decision == "ACCEPT"
        )

    def test_p_equal_to_the_corrected_bar_passes(self):
        """The bar is a maximum, so equality is inside it, not outside."""
        assert gate(0.8, 0.6, p_value=0.01, max_p=0.05, max_consultations=5).decision == "ACCEPT"

    def test_a_bar_with_no_p_value_refuses_to_run(self):
        """Fail closed. An unknown tail is not evidence that it clears the bar."""
        with pytest.raises(ValueError, match="p_value"):
            gate(0.8, 0.6, max_p=0.05, max_consultations=5)

    def test_a_regression_still_outranks_the_significance_bar(self):
        """Both refuse; the broken task is the one worth naming first."""
        result = gate(
            0.8, 0.6, discordant_loss=1, p_value=0.9, max_p=0.05, max_consultations=1
        )
        assert result.decision == "REJECT"
        assert "regressed" in result.reason

    def test_a_tie_is_still_a_tie_under_a_bar(self):
        result = gate(0.6, 0.6, p_value=0.001, max_p=0.05, max_consultations=1)
        assert result.decision == "REJECT"
        assert "tie" in result.reason

    @pytest.mark.parametrize("bad", [-0.1, 1.1, 2.0])
    def test_a_bar_outside_the_unit_interval_is_refused(self, bad):
        with pytest.raises(ValueError, match="max_p must be in"):
            gate(0.8, 0.6, p_value=0.25, max_p=bad, max_consultations=1)

    @pytest.mark.parametrize("bad", [-0.1, 1.1])
    def test_a_p_value_outside_the_unit_interval_is_refused(self, bad):
        with pytest.raises(ValueError, match="p_value must be in"):
            gate(0.8, 0.6, p_value=bad, max_p=0.05, max_consultations=1)

    @pytest.mark.parametrize("edge", [0.0, 1.0])
    def test_the_unit_interval_endpoints_are_legal(self, edge):
        gate(0.8, 0.6, p_value=edge, max_p=1.0, max_consultations=1)
        gate(0.8, 0.6, p_value=0.0, max_p=edge, max_consultations=1)

    def test_a_bar_of_zero_refuses_every_nonzero_tail(self):
        """0.0 is a legal bar and means only a certain result passes."""
        assert (
            gate(0.8, 0.6, p_value=0.001, max_p=0.0, max_consultations=1).decision == "REJECT"
        )
        assert (
            gate(0.8, 0.6, p_value=0.0, max_p=0.0, max_consultations=1).decision == "ACCEPT"
        )

    def test_the_bar_never_rescues_a_guard_refusal(self):
        """A moved fingerprint is not comparable, significant or not."""
        result = gate(
            0.8,
            0.6,
            split_fingerprint="a",
            incumbent_fingerprint="b",
            p_value=0.0,
            max_p=0.05,
            max_consultations=1,
        )
        assert result.decision == "REJECT"
        assert result.compared is False


class TestOneBarSpentFiveTimesIsNotThatBar:
    """Round fourteen: a per-comparison threshold does not bound a family.

    An adversarial review pointed out that the loop's own documented recipe
    permits five consultations, and that applying 0.05 independently to each
    does not leave the family at 0.05. Round eighteen sharpened the figure: the
    dependence-agnostic union bound is 5 * 0.05 = 0.25, while the exact
    1 - 0.95**5, about 0.226, assumes the five comparisons are independent,
    which five looks at one selection group are not. The bar an operator asks
    for is the one they believe governs the run, so it is read as the family
    bar and divided across the declared budget by Bonferroni, which holds under
    arbitrary dependence between the comparisons. Round nineteen added the
    missing half: that guarantee still assumes each per-comparison p-value is
    valid on its own, and this harness's rule-path null control reproduced two
    gains under a byte-identical no-op, so its outcomes are correlated and that
    assumption is not free.
    """

    def test_the_bar_is_divided_across_the_declared_budget(self):
        """0.05 over five consultations is 0.01 per comparison."""
        assert (
            gate(0.8, 0.6, p_value=0.02, max_p=0.05, max_consultations=5).decision == "REJECT"
        )
        assert gate(0.8, 0.6, p_value=0.02, max_p=0.05, max_consultations=2).decision == "ACCEPT"

    def test_the_refusal_names_both_the_family_bar_and_the_corrected_one(self):
        result = gate(0.8, 0.6, p_value=0.02, max_p=0.05, max_consultations=5)
        assert "0.05" in result.reason
        assert "0.01" in result.reason

    def test_a_single_consultation_budget_leaves_the_bar_alone(self):
        """With a family of one there is nothing to correct."""
        assert gate(0.8, 0.6, p_value=0.05, max_p=0.05, max_consultations=1).decision == "ACCEPT"
        assert (
            gate(0.8, 0.6, p_value=0.051, max_p=0.05, max_consultations=1).decision == "REJECT"
        )

    def test_a_bar_without_a_declared_budget_refuses_to_run(self):
        """An undeclared family size cannot be corrected for, so fail closed."""
        with pytest.raises(ValueError, match="max_consultations"):
            gate(0.8, 0.6, p_value=0.01, max_p=0.05)

    def test_no_bar_still_needs_no_budget(self):
        """The correction is only owed when a bar was asked for."""
        assert gate(0.8, 0.6, p_value=0.9).decision == "ACCEPT"

    def test_the_correction_cannot_be_escaped_by_raising_the_budget(self):
        """A larger budget buys more looks, each held to a stricter bar."""
        strict = gate(0.8, 0.6, p_value=0.02, max_p=0.05, max_consultations=100)
        assert strict.decision == "REJECT"


class TestBothBarsAreLabeledInTheRefusal:
    """Round eighteen: two bare numbers in one sentence do not say which is which.

    A reviewer read "above the 0.01 this comparison is allowed" as a sentence
    missing a word, and could not tell the family bar from the value it had been
    corrected to. Both numbers were already present; the round-fourteen test
    asserted only that. Presence is not legibility: the operator reading a
    refusal has to know which number they asked for and which one the correction
    produced, because only the second explains why this p value lost.
    """

    def test_each_number_carries_the_label_that_says_which_bar_it_is(self):
        result = gate(0.8, 0.6, p_value=0.02, max_p=0.05, max_consultations=5)
        assert result.decision == "REJECT"
        assert "per-comparison bar of 0.01" in result.reason
        assert "0.05 family bar" in result.reason

    def test_the_refusal_shows_the_arithmetic_that_produced_the_corrected_bar(self):
        """Naming both bars is not enough; the reader must be able to check them."""
        result = gate(0.8, 0.6, p_value=0.02, max_p=0.05, max_consultations=5)
        assert "divided across 5 consultation(s)" in result.reason

    def test_the_ambiguous_fragment_is_gone(self):
        """Negative control: the exact phrasing the reviewer could not parse."""
        result = gate(0.8, 0.6, p_value=0.02, max_p=0.05, max_consultations=5)
        assert "this comparison is allowed" not in result.reason

    def test_a_family_of_one_still_labels_both_bars_and_states_the_division(self):
        """Edge: dividing by one is a no-op, so both numbers are equal.

        The sentence has to stay honest and checkable when the correction
        changes nothing, rather than dropping the arithmetic and leaving the
        reader unable to tell a corrected bar from an uncorrected one.
        """
        result = gate(0.8, 0.6, p_value=0.051, max_p=0.05, max_consultations=1)
        assert result.decision == "REJECT"
        assert "per-comparison bar of 0.05" in result.reason
        assert "0.05 family bar" in result.reason
        assert "divided across 1 consultation(s)" in result.reason


class TestTheBudgetRefusalOnlyAdvisesMovesTheCliAllows:
    """Round twenty: the refusal named an invocation the parser rejects.

    The exhausted-budget message ended "refresh the split or report on the
    test group". `score --group` accepts only "opt", so the second half sent
    an operator who had just run out of budget into a dead end that the CLI's
    own argument parser refuses statically.

    The fix removes the advice rather than implementing it. Widening the
    choice would hand the loop unmetered reads of the group held back as a
    final unbiased look, and "score --group opt refuses to read any other
    group" is listed in the README as a property enforced whether or not the
    optimizer cooperates. The methodological point behind the advice is sound
    and the tooling for a one-shot final read does not exist; that is a
    capability gap to file, not a string to keep true by weakening an enforced
    boundary.
    """

    def test_the_refusal_does_not_send_the_operator_to_the_test_group(self):
        reason = guard_refusal(sel_consultations=5, max_consultations=5)
        assert reason is not None
        assert "test group" not in reason

    def test_the_refusal_still_names_the_count_and_the_limit(self):
        """Control: making the advice honest must not drop the diagnosis."""
        reason = guard_refusal(sel_consultations=5, max_consultations=5)
        assert reason is not None
        assert "5" in reason
        assert "exhausted" in reason

    def test_the_refusal_still_names_a_move_the_operator_can_make(self):
        """A refusal that diagnoses without advising leaves the loop stuck."""
        reason = guard_refusal(sel_consultations=5, max_consultations=5)
        assert reason is not None
        assert "split" in reason

    def test_a_budget_with_room_left_is_still_silent(self):
        """Control: the wording change must not make the guard fire early."""
        assert guard_refusal(sel_consultations=4, max_consultations=5) is None


class TestDuplicateTaskIdsAreNamedWithoutRescanningTheList:
    """Duplicate detection is a refusal path, so it must be cheap to reach.

    `split_tasks` refuses duplicate ids because two tasks sharing a key are
    one task to every downstream mapping, and a smaller denominator reads as
    a higher score. Naming them cost `list.count` per element, which is
    quadratic: measured 1.16s at 10k ids, 4.59s at 20k, and 18.48s at 40k.

    A caller reaches this with `split --tasks` on a generated id list, so the
    cost lands on an operator who already made a mistake and is waiting to be
    told which one. The counting is one pass now; the message is unchanged.
    """

    def test_a_clean_list_still_splits(self):
        split = split_tasks([f"t{i}" for i in range(10)], seed="s")
        assert len(split.opt) + len(split.sel) + len(split.test) == 10

    def test_a_duplicate_is_still_refused(self):
        with pytest.raises(ValueError, match="duplicate task ids"):
            split_tasks(["a", "b", "a"], seed="s")

    def test_the_refusal_names_every_repeated_id_once_and_in_order(self):
        """Sorted and deduplicated, so the message is stable across runs."""
        with pytest.raises(ValueError) as excinfo:
            split_tasks(["b", "a", "b", "a", "b", "c"], seed="s")
        assert "duplicate task ids: a, b" in str(excinfo.value)

    def test_an_id_repeated_many_times_is_named_once(self):
        with pytest.raises(ValueError) as excinfo:
            split_tasks(["x"] * 50, seed="s")
        assert str(excinfo.value).endswith("duplicate task ids: x")

    def test_naming_duplicates_in_a_large_list_stays_within_budget(self):
        """40k ids took 18.5s before this; the bound is 9x under that.

        A timing assertion is the only way to hold a complexity fix, so the
        margin is wide enough that ordinary machine noise cannot reach it
        while a return to `list.count` per element cannot pass it.
        """
        ids = [f"t{index % 2}" for index in range(40000)]
        started = time.perf_counter()
        with pytest.raises(ValueError, match="duplicate task ids"):
            split_tasks(ids, seed="s")
        assert time.perf_counter() - started < 2.0

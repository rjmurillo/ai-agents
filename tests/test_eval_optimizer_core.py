"""Tests for scripts/eval/_optimizer_core.py (Issue #3422).

Pure-function tests. The module under test performs no I/O and makes no API
calls, so nothing here is mocked; every case is exercised directly.

Coverage obligation per .agents/governance/TESTING-RIGOR.md: positive, negative,
and edge cases per public function, every raise branch, every conditional
branch that changes user-facing output.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_EVAL_DIR = _REPO_ROOT / "scripts" / "eval"
if str(_EVAL_DIR) not in sys.path:
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
    patch_fingerprint,
    score,
    split_tasks,
)

FENCE_START = "<!-- SLOW_UPDATE_START -->"
FENCE_END = "<!-- SLOW_UPDATE_END -->"


def _ids(n: int, prefix: str = "F") -> list[str]:
    return [f"{prefix}{i:03d}" for i in range(1, n + 1)]


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

    def test_rejects_blank_task_id(self):
        with pytest.raises(ValueError, match="non-empty"):
            split_tasks(["A", "   "], seed="s")

    def test_rejects_empty_seed(self):
        with pytest.raises(ValueError, match="seed"):
            split_tasks(_ids(10), seed="")

    @pytest.mark.parametrize("ratio", [0.0, 1.0, -0.1, 1.5])
    def test_rejects_out_of_range_sel_ratio(self, ratio):
        with pytest.raises(ValueError, match="sel_ratio"):
            split_tasks(_ids(20), seed="s", sel_ratio=ratio)

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

    def test_smallest_viable_set_splits(self):
        split = split_tasks(_ids(4), seed="s", sel_ratio=0.75, min_sel=3)
        assert len(split.sel) == 3
        assert len(split.opt) == 1

    def test_task_ids_are_stripped(self):
        split = split_tasks([" A ", "B", "C", "D"], seed="s", sel_ratio=0.5, min_sel=0)
        assert sorted(list(split.opt) + list(split.sel)) == ["A", "B", "C", "D"]

    def test_rejects_ids_that_collide_after_stripping(self):
        with pytest.raises(ValueError, match="duplicate"):
            split_tasks(["A", " A "], seed="s", min_sel=0)


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

    def test_order_does_not_change_the_fingerprint(self):
        a = [Patch("append", None, "one"), Patch("append", None, "two")]
        b = [Patch("append", None, "two"), Patch("append", None, "one")]
        assert patch_fingerprint(a) == patch_fingerprint(b)

    def test_whitespace_reflow_does_not_change_the_fingerprint(self):
        a = [Patch("replace", "x", "hello  world")]
        b = [Patch("replace", "x", "hello\n world ")]
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

    def test_matches_across_reordering(self):
        stored = [Patch("append", None, "one"), Patch("append", None, "two")]
        buffer = [{"fingerprint": patch_fingerprint(stored)}]
        reordered = [Patch("append", None, "two"), Patch("append", None, "one")]
        assert buffer_contains(buffer, reordered) is True

    def test_ignores_buffer_entries_without_a_fingerprint(self):
        buffer = [{"note": "malformed"}, {"fingerprint": None}]
        assert buffer_contains(buffer, [Patch("append", None, "x")]) is False

    def test_rejects_an_empty_patch_list(self):
        with pytest.raises(ValueError, match="at least one patch"):
            buffer_contains([], [])

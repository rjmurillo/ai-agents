"""Tests for the skillopt patch applier, edit budget, and slow-section guard."""

from __future__ import annotations

import itertools
from typing import Any, cast

import pytest
import skillopt
from skillopt import SkillOptError


class TestEditBudget:
    def test_first_step_is_max(self) -> None:
        assert skillopt.edit_budget(0, 10, l_max=5, l_min=1) == 5

    def test_last_step_is_min(self) -> None:
        assert skillopt.edit_budget(9, 10, l_max=5, l_min=1) == 1

    def test_single_step_is_max(self) -> None:
        assert skillopt.edit_budget(0, 1, l_max=4, l_min=1) == 4

    def test_monotonic_non_increasing(self) -> None:
        budgets = [skillopt.edit_budget(s, 20, l_max=8, l_min=1) for s in range(20)]
        assert all(b >= n for b, n in itertools.pairwise(budgets))
        assert budgets[0] == 8 and budgets[-1] == 1

    def test_midpoint_between_bounds(self) -> None:
        assert skillopt.edit_budget(5, 11, l_max=10, l_min=2) == 6  # 2 + (10-2)*0.5

    def test_total_steps_zero_rejected(self) -> None:
        with pytest.raises(SkillOptError, match="total_steps"):
            skillopt.edit_budget(0, 0)

    def test_step_out_of_range_rejected(self) -> None:
        with pytest.raises(SkillOptError, match="out of range"):
            skillopt.edit_budget(10, 10)
        with pytest.raises(SkillOptError, match="out of range"):
            skillopt.edit_budget(-1, 10)

    def test_bad_bounds_rejected(self) -> None:
        with pytest.raises(SkillOptError, match="l_min"):
            skillopt.edit_budget(0, 5, l_max=5, l_min=0)
        with pytest.raises(SkillOptError, match="l_max"):
            skillopt.edit_budget(0, 5, l_max=1, l_min=3)


class TestProtectedRanges:
    def test_no_fence(self) -> None:
        assert skillopt.protected_ranges(["a", "b", "c"]) == []

    def test_single_fence(self) -> None:
        lines = ["a", skillopt.SLOW_START, "x", "y", skillopt.SLOW_END, "b"]
        assert skillopt.protected_ranges(lines) == [(1, 4)]

    def test_multiple_fences(self) -> None:
        lines = [
            skillopt.SLOW_START, "x", skillopt.SLOW_END,
            "mid",
            skillopt.SLOW_START, "y", skillopt.SLOW_END,
        ]  # fmt: skip
        assert skillopt.protected_ranges(lines) == [(0, 2), (4, 6)]

    def test_indented_markers_detected(self) -> None:
        lines = ["a", f"  {skillopt.SLOW_START}", "x", f"\t{skillopt.SLOW_END}"]
        assert skillopt.protected_ranges(lines) == [(1, 3)]

    def test_nested_start_rejected(self) -> None:
        with pytest.raises(SkillOptError, match="nested"):
            skillopt.protected_ranges([skillopt.SLOW_START, skillopt.SLOW_START, skillopt.SLOW_END])

    def test_end_without_start_rejected(self) -> None:
        with pytest.raises(SkillOptError, match="without"):
            skillopt.protected_ranges(["a", skillopt.SLOW_END])

    def test_unterminated_rejected(self) -> None:
        with pytest.raises(SkillOptError, match="unterminated"):
            skillopt.protected_ranges([skillopt.SLOW_START, "x"])


class TestApplyPatches:
    DOC = "line one\nline two\nline three"
    FENCED = "\n".join(
        ["intro", skillopt.SLOW_START, "rail one", "rail two", skillopt.SLOW_END, "outro"]
    )

    def test_append(self) -> None:
        out = skillopt.apply_patches(self.DOC, [{"op": "append", "text": "line four"}], budget=1)
        assert out.endswith("line three\nline four")

    def test_append_multiline(self) -> None:
        out = skillopt.apply_patches(self.DOC, [{"op": "append", "text": "a\nb"}], budget=1)
        assert out.split("\n")[-2:] == ["a", "b"]

    def test_append_without_text_adds_empty_line(self) -> None:
        out = skillopt.apply_patches(self.DOC, [{"op": "append"}], budget=1)
        assert out == self.DOC + "\n"

    def test_insert_after(self) -> None:
        patch = {"op": "insert_after", "anchor": "line one", "text": "INS"}
        out = skillopt.apply_patches(self.DOC, [patch], budget=1)
        assert out.split("\n") == ["line one", "INS", "line two", "line three"]

    def test_replace(self) -> None:
        patch = {"op": "replace", "anchor": "line two", "text": "TWO"}
        out = skillopt.apply_patches(self.DOC, [patch], budget=1)
        assert out.split("\n") == ["line one", "TWO", "line three"]

    def test_delete(self) -> None:
        out = skillopt.apply_patches(self.DOC, [{"op": "delete", "anchor": "line two"}], budget=1)
        assert out.split("\n") == ["line one", "line three"]

    def test_multiple_patches_in_one_step(self) -> None:
        patches = [
            {"op": "replace", "anchor": "line one", "text": "ONE"},
            {"op": "append", "text": "END"},
        ]
        out = skillopt.apply_patches(self.DOC, patches, budget=2)
        assert out.split("\n") == ["ONE", "line two", "line three", "END"]

    def test_budget_exceeded_rejects_batch(self) -> None:
        patches = [{"op": "append", "text": "a"}, {"op": "append", "text": "b"}]
        with pytest.raises(SkillOptError, match="budget exceeded"):
            skillopt.apply_patches(self.DOC, patches, budget=1)

    def test_negative_budget_rejected(self) -> None:
        with pytest.raises(SkillOptError, match="budget must be"):
            skillopt.apply_patches(self.DOC, [], budget=-1)

    def test_invalid_op_rejected(self) -> None:
        with pytest.raises(SkillOptError, match="invalid op"):
            skillopt.apply_patches(self.DOC, [{"op": "frobnicate"}], budget=1)

    def test_missing_op_rejected(self) -> None:
        with pytest.raises(SkillOptError, match="invalid op"):
            skillopt.apply_patches(self.DOC, [{"text": "x"}], budget=1)

    def test_anchor_not_found_rejected(self) -> None:
        with pytest.raises(SkillOptError, match="not found"):
            skillopt.apply_patches(self.DOC, [{"op": "delete", "anchor": "nope"}], budget=1)

    def test_anchor_ambiguous_rejected(self) -> None:
        with pytest.raises(SkillOptError, match="ambiguous"):
            skillopt.apply_patches("dup\ndup\n", [{"op": "delete", "anchor": "dup"}], budget=1)

    def test_non_string_anchor_rejected(self) -> None:
        patch = {"op": "replace", "anchor": 3, "text": "x"}
        with pytest.raises(SkillOptError, match="string 'anchor'"):
            skillopt.apply_patches(self.DOC, [patch], budget=1)

    def test_missing_anchor_rejected(self) -> None:
        with pytest.raises(SkillOptError, match="string 'anchor'"):
            skillopt.apply_patches(self.DOC, [{"op": "delete"}], budget=1)

    def test_non_string_text_rejected(self) -> None:
        with pytest.raises(SkillOptError, match="'text' must be a string"):
            skillopt.apply_patches(self.DOC, [{"op": "append", "text": 5}], budget=1)

    @pytest.mark.parametrize("patches", [{"op": "append"}, "append", None, [1], ["append"], [[]]])
    def test_non_list_or_non_object_patches_rejected(self, patches: object) -> None:
        with pytest.raises(SkillOptError, match="list of objects"):
            skillopt.apply_patches(self.DOC, cast(Any, patches), budget=5)

    # --- slow-section protection ---
    def test_replace_inside_fence_rejected(self) -> None:
        patch = {"op": "replace", "anchor": "rail one", "text": "x"}
        with pytest.raises(SkillOptError, match="protected"):
            skillopt.apply_patches(self.FENCED, [patch], budget=1)

    def test_delete_inside_fence_rejected(self) -> None:
        with pytest.raises(SkillOptError, match="protected"):
            skillopt.apply_patches(self.FENCED, [{"op": "delete", "anchor": "rail two"}], budget=1)

    def test_replace_start_marker_rejected(self) -> None:
        patch = {"op": "replace", "anchor": skillopt.SLOW_START, "text": "x"}
        with pytest.raises(SkillOptError, match="protected"):
            skillopt.apply_patches(self.FENCED, [patch], budget=1)

    def test_replace_end_marker_rejected(self) -> None:
        patch = {"op": "replace", "anchor": skillopt.SLOW_END, "text": "x"}
        with pytest.raises(SkillOptError, match="protected"):
            skillopt.apply_patches(self.FENCED, [patch], budget=1)

    def test_insert_after_inside_fence_rejected(self) -> None:
        patch = {"op": "insert_after", "anchor": "rail one", "text": "x"}
        with pytest.raises(SkillOptError, match="protected"):
            skillopt.apply_patches(self.FENCED, [patch], budget=1)

    def test_insert_after_start_marker_rejected(self) -> None:
        patch = {"op": "insert_after", "anchor": skillopt.SLOW_START, "text": "x"}
        with pytest.raises(SkillOptError, match="protected"):
            skillopt.apply_patches(self.FENCED, [patch], budget=1)

    def test_insert_after_end_marker_allowed(self) -> None:
        patch = {"op": "insert_after", "anchor": skillopt.SLOW_END, "text": "added"}
        out = skillopt.apply_patches(self.FENCED, [patch], budget=1).split("\n")
        assert out[out.index(skillopt.SLOW_END) + 1] == "added"

    def test_append_allowed_with_fence(self) -> None:
        out = skillopt.apply_patches(self.FENCED, [{"op": "append", "text": "tail"}], budget=1)
        assert out.split("\n")[-1] == "tail"
        assert "rail one" in out  # fence content untouched

    def test_edit_outside_fence_allowed(self) -> None:
        patch = {"op": "replace", "anchor": "intro", "text": "INTRO"}
        assert skillopt.apply_patches(self.FENCED, [patch], budget=1).startswith("INTRO")

    def test_nested_fence_in_doc_errors(self) -> None:
        doc = "\n".join([skillopt.SLOW_START, skillopt.SLOW_START, skillopt.SLOW_END, "x"])
        with pytest.raises(SkillOptError, match="nested"):
            skillopt.apply_patches(doc, [{"op": "append", "text": "y"}], budget=1)

    def test_unterminated_fence_in_doc_errors(self) -> None:
        doc = "\n".join(["a", skillopt.SLOW_START, "b"])
        with pytest.raises(SkillOptError, match="unterminated"):
            skillopt.apply_patches(doc, [{"op": "append", "text": "y"}], budget=1)

    def test_orphan_end_in_doc_errors(self) -> None:
        doc = "\n".join(["a", skillopt.SLOW_END, "b"])
        with pytest.raises(SkillOptError, match="without"):
            skillopt.apply_patches(doc, [{"op": "delete", "anchor": "a"}], budget=1)

    # --- marker text and final fence check ---
    @pytest.mark.parametrize("op", ["append", "insert_after", "replace"])
    @pytest.mark.parametrize(
        "text",
        [
            skillopt.SLOW_START,
            skillopt.SLOW_END,
            "prefix SLOW_UPDATE_START suffix",
            "a\nSLOW_UPDATE_END",
            f"a\n{skillopt.SLOW_START}\nb\n{skillopt.SLOW_END}",
        ],
    )
    def test_marker_text_in_patch_rejected(self, op: str, text: str) -> None:
        patch = {"op": op, "anchor": "line two", "text": text}
        with pytest.raises(SkillOptError, match="slow-section marker text"):
            skillopt.apply_patches(self.DOC, [patch], budget=1)

    def test_marker_text_in_delete_patch_is_irrelevant(self) -> None:
        patch = {"op": "delete", "anchor": "line two", "text": skillopt.SLOW_START}
        out = skillopt.apply_patches(self.DOC, [patch], budget=1)
        assert out.split("\n") == ["line one", "line three"]

    def test_final_check_rejects_malformed_fence_with_no_patches(self) -> None:
        doc = "\n".join(["a", skillopt.SLOW_START, "b"])
        with pytest.raises(SkillOptError, match="unterminated"):
            skillopt.apply_patches(doc, [], budget=0)

    def test_final_check_accepts_wellformed_fence_with_no_patches(self) -> None:
        assert skillopt.apply_patches(self.FENCED, [], budget=0) == self.FENCED

    # --- CRLF ---
    def test_crlf_round_trip_preserved(self) -> None:
        doc = "line one\r\nline two\r\nline three\r\n"
        patch = {"op": "replace", "anchor": "line two", "text": "TWO"}
        out = skillopt.apply_patches(doc, [patch], budget=1)
        assert out == "line one\r\nTWO\r\nline three\r\n"

    def test_crlf_multiline_text_and_crlf_text(self) -> None:
        doc = "a\r\nb\r\n"
        patch = {"op": "insert_after", "anchor": "a", "text": "x\r\ny"}
        assert skillopt.apply_patches(doc, [patch], budget=1) == "a\r\nx\r\ny\r\nb\r\n"

    def test_crlf_no_patches_is_byte_identical(self) -> None:
        doc = "a\r\nb\r\n"
        assert skillopt.apply_patches(doc, [], budget=0) == doc

    def test_lf_doc_stays_lf(self) -> None:
        out = skillopt.apply_patches("a\nb\n", [{"op": "append", "text": "c"}], budget=1)
        assert "\r" not in out

    def test_crlf_fence_protected(self) -> None:
        doc = f"intro\r\n{skillopt.SLOW_START}\r\nrail\r\n{skillopt.SLOW_END}\r\n"
        with pytest.raises(SkillOptError, match="protected"):
            skillopt.apply_patches(doc, [{"op": "delete", "anchor": "rail"}], budget=1)

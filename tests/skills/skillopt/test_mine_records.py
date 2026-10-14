"""Tests for transcript parsing, correction cues, aggregation, ranking, and tasks."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import _mine_records as mr
import mine_sessions as ms
import pytest
from skillopt_helpers import (
    skill_use,
    user,
)


class TestIsCorrection:
    @pytest.mark.parametrize(
        "text",
        [
            "That's not right",
            "revert that",
            "undo",
            "this is broken",
            "WRONG",
            "that doesn't work",
            "that does not work",
            "It Does Not Work at all",
            "it didn't work",
            "it did not work",
            "try again",
            "still failing",
        ],
    )
    def test_positive(self, text: str) -> None:
        assert ms.is_correction(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "great, thanks",
            "looks good",
            "ship it",
            "",
            "no problem",
            "don't worry",
            "actually nice",
            "it does work",
        ],
    )
    def test_negative_includes_dropped_noisy_cues(self, text: str) -> None:
        # "no", "don't", "actually" were dropped: they saturated every skill at 1.0
        assert ms.is_correction(text) is False

    def test_regression_typo_cue_is_gone(self) -> None:
        assert not any("ddoes" in cue for cue in ms.CORRECTION_CUES)

    def test_non_string(self) -> None:
        assert ms.is_correction(cast(Any, None)) is False


class TestContentText:
    def test_string(self) -> None:
        assert mr._content_text({"content": "hi"}) == "hi"

    def test_block_list(self) -> None:
        msg = {"content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]}
        assert mr._content_text(msg) == "a\nb"

    def test_block_list_ignores_non_text(self) -> None:
        msg = {
            "content": [{"type": "tool_use", "name": "X"}, {"type": "text", "text": "t"}, "bare"]
        }
        assert mr._content_text(msg) == "t"

    def test_missing_content(self) -> None:
        assert mr._content_text({}) == ""


class TestExtractSkillInvocations:
    def test_skill_tool_use(self) -> None:
        assert ms.extract_skill_invocations(skill_use("review")) == ["review"]

    def test_skill_tool_use_command_key(self) -> None:
        rec = {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Skill", "input": {"command": "ship"}}]}}  # fmt: skip
        assert ms.extract_skill_invocations(rec) == ["ship"]

    @pytest.mark.parametrize("name", ["", 5, None])
    def test_skill_tool_use_without_usable_name(self, name: object) -> None:
        rec = {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Skill", "input": {"skill": name}}]}}  # fmt: skip
        assert ms.extract_skill_invocations(rec) == []

    def test_non_skill_tool_use_ignored(self) -> None:
        rec = {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}]}}  # fmt: skip
        assert ms.extract_skill_invocations(rec) == []

    def test_tool_use_bad_input(self) -> None:
        rec = {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Skill", "input": "oops"}]}}  # fmt: skip
        assert ms.extract_skill_invocations(rec) == []

    def test_command_name_tag_in_content(self) -> None:
        rec = {"type": "user", "message": {"content": "<command-name>/qa</command-name> run it"}}
        assert ms.extract_skill_invocations(rec) == ["qa"]

    def test_last_prompt_command(self) -> None:
        rec = {"type": "last-prompt", "prompt": "<command-name>build</command-name>"}
        assert ms.extract_skill_invocations(rec) == ["build"]

    def test_last_prompt_non_string(self) -> None:
        assert ms.extract_skill_invocations({"type": "last-prompt", "prompt": 5}) == []

    def test_non_tooluse_blocks_skipped(self) -> None:
        rec = {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "thinking"}, "bare-string-block"]}}  # fmt: skip
        assert ms.extract_skill_invocations(rec) == []

    def test_no_message(self) -> None:
        assert ms.extract_skill_invocations({"type": "assistant"}) == []


class TestUserText:
    def test_user_record(self) -> None:
        assert ms.user_text(user("hello")) == "hello"

    def test_nonuser(self) -> None:
        assert ms.user_text({"type": "assistant", "message": {"content": "x"}}) is None

    def test_user_bad_message(self) -> None:
        assert ms.user_text({"type": "user", "message": "nope"}) is None


class TestIterRecords:
    def test_parses_and_skips_bad(self, tmp_path: Path) -> None:
        f = tmp_path / "t.jsonl"
        f.write_text('{"type":"user"}\n\nnot json\n["a list"]\n', encoding="utf-8")
        assert list(ms.iter_records([f])) == [{"type": "user"}]

    def test_unreadable_file_skipped(self, tmp_path: Path) -> None:
        assert list(ms.iter_records([tmp_path / "nope.jsonl"])) == []


class TestAggregate:
    def test_counts_invocations(self) -> None:
        stats = ms.aggregate([skill_use("a"), skill_use("a"), skill_use("b")])
        assert stats["a"]["invocations"] == 2
        assert stats["b"]["invocations"] == 1

    def test_attributes_correction_within_window(self) -> None:
        assert ms.aggregate([skill_use("a"), user("no that's wrong")])["a"]["corrections"] == 1

    def test_one_invocation_credited_once_for_repeated_corrections(self) -> None:
        recs = [skill_use("a"), user("that's wrong"), user("still broken")]
        stats = ms.aggregate(recs, window=3)
        assert stats["a"] == {"invocations": 1, "corrections": 1}

    def test_each_invocation_credited_once_when_overlapping(self) -> None:
        recs = [skill_use("a"), user("wrong"), skill_use("a"), user("wrong"), user("wrong")]
        stats = ms.aggregate(recs, window=3)
        assert stats["a"]["invocations"] == 2
        assert stats["a"]["corrections"] <= stats["a"]["invocations"]

    def test_does_not_work_counts_as_correction(self) -> None:
        assert ms.aggregate([skill_use("a"), user("this does not work")])["a"]["corrections"] == 1

    def test_no_correction_when_praise(self) -> None:
        assert ms.aggregate([skill_use("a"), user("perfect, thanks")])["a"]["corrections"] == 0

    def test_correction_outside_window_not_attributed(self) -> None:
        recs = [skill_use("a"), user("ok"), user("ok"), user("ok"), user("no wrong")]
        assert ms.aggregate(recs, window=1)["a"]["corrections"] == 0


class TestRank:
    def test_scoring_and_sort(self) -> None:
        stats = {"a": {"invocations": 10, "corrections": 5},
                 "b": {"invocations": 2, "corrections": 0}}  # fmt: skip
        rows = ms.rank(stats)
        assert rows[0]["skill"] == "a"
        assert rows[0]["correction_rate"] == 0.5
        assert rows[0]["target_score"] == 7.5  # 10*(0.25+0.5)

    def test_zero_invocations_has_zero_rate(self) -> None:
        rows = ms.rank({"a": {"invocations": 0, "corrections": 0}})
        assert rows[0]["correction_rate"] == 0.0

    def test_in_repo_flag(self) -> None:
        stats = {"a": {"invocations": 1, "corrections": 0}}
        assert ms.rank(stats, known={"a"})[0]["in_repo"] is True
        assert ms.rank(stats, known=set())[0]["in_repo"] is False

    def test_known_none_marks_all_in_repo(self) -> None:
        assert (
            ms.rank({"a": {"invocations": 1, "corrections": 0}}, known=None)[0]["in_repo"] is True
        )

    def test_corrections_rank_but_are_not_labels(self) -> None:
        """Corrections only reorder candidates; no row carries a pass/fail label."""
        rows = ms.rank({"a": {"invocations": 4, "corrections": 4}})
        assert set(rows[0]) == {
            "skill",
            "invocations",
            "corrections",
            "correction_rate",
            "target_score",
            "in_repo",
        }


class TestExtractTasks:
    def test_captures_preceding_prompt(self) -> None:
        recs = [user("optimize the build skill"), skill_use("build")]
        assert ms.extract_tasks(recs, "build") == ["optimize the build skill"]

    def test_no_prompt_no_task(self) -> None:
        assert ms.extract_tasks([skill_use("x")], "x") == []

    def test_blank_prompt_ignored(self) -> None:
        assert ms.extract_tasks([user("   "), skill_use("x")], "x") == []

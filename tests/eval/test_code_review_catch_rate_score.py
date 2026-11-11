"""Tests for scripts/eval/_code_review_catch_rate_score.py (issue #7149).

Covers the pinned match rule: same file and same class inside the top 5 is a
catch, same file with another class is a near miss, anything else is a miss.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import _code_review_catch_rate_score as score  # noqa: E402

FILES = ("scripts/validation/merge_causal_graph.py",)


def _finding(path: str, klass: str, text: str = "the defect") -> str:
    return f"FINDING: {path} | {klass} | {text}"


class TestParseFindings:
    def test_parses_plain_line_with_line_number(self):
        found = score.parse_findings(_finding("a/b.py:42", "logic-error", "Wrong branch."))

        assert [(f.path, f.klass, f.text) for f in found] == [
            ("a/b.py", "logic-error", "Wrong branch.")
        ]

    def test_parses_bullet_bold_and_backtick_variants(self):
        raw = (
            "- **FINDING**: `x/y.py:7-9` | Edge Case | Empty input crashes.\n"
            "* FINDING: ./z.py:? | security | Bypass."
        )

        found = score.parse_findings(raw)

        assert [(f.path, f.klass) for f in found] == [("x/y.py", "edge-case"), ("z.py", "security")]

    def test_no_findings_marker_and_prose_parse_to_nothing(self):
        assert score.parse_findings("NO FINDINGS\n\nVERDICT: PASS") == []
        assert score.parse_findings("") == []
        assert score.parse_findings("The change looks fine. See a.py:3 | maybe | nothing.") == []

    def test_line_without_class_field_is_not_a_finding(self):
        assert score.parse_findings("FINDING: a.py:3 | only two fields") == []

    def test_order_is_preserved(self):
        raw = "\n".join(_finding(f"f{i}.py:1", "logic-error") for i in range(3))

        assert [f.path for f in score.parse_findings(raw)] == ["f0.py", "f1.py", "f2.py"]


class TestSameFile:
    @pytest.mark.parametrize(
        ("finding", "defect", "expected"),
        [
            ("scripts/a.py", "scripts/a.py", True),
            ("a.py", "scripts/a.py", True),
            ("scripts/a.py", "a.py", True),
            ("b/scripts/a.py", "scripts/a.py", True),
            ("ripts/a.py", "scripts/a.py", False),
            ("scripts/a.py", "scripts/b.py", False),
            ("", "scripts/a.py", False),
            ("a.py", "other/dir/xa.py", False),
        ],
    )
    def test_path_match_cases(self, finding, defect, expected):
        assert score.same_file(finding, defect) is expected


class TestScoring:
    def test_same_file_and_class_is_caught(self):
        raw = _finding("scripts/validation/merge_causal_graph.py:88", "resource-handling")

        outcome = score.score_response(raw, FILES, "resource-handling")

        assert outcome.caught and not outcome.near_miss
        assert outcome.matched == "the defect"

    def test_same_file_other_class_is_a_near_miss_not_a_catch(self):
        raw = _finding("scripts/validation/merge_causal_graph.py:88", "logic-error")

        outcome = score.score_response(raw, FILES, "resource-handling")

        assert not outcome.caught and outcome.near_miss and outcome.matched is None

    def test_same_class_wrong_file_is_a_miss(self):
        raw = _finding("scripts/other.py:1", "resource-handling")

        outcome = score.score_response(raw, FILES, "resource-handling")

        assert not outcome.caught and not outcome.near_miss

    def test_empty_findings_is_a_miss(self):
        outcome = score.score_response("NO FINDINGS\nVERDICT: PASS", FILES, "resource-handling")

        assert not outcome.caught and not outcome.near_miss
        assert outcome.findings == () and outcome.extra == 0

    def test_a_mirror_copy_of_the_file_counts(self):
        files = ("src/copilot-cli/skills/x/run.py", ".claude/skills/x/run.py")
        raw = _finding(".claude/skills/x/run.py:3", "security")

        assert score.score_response(raw, files, "security").caught

    def test_only_the_first_five_findings_count(self):
        decoys = [_finding(f"d{i}.py:1", "logic-error") for i in range(5)]
        hit = _finding("scripts/validation/merge_causal_graph.py:1", "resource-handling")

        outcome = score.score_response("\n".join([*decoys, hit]), FILES, "resource-handling")

        assert not outcome.caught
        assert outcome.extra == 1 and len(outcome.findings) == 5

    def test_a_hit_at_rank_five_counts(self):
        decoys = [_finding(f"d{i}.py:1", "logic-error") for i in range(4)]
        hit = _finding("scripts/validation/merge_causal_graph.py:1", "resource-handling")

        assert score.score_response("\n".join([*decoys, hit]), FILES, "resource-handling").caught

    def test_a_later_catch_beats_an_earlier_near_miss(self):
        near = _finding("scripts/validation/merge_causal_graph.py:1", "logic-error")
        hit = _finding("scripts/validation/merge_causal_graph.py:9", "resource-handling")

        outcome = score.score_response(f"{near}\n{hit}", FILES, "resource-handling")

        assert outcome.caught and not outcome.near_miss


class TestLeakDetection:
    FIX_PATCH = (
        "+++ b/f.py\n"
        "+    return compute_the_corrected_value(argument_one, argument_two)\n"
        "+    x = 1\n"
    )
    INTRO_PATCH = "+++ b/f.py\n+    x = 1\n"

    def test_clean_prompt_reports_nothing(self):
        prompt = "diff of the introducing change\n+    x = 1\n"

        assert (
            score.leaked_fix_content(
                prompt, "f" * 40, "fix: repair it", self.FIX_PATCH, self.INTRO_PATCH
            )
            == []
        )

    def test_fix_sha_prefix_subject_and_long_added_line_are_caught(self):
        prompt = (
            f"see {'f' * 12}\nfix: repair it\n"
            "    return compute_the_corrected_value(argument_one, argument_two)\n"
        )

        reasons = score.leaked_fix_content(
            prompt, "f" * 40, "fix: repair it", self.FIX_PATCH, self.INTRO_PATCH
        )

        assert any("fix sha" in r for r in reasons)
        assert "fix subject" in reasons
        assert any("fix line" in r for r in reasons)

    @pytest.mark.parametrize("run_length", [7, 8, 12, 40])
    def test_any_sha_prefix_of_seven_or_more_characters_is_caught(self, run_length):
        fix_sha = "abcdef0123456789abcdef0123456789abcdef01"
        prompt = f"Reverts {fix_sha[:run_length]} later\n"

        reasons = score.leaked_fix_content(prompt, fix_sha, "fix: unrelated", "", "")

        assert reasons == [f"fix sha {fix_sha[:run_length]}"]

    def test_short_or_unrelated_hex_runs_are_not_a_leak(self):
        fix_sha = "abcdef0123456789abcdef0123456789abcdef01"
        prompt = "abcdef is only 6 chars; deadbeef is another commit; abcdee1 is not a prefix\n"

        reasons = score.leaked_fix_content(prompt, fix_sha, "fix: unrelated", "", "")

        assert reasons == []

    def test_a_line_both_patches_add_is_shared_not_a_leak(self):
        shared = "    value = compute_the_shared_helper(argument_one, argument_two)"
        fix = f"+++ b/f.py\n+{shared}\n"
        intro = f"+++ b/f.py\n+{shared}\n"

        assert (
            score.leaked_fix_content(shared, "a" * 40, "fix: an unrelated subject", fix, intro)
            == []
        )

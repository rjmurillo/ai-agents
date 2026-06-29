"""Tests for scripts/eval/_oneshot_bench_core.py (issue #2788).

Covers fixture validation, hardest-N selection, prompt construction (fix is
withheld from the agent, shown to the judge), judge-response parsing including
the malformed/off-grammar failure paths, and aggregation.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

import _oneshot_bench_core as core  # noqa: E402


def _fixture_dict(**overrides: object) -> dict:
    base = {
        "id": "f1",
        "source_repo": "owner/repo",
        "issue_number": 10,
        "title": "Bug title",
        "discourse": "the issue discussion",
        "shipped_fix": "the merged fix",
        "edges_named_in_discourse": ["edge A", "edge B"],
        "difficulty": 4,
    }
    base.update(overrides)
    return base


# --- Fixture.from_dict -------------------------------------------------------


def test_from_dict_builds_fixture():
    fixture = core.Fixture.from_dict(_fixture_dict())
    assert fixture.id == "f1"
    assert fixture.issue_number == 10
    assert fixture.edges_named_in_discourse == ("edge A", "edge B")
    assert fixture.difficulty == 4


def test_from_dict_missing_required_field_raises():
    payload = _fixture_dict()
    del payload["shipped_fix"]
    with pytest.raises(core.FixtureError, match="shipped_fix"):
        core.Fixture.from_dict(payload)


def test_from_dict_empty_required_field_raises():
    with pytest.raises(core.FixtureError, match="discourse"):
        core.Fixture.from_dict(_fixture_dict(discourse=""))


def test_from_dict_non_integer_issue_number_raises():
    with pytest.raises(core.FixtureError, match="integers"):
        core.Fixture.from_dict(_fixture_dict(issue_number="ten"))


def test_from_dict_out_of_range_difficulty_raises():
    with pytest.raises(core.FixtureError, match="difficulty"):
        core.Fixture.from_dict(_fixture_dict(difficulty=9))


def test_from_dict_edges_not_a_list_raises():
    with pytest.raises(core.FixtureError, match="edges_named_in_discourse"):
        core.Fixture.from_dict(_fixture_dict(edges_named_in_discourse="edge"))


def test_from_dict_defaults_difficulty_and_edges():
    payload = _fixture_dict()
    del payload["difficulty"]
    del payload["edges_named_in_discourse"]
    fixture = core.Fixture.from_dict(payload)
    assert fixture.difficulty == 3
    assert fixture.edges_named_in_discourse == ()


# --- load_fixture / load_fixtures -------------------------------------------


def test_load_fixture_round_trips(tmp_path: Path):
    path = tmp_path / "f.json"
    path.write_text(json.dumps(_fixture_dict()), encoding="utf-8")
    assert core.load_fixture(path).id == "f1"


def test_load_fixture_bad_json_raises(tmp_path: Path):
    path = tmp_path / "f.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(core.FixtureError, match="not valid JSON"):
        core.load_fixture(path)


def test_load_fixture_non_object_raises(tmp_path: Path):
    path = tmp_path / "f.json"
    path.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(core.FixtureError, match="must be an object"):
        core.load_fixture(path)


def test_load_fixtures_sorted_by_id(tmp_path: Path):
    (tmp_path / "b.json").write_text(json.dumps(_fixture_dict(id="b")), encoding="utf-8")
    (tmp_path / "a.json").write_text(json.dumps(_fixture_dict(id="a")), encoding="utf-8")
    assert [f.id for f in core.load_fixtures(tmp_path)] == ["a", "b"]


# --- select_hardest ----------------------------------------------------------


def test_select_hardest_orders_by_difficulty():
    fixtures = [
        core.Fixture.from_dict(_fixture_dict(id="easy", difficulty=1)),
        core.Fixture.from_dict(_fixture_dict(id="hard", difficulty=5)),
        core.Fixture.from_dict(_fixture_dict(id="mid", difficulty=3)),
    ]
    assert [f.id for f in core.select_hardest(fixtures, 2)] == ["hard", "mid"]


def test_select_hardest_none_returns_all_ordered():
    fixtures = [
        core.Fixture.from_dict(_fixture_dict(id="easy", difficulty=1)),
        core.Fixture.from_dict(_fixture_dict(id="hard", difficulty=5)),
    ]
    assert [f.id for f in core.select_hardest(fixtures, None)] == ["hard", "easy"]


def test_select_hardest_zero_returns_all():
    fixtures = [core.Fixture.from_dict(_fixture_dict())]
    assert len(core.select_hardest(fixtures, 0)) == 1


# --- prompt construction -----------------------------------------------------


def test_agent_prompt_includes_discourse_and_withholds_fix():
    fixture = core.Fixture.from_dict(_fixture_dict())
    prompt = core.build_agent_prompt(fixture)
    assert "the issue discussion" in prompt
    assert "the merged fix" not in prompt  # ground truth is withheld


def test_judge_prompt_includes_fix_and_edges():
    fixture = core.Fixture.from_dict(_fixture_dict())
    prompt = core.build_judge_prompt(fixture, "the agent proposal")
    assert "the merged fix" in prompt
    assert "edge A" in prompt
    assert "the agent proposal" in prompt


def test_judge_prompt_handles_no_named_edges():
    fixture = core.Fixture.from_dict(_fixture_dict(edges_named_in_discourse=[]))
    prompt = core.build_judge_prompt(fixture, "x")
    assert "none explicitly named" in prompt


# --- parse_judge_response ----------------------------------------------------


def test_parse_full_grade():
    raw = json.dumps(
        {
            "grade": "FULL",
            "edges_caught": ["edge A", "edge B"],
            "edges_missed": [],
            "reasoning": "covers both.",
        }
    )
    verdict = core.parse_judge_response(raw)
    assert verdict.grade == "FULL"
    assert verdict.edges_caught == ("edge A", "edge B")
    assert verdict.judge_failed is False


def test_parse_grade_is_case_insensitive_and_strips_prose():
    raw = 'Here you go: {"grade": "partial", "reasoning": "missed one"}'
    verdict = core.parse_judge_response(raw)
    assert verdict.grade == "PARTIAL"
    assert verdict.judge_failed is False


def test_parse_no_json_is_failure():
    verdict = core.parse_judge_response("I cannot grade this.")
    assert verdict.judge_failed is True
    assert verdict.grade == "NONE"


def test_parse_malformed_json_is_failure():
    verdict = core.parse_judge_response('{"grade": "FULL", ')
    assert verdict.judge_failed is True


def test_parse_unknown_grade_is_failure():
    raw = json.dumps({"grade": "MAYBE"})
    verdict = core.parse_judge_response(raw)
    assert verdict.judge_failed is True
    assert verdict.grade == "NONE"


def test_parse_non_list_edges_coerce_to_empty():
    raw = json.dumps({"grade": "NONE", "edges_caught": "edge A"})
    verdict = core.parse_judge_response(raw)
    assert verdict.edges_caught == ()


# --- aggregate ---------------------------------------------------------------


def _result(fixture_id: str, grade: str, *, caught=(), failed=False, error=None):
    return core.FixtureResult(
        fixture_id=fixture_id,
        issue_number=1,
        difficulty=3,
        verdict=core.JudgeVerdict(grade, tuple(caught), (), "", failed),
        error=error,
    )


def test_aggregate_counts_grades_and_edges():
    fixtures = [
        core.Fixture.from_dict(_fixture_dict(id="a")),
        core.Fixture.from_dict(_fixture_dict(id="b")),
    ]
    results = [
        _result("a", "FULL", caught=["edge A", "edge B"]),
        _result("b", "PARTIAL", caught=["edge A"]),
    ]
    summary = core.aggregate(fixtures, results)
    assert (summary.full, summary.partial, summary.none) == (1, 1, 0)
    assert summary.edges_named == 4
    assert summary.edges_caught == 3
    assert summary.edge_catch_rate == pytest.approx(0.75)
    assert summary.same_or_better_rate == pytest.approx(0.5)
    assert summary.verdict == "SCORED"


def test_aggregate_judge_failure_makes_inconclusive():
    fixtures = [core.Fixture.from_dict(_fixture_dict(id="a"))]
    summary = core.aggregate(fixtures, [_result("a", "NONE", failed=True)])
    assert summary.judge_failures == 1
    assert summary.verdict == "INCONCLUSIVE_HARNESS_ERRORS"


def test_aggregate_api_error_makes_inconclusive():
    fixtures = [core.Fixture.from_dict(_fixture_dict(id="a"))]
    summary = core.aggregate(fixtures, [_result("a", "NONE", error="boom")])
    assert summary.api_errors == 1
    assert summary.verdict == "INCONCLUSIVE_HARNESS_ERRORS"


def test_aggregate_empty_is_no_fixtures():
    assert core.aggregate([], []).verdict == "NO_FIXTURES"

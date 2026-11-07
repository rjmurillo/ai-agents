"""bootstrap_eval: benchmark block, per-run evidence, case signals, and draft cases."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

_SCRIPTS = (
    Path(__file__).resolve().parents[3] / ".claude" / "skills" / "skill-bootstrap" / "scripts"
)
sys.path.insert(0, str(_SCRIPTS))
try:
    import bootstrap_eval
finally:
    sys.path.remove(str(_SCRIPTS))

Capsys = pytest.CaptureFixture[str]
Result = tuple[int, dict[str, Any]]

ALPHA = {"kind": "contains_all", "terms": ["alpha"]}


def _run(capsys: Capsys, *argv: str) -> Result:
    code = bootstrap_eval.main(list(argv))
    return code, json.loads(capsys.readouterr().out)


def _case(case_id: str = "C1", grader: Any = ALPHA, **extra: Any) -> dict[str, Any]:
    case = {"id": case_id, "skill": "acme", "source": "lens:ops", "prompt": "p"}
    if grader is not None:
        case["grader"] = grader
    return {**case, **extra}


def _write(path: Path, data: Any) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _freeze(capsys: Capsys, tmp_path: Path, cases: list[dict[str, Any]]) -> Path:
    cases_file = _write(tmp_path / "cases.json", {"cases": cases})
    frozen = tmp_path / "out" / "frozen.json"
    assert _run(capsys, "freeze", "--cases", str(cases_file), "--out", str(frozen))[0] == 0
    return frozen


def _row(case_id: str, condition: str, output: str, **extra: Any) -> dict[str, Any]:
    return {"case_id": case_id, "condition": condition, "output": output, **extra}


def _score(
    capsys: Capsys,
    tmp_path: Path,
    cases: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    *extra: str,
) -> Result:
    frozen = _freeze(capsys, tmp_path, cases)
    results = tmp_path / "r.jsonl"
    results.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return _run(capsys, "score", "--frozen", str(frozen), "--results", str(results), *extra)


# --- benchmark ---------------------------------------------------------------


def test_pass_rate_mean_and_stdev_cover_complete_cases_and_match_overall(capsys, tmp_path):
    rows = [
        _row("C1", "baseline", "nope"),
        _row("C1", "with_skill", "alpha"),
        _row("C2", "baseline", "alpha"),
        _row("C2", "with_skill", "alpha"),
    ]

    _, payload = _score(capsys, tmp_path, [_case("C1"), _case("C2")], rows)

    bench = payload["benchmark"]
    assert bench["baseline"]["pass_rate"] == {"n": 2, "mean": 0.5, "stdev": 0.7071}
    assert bench["with_skill"]["pass_rate"] == {"n": 2, "mean": 1.0, "stdev": 0.0}
    assert bench["delta"]["pass_rate"] == 0.5
    assert bench["baseline"]["pass_rate"]["mean"] == payload["overall"]["baseline"]
    assert bench["delta"]["pass_rate"] == payload["overall"]["capability_delta"]


def test_time_and_token_means_pool_recorded_runs_and_report_the_delta(capsys, tmp_path):
    rows = [
        _row("C1", "baseline", "nope", duration_ms=1000, total_tokens=100),
        _row("C1", "baseline", "nope", duration_ms=3000, total_tokens=300),
        _row("C1", "with_skill", "alpha", duration_ms=4000, total_tokens=500),
        _row("C1", "with_skill", "alpha", duration_ms=6000, total_tokens=700),
    ]

    _, payload = _score(capsys, tmp_path, [_case()], rows)

    bench = payload["benchmark"]
    assert bench["baseline"]["duration_ms"] == {"n": 2, "mean": 2000.0, "stdev": 1414.2136}
    assert bench["with_skill"]["total_tokens"]["mean"] == 600.0
    assert bench["delta"]["duration_ms"] == 3000.0
    assert bench["delta"]["total_tokens"] == 400.0


def test_runs_without_timing_leave_time_and_token_stats_empty_not_zero(capsys, tmp_path):
    rows = [_row("C1", "baseline", "nope"), _row("C1", "with_skill", "alpha")]

    _, payload = _score(capsys, tmp_path, [_case()], rows)

    bench = payload["benchmark"]
    assert bench["baseline"]["duration_ms"] == {"n": 0, "mean": None, "stdev": None}
    assert bench["delta"]["duration_ms"] is None
    assert bench["delta"]["total_tokens"] is None


def test_one_sided_timing_gives_no_delta(capsys, tmp_path):
    rows = [
        _row("C1", "baseline", "nope"),
        _row("C1", "with_skill", "alpha", total_tokens=500),
    ]

    _, payload = _score(capsys, tmp_path, [_case()], rows)

    assert payload["benchmark"]["with_skill"]["total_tokens"]["n"] == 1
    assert payload["benchmark"]["with_skill"]["total_tokens"]["stdev"] is None
    assert payload["benchmark"]["delta"]["total_tokens"] is None


def test_an_incomplete_case_stays_out_of_the_pass_rate_stats(capsys, tmp_path):
    rows = [_row("C1", "baseline", "nope"), _row("C1", "with_skill", "alpha")]

    _, payload = _score(capsys, tmp_path, [_case("C1"), _case("C2")], rows)

    assert payload["benchmark"]["baseline"]["pass_rate"]["n"] == 1
    assert payload["cases"][1]["status"] == "incomplete"


@pytest.mark.parametrize(
    ("extra", "fragment"),
    [
        ({"duration_ms": -1}, "duration_ms must be a number"),
        ({"duration_ms": "fast"}, "duration_ms must be a number"),
        ({"duration_ms": True}, "duration_ms must be a number"),
        ({"duration_ms": float("nan")}, "duration_ms must be a number"),
        ({"duration_ms": float("inf")}, "duration_ms must be a number"),
        ({"total_tokens": 1.5}, "total_tokens must be an integer"),
        ({"total_tokens": -5}, "total_tokens must be an integer"),
        ({"total_tokens": True}, "total_tokens must be an integer"),
        ({"total_tokens": 10**400}, "total_tokens must be an integer"),
    ],
)
def test_a_bad_time_or_token_value_is_a_config_error(capsys, tmp_path, extra, fragment):
    rows = [_row("C1", "baseline", "nope", **extra), _row("C1", "with_skill", "alpha")]

    code, payload = _score(capsys, tmp_path, [_case()], rows)

    assert code == 2
    assert fragment in payload["message"]
    assert "line 1" in payload["message"]


def test_null_time_and_zero_values_are_accepted(capsys, tmp_path):
    rows = [
        _row("C1", "baseline", "nope", duration_ms=None, total_tokens=0),
        _row("C1", "with_skill", "alpha", duration_ms=0),
    ]

    code, payload = _score(capsys, tmp_path, [_case()], rows)

    assert code == 0
    assert payload["benchmark"]["baseline"]["total_tokens"]["mean"] == 0.0
    assert payload["benchmark"]["baseline"]["duration_ms"]["n"] == 0


# --- evidence ----------------------------------------------------------------


def _detail(capsys, tmp_path, cases, rows):
    _, payload = _score(capsys, tmp_path, cases, rows, "--detail")
    return payload["runs"]


def test_detail_is_absent_unless_asked(capsys, tmp_path):
    _, payload = _score(
        capsys,
        tmp_path,
        [_case()],
        [_row("C1", "baseline", "x"), _row("C1", "with_skill", "alpha")],
    )

    assert "runs" not in payload


def test_contains_all_evidence_names_found_and_missing_terms(capsys, tmp_path):
    case = _case(grader={"kind": "contains_all", "terms": ["Alpha", "beta"]})
    rows = [_row("C1", "baseline", "ALPHA only"), _row("C1", "with_skill", "alpha and BETA")]

    runs = _detail(capsys, tmp_path, [case], rows)

    assert runs[0]["passed"] is False
    assert runs[0]["evidence"] == "found: Alpha; missing: beta"
    assert runs[1]["passed"] is True
    assert runs[1]["evidence"] == "found: Alpha, beta; missing: none"


def test_long_term_lists_and_terms_are_clipped(capsys, tmp_path):
    terms = [f"term{i}" for i in range(11)] + ["x" * 100]
    case = _case(grader={"kind": "contains_all", "terms": terms})

    runs = _detail(
        capsys, tmp_path, [case], [_row("C1", "baseline", ""), _row("C1", "with_skill", "")]
    )

    evidence = runs[0]["evidence"]
    assert "(+4 more)" in evidence
    assert "x" * 100 not in evidence


def test_a_long_term_is_clipped_with_an_ellipsis(capsys, tmp_path):
    case = _case(grader={"kind": "contains_all", "terms": ["y" * 100]})

    runs = _detail(
        capsys, tmp_path, [case], [_row("C1", "baseline", ""), _row("C1", "with_skill", "")]
    )

    assert runs[0]["evidence"] == f"found: none; missing: {'y' * 60}..."


def test_regex_evidence_says_matched_or_did_not_match(capsys, tmp_path):
    case = _case(grader={"kind": "regex", "pattern": r"v\d+"})
    rows = [_row("C1", "baseline", "none"), _row("C1", "with_skill", "see v12")]

    runs = _detail(capsys, tmp_path, [case], rows)

    assert runs[0]["evidence"] == r"pattern v\d+ did not match"
    assert runs[1]["evidence"].endswith(" matched")


STALE = {"kind": "json_set_f1", "key": "stale", "gold": ["a", "b"], "threshold": 0.8}


def _fence(body: str) -> str:
    return f"```json\n{body}\n```"


@pytest.mark.parametrize(
    ("output", "fragment"),
    [
        ("no block here", "no fenced json object"),
        (_fence('{"other": []}'), "key 'stale' is missing or not a list of strings"),
        (_fence('{"stale": "a"}'), "key 'stale' is missing or not a list of strings"),
        (_fence('{"stale": ["a", 1]}'), "key 'stale' is missing or not a list of strings"),
        (_fence('{"stale": ["a"]}'), "f1 0.67 (threshold 0.8); missing: b; extra: none"),
        (_fence('{"stale": ["a", "b", "z"]}'), "f1 0.80 (threshold 0.8); missing: none; extra: z"),
    ],
)
def test_json_set_f1_evidence_explains_the_score(capsys, tmp_path, output, fragment):
    runs = _detail(
        capsys,
        tmp_path,
        [_case(grader=STALE)],
        [_row("C1", "baseline", output), _row("C1", "with_skill", output)],
    )

    assert fragment in runs[0]["evidence"]


def test_evidence_follows_the_pass_flag_and_never_recomputes_it(capsys, tmp_path, monkeypatch):
    real = bootstrap_eval.compile_grader
    monkeypatch.setattr(
        bootstrap_eval,
        "compile_grader",
        lambda g: lambda out: None if out == "slow" else real(g)(out),
    )

    runs = _detail(
        capsys,
        tmp_path,
        [_case()],
        [_row("C1", "baseline", "slow"), _row("C1", "with_skill", "alpha")],
    )

    assert runs[0]["passed"] is None
    assert runs[0]["evidence"] == "ungraded: the regex grader timed out"


def test_runs_number_reps_per_case_and_condition_and_carry_timing(capsys, tmp_path):
    rows = [
        _row("C1", "baseline", "x", duration_ms=5),
        _row("C1", "baseline", "x", total_tokens=7),
        _row("C1", "with_skill", "alpha"),
    ]

    runs = _detail(capsys, tmp_path, [_case()], rows)

    assert [(r["condition"], r["rep"]) for r in runs] == [
        ("baseline", 1),
        ("baseline", 2),
        ("with_skill", 1),
    ]
    assert runs[0]["duration_ms"] == 5 and runs[0]["total_tokens"] is None
    assert runs[1]["total_tokens"] == 7
    assert "output" not in runs[0]


# --- signals -----------------------------------------------------------------


def _signals(capsys, tmp_path, baseline: list[str], with_skill: list[str]) -> list[str]:
    rows = [_row("C1", "baseline", o) for o in baseline]
    rows += [_row("C1", "with_skill", o) for o in with_skill]
    _, payload = _score(capsys, tmp_path, [_case()], rows)
    signals: list[str] = payload["cases"][0]["signals"]
    return signals


def test_a_case_that_never_passes_in_either_condition_is_flagged(capsys, tmp_path):
    assert _signals(capsys, tmp_path, ["x", "x"], ["y", "y"]) == ["never_passes"]


def test_a_gain_with_a_failing_baseline_carries_no_signal(capsys, tmp_path):
    assert _signals(capsys, tmp_path, ["x", "x"], ["alpha", "alpha"]) == []


def test_a_case_that_passes_everywhere_carries_no_signal(capsys, tmp_path):
    assert _signals(capsys, tmp_path, ["alpha"], ["alpha"]) == []


def test_mixed_baseline_reps_are_flagged_unstable(capsys, tmp_path):
    assert _signals(capsys, tmp_path, ["alpha", "x"], ["alpha", "alpha"]) == ["unstable_baseline"]


def test_mixed_with_skill_reps_are_flagged_unstable(capsys, tmp_path):
    assert _signals(capsys, tmp_path, ["x", "x"], ["alpha", "x"]) == ["unstable_with_skill"]


def test_both_conditions_can_be_unstable(capsys, tmp_path):
    result = _signals(capsys, tmp_path, ["alpha", "x"], ["alpha", "x"])

    assert result == ["unstable_baseline", "unstable_with_skill"]


def test_one_rep_cannot_be_unstable(capsys, tmp_path):
    assert _signals(capsys, tmp_path, ["x"], ["alpha"]) == []


def test_an_ungraded_run_does_not_fake_a_never_passes_signal(capsys, tmp_path, monkeypatch):
    real = bootstrap_eval.compile_grader
    monkeypatch.setattr(
        bootstrap_eval,
        "compile_grader",
        lambda g: lambda out: None if out == "slow" else real(g)(out),
    )

    assert _signals(capsys, tmp_path, ["slow"], ["x"]) == []


# --- draft cases -------------------------------------------------------------


def _draft(case_id: str = "D1", **extra: Any) -> dict[str, Any]:
    return _case(case_id, grader=None, expected_output="Names the stdlib module.", **extra)


def test_check_counts_graded_and_draft_cases(capsys, tmp_path):
    cases = _write(tmp_path / "c.json", {"cases": [_case("C1"), _draft("D1"), _draft("D2")]})

    code, payload = _run(capsys, "check", "--cases", str(cases))

    assert code == 0
    assert payload["examined"] == {"cases": 3, "graded": 1, "drafts": 2}
    assert payload["draft_ids"] == ["D1", "D2"]
    assert payload["skills"] == ["acme"]


def test_check_still_validates_a_grader_that_is_present(capsys, tmp_path):
    bad = _case("C1", grader={"kind": "regex", "pattern": ""})
    cases = _write(tmp_path / "c.json", {"cases": [bad, _draft()]})

    code, payload = _run(capsys, "check", "--cases", str(cases))

    assert code == 2
    assert "case C1" in payload["message"]


@pytest.mark.parametrize(
    ("case", "fragment"),
    [
        (_case("D1", grader=None), "needs expected_output"),
        (_case("D1", grader=None, expected_output="  "), "expected_output must be a non-empty"),
        (_case("D1", grader=None, expected_output=3), "expected_output must be a non-empty"),
        (_draft(unknown="x"), "unknown ['unknown']"),
        ({"id": "D1", "expected_output": "x"}, "missing"),
    ],
)
def test_check_refuses_a_malformed_draft(capsys, tmp_path, case, fragment):
    cases = _write(tmp_path / "c.json", {"cases": [case]})

    code, payload = _run(capsys, "check", "--cases", str(cases))

    assert code == 2
    assert fragment in payload["message"]


def test_check_refuses_duplicate_ids_and_a_missing_file(capsys, tmp_path):
    cases = _write(tmp_path / "c.json", {"cases": [_draft(), _draft()]})

    assert _run(capsys, "check", "--cases", str(cases))[0] == 2
    assert _run(capsys, "check", "--cases", str(tmp_path / "absent.json"))[0] == 2


def test_freeze_refuses_a_draft_and_names_the_next_step(capsys, tmp_path):
    cases = _write(tmp_path / "c.json", {"cases": [_draft()]})
    out = tmp_path / "out" / "frozen.json"

    code, payload = _run(capsys, "freeze", "--cases", str(cases), "--out", str(out))

    assert code == 2
    assert "draft with no grader" in payload["message"]
    assert not out.exists()


def test_freeze_without_grader_or_expected_output_keeps_the_old_message(capsys, tmp_path):
    case = _case("C1", grader=None)
    cases = _write(tmp_path / "c.json", {"cases": [case]})

    code, payload = _run(
        capsys, "freeze", "--cases", str(cases), "--out", str(tmp_path / "out" / "f.json")
    )

    assert code == 2
    assert "missing ['grader']" in payload["message"]


def test_a_graded_case_may_carry_expected_output_and_the_hash_covers_it(capsys, tmp_path):
    case = _case(expected_output="Names alpha.")
    frozen = _freeze(capsys, tmp_path, [case])
    record = json.loads(frozen.read_text(encoding="utf-8"))
    record["cases"][0]["expected_output"] = "Names beta."
    frozen.write_text(json.dumps(record), encoding="utf-8")
    results = tmp_path / "r.jsonl"
    results.write_text(json.dumps(_row("C1", "baseline", "x")) + "\n", encoding="utf-8")

    code, payload = _run(capsys, "score", "--frozen", str(frozen), "--results", str(results))

    assert code == 2
    assert "edited after freezing" in payload["message"]


def test_the_stats_helpers_treat_a_bool_and_a_negative_as_not_measurements():
    assert bootstrap_eval.is_measurement(0) is True
    assert bootstrap_eval.is_measurement(2.5) is True
    assert bootstrap_eval.is_measurement(True) is False
    assert bootstrap_eval.is_measurement(-0.1) is False
    assert bootstrap_eval.is_measurement(2.5, integer=True) is False
    assert bootstrap_eval.is_measurement(None) is False
    assert bootstrap_eval.spread([]) == {"n": 0, "mean": None, "stdev": None}

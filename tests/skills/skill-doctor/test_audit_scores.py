"""Tests for audit_scores: validation, Step 3 aggregation, strata pooling, CLI."""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import audit_scores as a
import pytest

EXPECTED_TABLES = {
    "efficiency": {
        "highly_efficient": 1,
        "mostly_efficient": 0.8,
        "mostly_inefficient": 0.4,
        "highly_inefficient": 0.2,
    },
    "code_quality": {"approve": 1, "block": 0.2, "insufficient_evidence": 0.5},
    "procedure_compliance": {"fully_compliant": 1, "mostly_compliant": 0.8, "noncompliant": 0.2},
    "verbosity": {"proportionate": 1, "verbose": 0.2, "terse": 0.1},
}


def result(scorer: str, label: str, **extra):
    r = {
        "label": label,
        "score": EXPECTED_TABLES[scorer][label],
        "reason": "synthetic reason",
        "evidence_ref": "t:1",
    }
    r.update(extra)
    return r


def session(
    sid,
    eff="highly_efficient",
    q="approve",
    proc="fully_compliant",
    verb="proportionate",
    detected=True,
    harness="h1",
    stratum=None,
    **extra,
):
    s = {
        "session_id": sid,
        "harness": harness,
        "skills_detected": detected,
        "scores": {
            "efficiency": result("efficiency", eff),
            "code_quality": result(
                "code_quality", q, **({"applicable": False} if q == "insufficient_evidence" else {})
            ),
            "procedure_compliance": result("procedure_compliance", proc),
            "verbosity": result("verbosity", verb),
        },
    }
    if stratum:
        s["stratum"] = stratum
    s.update(extra)
    return s


def expand(counts):
    return [label for label, n in counts for _ in range(n)]


def epic_sessions():
    eff = expand(
        [
            ("highly_efficient", 12),
            ("mostly_efficient", 34),
            ("mostly_inefficient", 94),
            ("highly_inefficient", 10),
        ]
    )
    qual = expand([("approve", 4), ("block", 2), ("insufficient_evidence", 144)])
    proc = expand([("fully_compliant", 140), ("mostly_compliant", 7), ("noncompliant", 3)])
    verb = expand([("proportionate", 130), ("verbose", 18), ("terse", 2)])
    return [
        session(f"s{i}", eff[i], qual[i], proc[i], verb[i], detected=i < 140) for i in range(150)
    ]


def test_label_tables_match_expected_constants():
    assert a.load_label_tables() == EXPECTED_TABLES


def test_epic_aggregate_fixture_exact():
    agg = a.aggregate(epic_sessions())
    d = agg["dimensions"]
    assert math.isclose(agg["overall"], 0.8867, abs_tol=1e-8)
    assert math.isclose(agg["overall"] * 100, 88.67, abs_tol=1e-8)
    assert math.isclose(agg["total_shortfall"], 11.33, abs_tol=1e-8)
    assert math.isclose(d["efficiency"]["weighted_shortfall"], 5.933333333333333, abs_tol=1e-8)
    assert math.isclose(d["code_quality"]["weighted_shortfall"], 3.3333333333333335, abs_tol=1e-8)
    assert math.isclose(
        d["procedure_compliance"]["weighted_shortfall"], 0.2533333333333, abs_tol=1e-8
    )
    assert math.isclose(d["verbosity"]["weighted_shortfall"], 0.81, abs_tol=1e-8)
    assert math.isclose(d["skill_coverage"]["weighted_shortfall"], 1.0, abs_tol=1e-8)
    parts = sum(x["weighted_shortfall"] for x in d.values())
    assert abs(parts - agg["total_shortfall"]) < 1e-8


def test_quality_fixture_exposes_six_applicable_not_144_failures():
    agg = a.aggregate(epic_sessions())
    q = agg["dimensions"]["code_quality"]
    assert (q["denominator"], q["inapplicable"]) == (6, 144)
    assert math.isclose(q["numerator"], 4.4)
    assert not q["fallback_used"]
    quality_failures = [
        s for s in epic_sessions() if s["scores"]["code_quality"]["label"] == "block"
    ]
    assert len(quality_failures) == 2


def test_insufficient_evidence_never_fails_conversation():
    s = [session("a", q="insufficient_evidence")]
    assert a.failed_conversations(s)["count"] == 0


def test_block_fails_conversation():
    out = a.failed_conversations([session("a", q="block"), session("b")])
    assert out["session_ids"] == ["a"]


def test_terminated_session_excluded_and_counted():
    s = session("t", verb="terse", terminated_by="usage_limit_exceeded")
    out = a.failed_conversations([s])
    assert (out["count"], out["excluded_count"]) == (0, 1)


def test_terminated_session_with_pre_cutoff_failure_counts():
    s = session("t", eff="highly_inefficient", terminated_by="server_overloaded")
    s["scores"]["efficiency"]["pre_cutoff"] = True
    out = a.failed_conversations([s])
    assert (out["count"], out["excluded_count"]) == (1, 0)


def test_zero_applicability_uses_fallback_and_limit():
    agg = a.aggregate([session("a", q="insufficient_evidence")])
    q = agg["dimensions"]["code_quality"]
    assert q["fallback_used"] is True
    assert q["raw"] == 0.5 and q["score"] == 0.75
    assert q["denominator"] == 0 and q["numerator"] == 0
    assert "fallback" in q["evidence_limit"]
    assert agg["fallback_used"] is True and agg["evidence_limits"]


def test_no_fallback_flag_when_evidence_exists():
    agg = a.aggregate([session("a")])
    assert agg["fallback_used"] is False and agg["evidence_limits"] == []


def stratum_records():
    """Stratum A has all quality applicable and bad; B has one good applicable of many."""
    a_recs = [session(f"a{i}", q="block", stratum="A") for i in range(4)]
    b_recs = [session("b0", q="approve", stratum="B")] + [
        session(f"b{i}", q="insufficient_evidence", stratum="B") for i in range(1, 20)
    ]
    return a_recs, b_recs


def test_pooled_differs_from_linear_pooling_of_stratum_grades():
    a_recs, b_recs = stratum_records()
    grade_a = a.aggregate(a_recs)["overall"]
    grade_b = a.aggregate(b_recs)["overall"]
    linear = (grade_a + grade_b) / 2
    pooled = a.pool_strata({"A": a_recs, "B": b_recs})["overall"]
    assert abs(pooled - linear) > 1e-4
    assert math.isclose(pooled, a.aggregate(a_recs + b_recs)["overall"])


def test_pool_strata_rejects_precomputed_grades():
    a_recs, _ = stratum_records()
    grade = a.aggregate(a_recs)
    with pytest.raises(TypeError):
        a.pool_strata({"A": grade})
    with pytest.raises(TypeError):
        a.pool_strata({"A": [{"overall": 0.9}]})


def test_artifact_combined_recomputed_not_averaged_and_subsets_independent():
    a_recs, b_recs = stratum_records()
    art = a.build_artifact(a_recs + b_recs)
    assert art["combined_source"] == "pooled_records"
    assert math.isclose(art["overall"], a.aggregate(a_recs + b_recs)["overall"])
    assert math.isclose(art["strata"]["A"]["overall"], a.aggregate(a_recs)["overall"])
    assert art["strata"]["B"]["dimensions"]["code_quality"]["denominator"] == 1
    avg = (art["strata"]["A"]["overall"] + art["strata"]["B"]["overall"]) / 2
    assert abs(art["overall"] - avg) > 1e-4


def test_per_harness_subsets():
    recs = [session("x1", harness="h1"), session("x2", harness="h2", eff="highly_inefficient")]
    art = a.build_artifact(recs)
    assert set(art["per_harness"]) == {"h1", "h2"}
    assert art["per_harness"]["h1"]["overall"] > art["per_harness"]["h2"]["overall"]
    assert art["strata"] == {}


def test_limitations_collected():
    art = a.build_artifact([session("x", limitations=["no diff"]), session("y")])
    assert art["limitations"] == ["no diff"]


def errors_for(sessions):
    return a.validate_sessions(sessions)


def test_valid_input_has_no_errors():
    assert errors_for([session("a"), session("b", q="insufficient_evidence")]) == []


def test_label_value_mismatch_fails():
    s = session("a")
    s["scores"]["efficiency"]["score"] = 0.9
    errs = errors_for([s])
    assert any("requires score" in e for e in errs)


def test_unknown_label_for_scorer_fails():
    s = session("a")
    s["scores"]["verbosity"]["label"] = "approve"
    assert any("unknown label" in e for e in errors_for([s]))


def test_insufficient_evidence_only_valid_for_code_quality():
    s = session("a")
    s["scores"]["efficiency"] = {
        "label": "insufficient_evidence",
        "score": 0.5,
        "reason": "x",
        "applicable": False,
    }
    assert any("unknown label" in e for e in errors_for([s]))


@pytest.mark.parametrize("reason", ["", "   ", None, 3])
def test_empty_reason_fails(reason):
    s = session("a")
    s["scores"]["verbosity"]["reason"] = reason
    assert any("reason" in e for e in errors_for([s]))


def test_insufficient_evidence_applicable_true_fails():
    s = session("a", q="insufficient_evidence")
    s["scores"]["code_quality"]["applicable"] = True
    assert any("applicable=false" in e for e in errors_for([s]))


def test_judged_label_marked_inapplicable_fails():
    s = session("a")
    s["scores"]["code_quality"]["applicable"] = False
    assert any("must have applicable=true" in e for e in errors_for([s]))


def test_applicable_must_be_bool():
    s = session("a")
    s["scores"]["code_quality"]["applicable"] = "yes"
    assert any("applicable must be a boolean" in e for e in errors_for([s]))


def test_duplicate_session_ids_fail():
    assert any("duplicate" in e for e in errors_for([session("a"), session("a")]))


def test_missing_and_unknown_scorer_fail():
    s = session("a")
    del s["scores"]["verbosity"]
    s["scores"]["bogus"] = {}
    errs = errors_for([s])
    assert any("missing scorer verbosity" in e for e in errs)
    assert any("unknown scorer bogus" in e for e in errs)


@pytest.mark.parametrize("bad", [[], None, {}, "x", [3], [{"harness": "h"}]])
def test_malformed_sessions_fail(bad):
    assert errors_for(bad)


def test_header_field_types_fail():
    s = session("a", terminated_by=5, limitations="no")
    s["skills_detected"] = "yes"
    s["harness"] = ""
    s["stratum"] = 3
    errs = errors_for([s])
    assert len(errs) >= 5


def test_result_not_object_and_bad_score_type_and_evidence_ref():
    s = session("a")
    s["scores"]["efficiency"] = "oops"
    s["scores"]["verbosity"]["score"] = True
    s["scores"]["procedure_compliance"]["evidence_ref"] = 5
    s["scores"]["code_quality"]["pre_cutoff"] = "y"
    errs = errors_for([s])
    assert any("must be an object" in e for e in errs)
    assert any("score must be a number" in e for e in errs)
    assert any("evidence_ref" in e for e in errs)
    assert any("pre_cutoff" in e for e in errs)


# CLI


def write_scores(tmp_path: Path, sessions, wrap=True) -> Path:
    p = tmp_path / "scores.json"
    p.write_text(json.dumps({"sessions": sessions} if wrap else sessions), encoding="utf-8")
    return p


def test_cli_ok_writes_artifact(tmp_path):
    src = write_scores(tmp_path, epic_sessions())
    out = tmp_path / "sub" / "artifact.json"
    assert a.main([str(src), "--out", str(out)]) == 0
    art = json.loads(out.read_text(encoding="utf-8"))
    assert math.isclose(art["total_shortfall"], 11.33, abs_tol=1e-8)
    assert list(tmp_path.glob("sub/.audit_scores.*")) == []


def test_cli_stdout_and_bare_list(tmp_path, capsys):
    src = write_scores(tmp_path, [session("a")], wrap=False)
    assert a.main([str(src)]) == 0
    assert json.loads(capsys.readouterr().out)["sessions_scored"] == 1


def test_cli_validation_failure_exit_1_writes_nothing(tmp_path, capsys):
    bad = session("a")
    bad["scores"]["efficiency"]["score"] = 0.9
    src = write_scores(tmp_path, [bad])
    out = tmp_path / "artifact.json"
    assert a.main([str(src), "--out", str(out)]) == 1
    assert "requires score" in capsys.readouterr().err
    assert not out.exists()


def test_cli_bad_args_exit_2(capsys):
    assert a.main([]) == 2
    assert a.main(["--nope"]) == 2


def test_cli_unreadable_and_invalid_json_exit_2(tmp_path):
    assert a.main([str(tmp_path / "missing.json")]) == 2
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert a.main([str(broken)]) == 2


def test_cli_unwritable_out_exit_2(tmp_path):
    src = write_scores(tmp_path, [session("a")])
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    assert a.main([str(src), "--out", str(blocker / "child.json")]) == 2


def test_load_label_table_rejects_bad_rubric(tmp_path):
    p = tmp_path / "x.md"
    p.write_text("no frontmatter", encoding="utf-8")
    with pytest.raises(a.ScoreInputError):
        a.load_label_table(p)
    p.write_text("---\nname: x\n---\n", encoding="utf-8")
    with pytest.raises(a.ScoreInputError):
        a.load_label_table(p)


def test_inputs_not_mutated():
    recs = epic_sessions()[:10]
    snap = copy.deepcopy(recs)
    a.build_artifact(recs)
    assert recs == snap

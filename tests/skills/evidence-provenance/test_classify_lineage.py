"""Lineage classification: independence, authority, states, and binding."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import classify_lineage
import pytest
from evidence_fixtures import FIXTURES, load_fixture

SCENARIOS = sorted(p.stem for p in FIXTURES.glob("*.json"))


def run_main(
    path: Path, capsys: pytest.CaptureFixture[str], *extra: str
) -> tuple[int, dict[str, Any]]:
    code = classify_lineage.main([str(path), *extra])
    out = capsys.readouterr().out
    return code, (json.loads(out) if out else {})


def write(tmp_path: Path, record: dict[str, Any]) -> Path:
    path = tmp_path / "record.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def subject(**overrides: object) -> dict[str, Any]:
    base = {"artifact": "pkg", "revision": "r2", "premises": ["interp:R"]}
    return {**base, **overrides}


def item(item_id: str, state: str = "VERIFIED", **fields: object) -> dict[str, Any]:
    return {"id": item_id, "state": state, **fields}


@pytest.mark.parametrize("name", SCENARIOS)
def test_fixture_matches_its_expected_classification(
    name: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    record = load_fixture(name)
    expect = record["expect"]
    extra = ("--promotion",) if expect.get("promotion") else ()
    code, report = run_main(FIXTURES / f"{name}.json", capsys, *extra)

    assert code == expect["exit"]
    for key in ("verdict", "independent_loops", "authoritative_independent_loops"):
        if key in expect:
            assert report[key] == expect[key], key
    if "violations" in expect:
        assert [v["rule"] for v in report["violations"]] == expect["violations"]
    if "rejected" in expect:
        assert {r["id"]: r["reason"] for r in report["rejected"]} == expect["rejected"]
    if "loops" in expect:
        assert {r["id"]: r["loop"] for r in report["evidence"]} == expect["loops"]
    if "discriminating" in expect:
        assert [r["id"] for r in report["evidence"] if r["discriminating"]] == expect[
            "discriminating"
        ]
    for item_id, reasons in expect.get("not_independent_because", {}).items():
        row = next(r for r in report["evidence"] if r["id"] == item_id)
        assert row["not_independent_because"] == reasons


def test_every_issue_scenario_has_a_fixture() -> None:
    required = {
        "s1_same_interpretation",
        "s2_preexisting_red_to_green",
        "s3_mutation_restoration",
        "s4_shared_generator",
        "s5_runtime_contradicts_generated",
        "s6_reviewer_inherits_conclusion",
        "s7_reviewer_reconstructs",
        "s8_should_run_pending",
        "s9_unavailable_reported",
        "c1_negative_control_doubled_confidence",
    }
    assert required <= set(SCENARIOS)


def test_a_second_agent_is_not_independent_because_it_is_a_second_agent(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Same record, one field changed: only the inherited premise differs."""
    inherited = load_fixture("s6_reviewer_inherits_conclusion")
    reconstructed = load_fixture("s6_reviewer_inherits_conclusion")
    reconstructed["evidence"][1]["inherits_from"] = []
    inherited_report = classify_lineage.classify(inherited, promotion=False)
    reconstructed_report = classify_lineage.classify(reconstructed, promotion=False)

    assert inherited_report["independent_loops"] == 0
    assert reconstructed_report["independent_loops"] == 1
    assert inherited["evidence"][1]["origin"] == "independent-reviewer"


def test_creator_tests_stay_valid_evidence_in_the_subject_loop() -> None:
    report = classify_lineage.classify(load_fixture("s1_same_interpretation"), promotion=False)

    assert report["verdict"] == "SINGLE_LOOP"
    assert all(row["state"] == "VERIFIED" for row in report["evidence"])


def test_independence_and_authority_are_separate_axes() -> None:
    record = {
        "subject": subject(),
        "evidence": [
            item("weak-independent", premises=["obs:a"], origin="human", authority="heuristic"),
            item("strong-same-loop", premises=["interp:R"], authority="executable-runtime"),
        ],
    }
    rows = {r["id"]: r for r in classify_lineage.classify(record, False)["evidence"]}

    assert rows["weak-independent"]["independent"] and not rows["weak-independent"]["authoritative"]
    assert rows["strong-same-loop"]["authoritative"] and not rows["strong-same-loop"]["independent"]


def test_weak_independent_evidence_counts_as_loop_but_not_authoritative() -> None:
    record = {"subject": subject(), "evidence": [item("e", premises=["obs:a"], origin="human")]}
    report = classify_lineage.classify(record, False)

    assert (report["independent_loops"], report["authoritative_independent_loops"]) == (1, 0)


def test_two_independent_items_sharing_a_premise_are_one_loop() -> None:
    record = {
        "subject": subject(),
        "evidence": [
            item("a", premises=["spec:ext"], origin="pre-existing", created="pre-existing"),
            item("b", premises=["spec:ext"], origin="pre-existing", created="pre-existing"),
        ],
    }

    assert classify_lineage.classify(record, False)["independent_loops"] == 1


def test_a_preexisting_test_the_subject_edited_is_not_independent() -> None:
    record = {
        "subject": subject(),
        "evidence": [
            item(
                "edited-legacy",
                premises=["contract:ext"],
                origin="pre-existing",
                created="pre-existing",
                changed_by_subject=True,
            )
        ],
    }
    row = classify_lineage.classify(record, False)["evidence"][0]

    assert row["not_independent_because"] == ["changed-by-subject"]


def test_same_origin_observation_of_a_real_runtime_is_independent() -> None:
    record = {
        "subject": subject(),
        "evidence": [item("ran-it", premises=["obs:runtime"], environment="real")],
    }

    assert classify_lineage.classify(record, False)["independent_loops"] == 1


def test_same_origin_synthetic_fixture_with_new_premise_is_still_not_independent() -> None:
    record = {"subject": subject(), "evidence": [item("fx", premises=["fixture:new"])]}
    row = classify_lineage.classify(record, False)["evidence"][0]

    assert row["not_independent_because"] == ["same-origin-synthetic"]


def test_independent_failure_without_authority_does_not_falsify() -> None:
    record = {
        "subject": subject(),
        "evidence": [item("opinion", "FAILED", premises=["obs:x"], origin="human")],
    }

    assert classify_lineage.classify(record, False)["verdict"] == "FAILED"


def test_not_run_and_unavailable_items_never_corroborate() -> None:
    record = {
        "subject": subject(),
        "evidence": [
            item("a", "NOT RUN", premises=["obs:a"], origin="human"),
            item("b", "UNAVAILABLE", premises=["obs:b"], origin="human"),
        ],
    }
    report = classify_lineage.classify(record, False)

    assert (report["verdict"], report["independent_loops"]) == ("NO_VERIFIED_EVIDENCE", 0)


def test_unverified_evidence_used_as_support_is_a_violation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    record = {"subject": subject(), "evidence": [item("e", "NOT RUN", used_as_support=True)]}
    code, report = run_main(write(tmp_path, record), capsys)

    assert code == 1
    assert report["violations"] == [{"rule": "unverified-support", "subject": "e"}]


def test_a_named_check_that_is_not_run_but_not_used_is_honest_with_a_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    record = {
        "subject": subject(),
        "checks": [{"check": "ruff", "state": "NOT RUN", "cheap": True, "available": True}],
    }
    code, report = run_main(write(tmp_path, record), capsys)

    assert code == 0
    assert report["warnings"] == [{"rule": "cheap-gate-not-run", "subject": "ruff"}]


def test_a_failed_check_used_as_support_is_a_violation() -> None:
    record = {
        "subject": subject(),
        "checks": [{"check": "lint", "state": "FAILED", "used_as_support": True}],
    }

    assert classify_lineage.classify(record, False)["violations"] == [
        {"rule": "unverified-support", "subject": "lint"}
    ]


def test_a_verified_check_used_as_support_passes() -> None:
    record = {
        "subject": subject(),
        "checks": [{"check": "lint", "state": "VERIFIED", "used_as_support": True}],
    }

    assert classify_lineage.classify(record, False)["violations"] == []


def test_classification_survives_a_handoff_round_trip() -> None:
    record = load_fixture("s7_reviewer_reconstructs")
    first = classify_lineage.classify(record, False)
    second = classify_lineage.classify(json.loads(json.dumps(record)), False)

    assert first == second


def no_grouping(subj: dict[str, Any], items: list[Any]) -> classify_lineage.LoopMap:
    return classify_lineage.LoopMap(["subject", *[i.id for i in items]])


def test_negative_control_bypassing_the_rule_allows_doubled_confidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With the whole rule removed, the doubled claim passes: the rule is what blocks it."""
    record = load_fixture("c1_negative_control_doubled_confidence")
    guarded = classify_lineage.classify(record, False)

    monkeypatch.setattr(classify_lineage, "build_loops", no_grouping)
    monkeypatch.setattr(classify_lineage, "independence_reasons", lambda item, in_loop: [])
    bypassed = classify_lineage.classify(record, False)

    assert guarded["violations"] and guarded["independent_loops"] == 0
    assert bypassed["violations"] == [] and bypassed["independent_loops"] == 2


def test_loop_grouping_alone_stops_an_inheriting_second_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The origin check does not catch a reviewer agent; only premise grouping does."""
    record = load_fixture("s6_reviewer_inherits_conclusion")
    guarded = classify_lineage.classify(record, False)

    monkeypatch.setattr(classify_lineage, "build_loops", no_grouping)
    bypassed = classify_lineage.classify(record, False)

    assert guarded["independent_loops"] == 0 and guarded["violations"]
    assert bypassed["independent_loops"] == 1 and bypassed["violations"] == []


def test_naive_item_count_doubles_what_the_classifier_counts() -> None:
    record = load_fixture("c1_negative_control_doubled_confidence")
    naive = sum(1 for e in record["evidence"] if e["state"] == "VERIFIED")

    assert naive == 2
    assert classify_lineage.classify(record, False)["independent_loops"] == 0


def test_binding_is_optional_outside_promotion() -> None:
    record = {"subject": subject(), "evidence": [item("e", premises=["obs:a"], origin="human")]}

    assert classify_lineage.classify(record, False)["rejected"] == []
    assert classify_lineage.classify(record, True)["rejected"] == [
        {"id": "e", "reason": "binding-missing"}
    ]


def test_rejected_item_cannot_link_loops_or_count() -> None:
    record = load_fixture("x1_stale_revision")
    record["evidence"].append(item("child", premises=["interp:R"], inherits_from=["old-run"]))
    report = classify_lineage.classify(record, False)

    assert [r["id"] for r in report["evidence"]] == ["child"]
    assert report["rejected"][0]["id"] == "old-run"


def test_inheritance_from_a_rejected_item_is_not_independent() -> None:
    record = load_fixture("x7_inherits_stale_revision")
    report = classify_lineage.classify(record, False)
    row = report["evidence"][0]

    assert row["id"] == "second-agent-review"
    assert row["independent"] is False
    assert report["independent_loops"] == 0


def test_inheritance_taint_follows_a_chain_through_accepted_items() -> None:
    record = load_fixture("x7_inherits_stale_revision")
    record["evidence"].append(
        item(
            "third-review",
            premises=["review:r2"],
            origin="human",
            inherits_from=["second-agent-review"],
        )
    )
    report = classify_lineage.classify(record, False)
    reasons = {r["id"]: r["not_independent_because"] for r in report["evidence"]}

    assert reasons["third-review"] == ["inherits-rejected-evidence"]
    assert report["independent_loops"] == 0


def test_inheriting_an_accepted_independent_item_stays_independent() -> None:
    record = {
        "subject": subject(),
        "evidence": [
            item("base", premises=["obs:a"], origin="human"),
            item("child", premises=["obs:b"], origin="human", inherits_from=["base"]),
        ],
    }
    report = classify_lineage.classify(record, False)

    assert [r["independent"] for r in report["evidence"]] == [True, True]


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda r: r.pop("subject"), "subject is required"),
        (lambda r: r["evidence"][0].update(state="PASSED"), "state must be one of"),
        (lambda r: r["evidence"][0].update(origin="alien"), "origin must be one of"),
        (lambda r: r["evidence"][0].update(id=""), "needs a string id"),
        (lambda r: r["evidence"][0].update(id="subject"), "reserved"),
        (lambda r: r["evidence"][0].update(inherits_from=["ghost"]), "unknown ids"),
        (lambda r: r["evidence"].append(dict(r["evidence"][0])), "unique"),
        (lambda r: r.update(evidence="nope"), "evidence must be a list"),
        (lambda r: r.update(evidence=["nope"]), "must be an object"),
        (lambda r: r["evidence"][0].update(bound_to="x"), "bound_to must be an object"),
        (lambda r: r["evidence"][0].update(premises="x"), "list of strings"),
        (lambda r: r.update(checks="x"), "checks must be a list"),
        (lambda r: r.update(checks=[{"state": "VERIFIED"}]), "string 'check'"),
    ],
)
def test_malformed_input_is_a_config_error(
    mutate, message: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    record = {"subject": subject(), "evidence": [item("e", premises=["obs:a"])]}
    mutate(record)
    code = classify_lineage.main([str(write(tmp_path, record))])
    captured = capsys.readouterr()

    assert code == 2
    assert message in captured.err
    assert captured.out == ""


def test_missing_file_and_non_object_json_are_config_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert classify_lineage.main([str(tmp_path / "absent.json")]) == 2
    array = tmp_path / "array.json"
    array.write_text("[]", encoding="utf-8")
    assert classify_lineage.main([str(array)]) == 2
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    assert classify_lineage.main([str(bad)]) == 2
    assert "cannot read JSON" in capsys.readouterr().err


def test_script_runs_as_a_fresh_interpreter_and_returns_the_gate_exit_code() -> None:
    script = Path(classify_lineage.__file__)
    clean = FIXTURES / "s2_preexisting_red_to_green.json"
    inflated = FIXTURES / "c1_negative_control_doubled_confidence.json"

    ok = subprocess.run(
        [sys.executable, "-I", str(script), str(clean)], capture_output=True, text=True
    )
    bad = subprocess.run(
        [sys.executable, "-I", str(script), str(inflated)], capture_output=True, text=True
    )

    assert ok.returncode == 0 and json.loads(ok.stdout)["verdict"] == "CORROBORATED"
    assert bad.returncode == 1 and "inflated-confidence" in bad.stdout

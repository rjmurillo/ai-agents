"""Tests for scripts/eval/eval_longitudinal_pilot.py and _longitudinal_pilot.py (issue #6993).

No test spawns a model. Live-path tests inject a fake runner or fail before any spawn.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import pytest

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import _longitudinal_pilot as lp  # noqa: E402
import _longitudinal_report as rep  # noqa: E402
import eval_longitudinal_pilot as cli  # noqa: E402

from tests.eval._longitudinal_test_support import (  # noqa: E402
    PILOT_PATH,
    SENTINEL,
    fake_checkout,
    report_of,
    runs,
)


@pytest.fixture
def pilot() -> dict[str, Any]:
    return lp.load_pilot(PILOT_PATH)


# ---- pilot file ----


def test_shipped_pilot_loads(pilot: dict[str, Any]) -> None:
    assert [t["role"] for t in pilot["tasks"]] == [
        "seed",
        "correction_source",
        "related",
        "stale_trap",
        "held_out",
    ]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["tasks"].append(copy.deepcopy(d["tasks"][0])),
        lambda d: d["tasks"][0].update(grader="pairs_f1"),
        lambda d: d["tasks"][0].update(gold=[]),
        lambda d: d["tasks"][0].update(decision_points=-1),
        lambda d: d["tasks"][2].update(uses_correction="NOPE"),
        lambda d: d["tasks"][3].update(uses_fact="NOPE"),
        lambda d: d["tasks"][0].update(followup_of="T9"),
        lambda d: d["tasks"].append({**copy.deepcopy(d["tasks"][0]), "id": "late", "phase": "pre"}),
        lambda d: d["local_context"].update(facts=[]),
        lambda d: d["repo_change"].update(rename=["only-one"]),
    ],
)
def test_invalid_pilot_rejected(pilot: dict[str, Any], tmp_path: Path, mutate: Any) -> None:
    mutate(pilot)
    path = tmp_path / "p.json"
    path.write_text(json.dumps(pilot), encoding="utf-8")
    with pytest.raises(lp.PilotError):
        lp.load_pilot(path)


def test_unapproved_correction_cannot_be_used(pilot: dict[str, Any], tmp_path: Path) -> None:
    pilot["tasks"][1]["correction"]["approved"] = False
    path = tmp_path / "p.json"
    path.write_text(json.dumps(pilot), encoding="utf-8")
    with pytest.raises(lp.PilotError, match="uses_correction"):
        lp.load_pilot(path)


def test_unreadable_pilot(tmp_path: Path) -> None:
    with pytest.raises(lp.PilotError):
        lp.load_pilot(tmp_path / "missing.json")


# ---- gold is re-derivable (the verifier is real) ----


def _synthetic_tree(root: Path, pilot: dict[str, Any], phase: str) -> None:
    """Write files so each task's gold_probe re-derives exactly its gold."""
    eval_dir = root / "scripts" / "eval"
    eval_dir.mkdir(parents=True, exist_ok=True)
    for task in pilot["tasks"]:
        if task["phase"] != phase:
            continue
        sample = {
            "_human_minutes": "_human_minutes",
            "parse_record": "parse_record(",
            "HumanMinutesError": "class HumanMinutesError",
            "DurableOutcomeError": "class DurableOutcomeError",
        }
        for gold in task["gold"]:
            path = root / gold
            body = path.read_text(encoding="utf-8") if path.exists() else ""
            for needle, line in sample.items():
                if (
                    needle in task["gold_probe"]["pattern"]
                    and (needle != "HumanMinutesError" or "human_minutes" in gold)
                    and (needle != "DurableOutcomeError" or "outcome" in gold)
                ):
                    body += (
                        line + "\n" if not line.startswith("class") else line + "(ValueError):\n"
                    )
            if needle == "parse_record" and task["id"] == "T2-correction-source":
                body = "def parse_record(x):\n"
            path.write_text(body, encoding="utf-8")


def test_gold_is_rederivable_from_a_tree(pilot: dict[str, Any], tmp_path: Path) -> None:
    pilot["tasks"] = [t for t in pilot["tasks"] if t["id"] in ("T1-seed", "T4-stale-trap")]
    pilot["tasks"][1].pop("uses_fact")
    for phase in ("pre", "post"):
        _synthetic_tree(tmp_path, pilot, phase)
    assert cli._verify_gold(pilot, tmp_path, "pre") == []
    assert cli._verify_gold(pilot, tmp_path, "post") == []


def test_wrong_gold_is_reported(pilot: dict[str, Any], tmp_path: Path) -> None:
    (tmp_path / "scripts" / "eval").mkdir(parents=True)
    pilot["tasks"][0]["gold"] = ["scripts/eval/nope.py"]
    assert "T1-seed" in cli._verify_gold(pilot, tmp_path, "pre")


# ---- grading ----


def test_grade_exact_missing_extra_and_unanswered(pilot: dict[str, Any]) -> None:
    task = pilot["tasks"][4]
    key = task["answer_key"]
    exact = lp.grade_task(task, {key: task["gold"]})
    assert exact["accepted"] and exact["missing"] == 0 and exact["extra"] == 0
    partial = lp.grade_task(task, {key: [task["gold"][0], "scripts/eval/other.py"]})
    assert not partial["accepted"] and (partial["missing"], partial["extra"]) == (1, 1)
    none = lp.grade_task(task, None)
    assert none["answered"] is False and none["missing"] == len(task["gold"])
    assert lp.grade_task(task, {key: "not a list"})["answered"] is False


def test_grade_ignores_excluded_files_and_line_suffixes(pilot: dict[str, Any]) -> None:
    task = pilot["tasks"][0]
    answer = {
        task["answer_key"]: [
            *(g + ":12" for g in task["gold"]),
            "scripts/eval/eval_longitudinal_pilot.py",
        ]
    }
    assert lp.grade_task(task, answer)["accepted"]


def test_clarification_counts_prose_questions_only() -> None:
    text = 'Which one do you mean?\nOk.\n```json\n{"a": "why?"}\n```\nAnd also this?'
    assert lp.count_clarifications(text) == 2
    assert lp.count_clarifications("") == 0
    assert lp.count_clarifications("```json\nq?") == 0


# ---- context, corrections, stale detection ----


def test_baseline_gets_no_context(pilot: dict[str, Any], tmp_path: Path) -> None:
    ctx = lp.build_context(pilot, lp.BASELINE, pilot["tasks"][0], lp.PilotState(), tmp_path)
    assert ctx.text == "" and ctx.fact_ids == [] and ctx.tokens_est == 0


def test_stale_fact_is_withheld_and_flagged_after_the_change(
    pilot: dict[str, Any], tmp_path: Path
) -> None:
    root = fake_checkout(tmp_path, pilot)
    pre = lp.build_context(pilot, "local_context", pilot["tasks"][0], lp.PilotState(), root)
    post = lp.build_context(pilot, "local_context", pilot["tasks"][3], lp.PilotState(), root)
    assert pre.stale_fact_ids == [] and "F1" in pre.fact_ids
    assert post.stale_fact_ids == ["F1"] and "F1" not in post.fact_ids
    assert "_human_minutes.py" not in post.text.split("Withheld")[0]
    assert "Withheld as stale" in post.text


def test_real_removal_is_detected_without_the_overlay(
    pilot: dict[str, Any], tmp_path: Path
) -> None:
    root = fake_checkout(tmp_path, pilot)
    (root / pilot["repo_change"]["rename"][0]).unlink()
    ctx = lp.build_context(pilot, "local_context", pilot["tasks"][0], lp.PilotState(), root)
    assert ctx.stale_fact_ids == ["F1"]


def test_unknown_probe_kind_fails_loud() -> None:
    with pytest.raises(lp.PilotError):
        lp.probe_ok({"grep": "x"}, Path("."), frozenset())


def test_retained_correction_reaches_later_task_only_when_approved(
    pilot: dict[str, Any], tmp_path: Path
) -> None:
    state = lp.PilotState()
    state.retain(pilot["tasks"][1])
    ctx = lp.build_context(pilot, "local_context", pilot["tasks"][2], state, tmp_path)
    assert ctx.correction_ids == ["C1"] and "parse_record is defined" in ctx.text
    unapproved = lp.PilotState()
    task = copy.deepcopy(pilot["tasks"][1])
    task["correction"]["approved"] = False
    unapproved.retain(task)
    assert unapproved.corrections == {}


def test_stale_context_check_fails_when_a_stale_fact_is_reused(
    pilot: dict[str, Any], tmp_path: Path
) -> None:
    records, _ = runs(pilot, tmp_path, cli.scripted_runner(pilot))
    assert report_of(pilot, records)["stale_context"][0]["result"] == "pass"
    for r in records:
        if r["condition"] == "local_context" and r["task_id"] == "T4-stale-trap":
            r["context"] = {**r["context"], "fact_ids": ["F1", "F2"], "stale_fact_ids": []}
    check = report_of(pilot, records)["stale_context"][0]
    assert (
        check["result"] == "fail"
        and check["missed"] == ["F1"]
        and check["silently_reused"] == ["F1"]
    )


# ---- full dry run ----


def test_dry_run_reports_gain_and_keeps_baseline_visible(
    pilot: dict[str, Any], tmp_path: Path
) -> None:
    records, window = runs(pilot, tmp_path, cli.scripted_runner(pilot))
    report = report_of(pilot, records)
    assert report["baseline"] == "vendor_only"
    assert list(report["conditions"]) == ["vendor_only", "local_context"]
    assert report["verdict"] == "local_context_improves_outcome"
    corr = report["retained_correction"][0]
    assert corr["result"] == "gain" and corr["local_f1"] > corr["baseline_f1"]
    assert report["production_claim"]["made"] is False
    assert report["limitations"] and window["elapsed_s"] >= 0


def test_no_gain_is_reported_when_conditions_tie(pilot: dict[str, Any], tmp_path: Path) -> None:
    same = copy.deepcopy(pilot)
    same["dry_run_script"]["local_context"] = copy.deepcopy(same["dry_run_script"]["vendor_only"])
    records, _ = runs(same, tmp_path, cli.scripted_runner(same))
    report = report_of(same, records)
    assert report["retained_correction"][0]["result"] == "no_gain"
    assert report["verdict"] == "no_gain"


def test_worse_verdict(pilot: dict[str, Any], tmp_path: Path) -> None:
    swapped = copy.deepcopy(pilot)
    script = swapped["dry_run_script"]
    script["vendor_only"], script["local_context"] = script["local_context"], script["vendor_only"]
    records, _ = runs(swapped, tmp_path, cli.scripted_runner(swapped))
    assert report_of(swapped, records)["verdict"] == "worse"


def test_human_minutes_unknown_is_never_zero(pilot: dict[str, Any], tmp_path: Path) -> None:
    records, _ = runs(pilot, tmp_path, cli.scripted_runner(pilot))
    assert all(r["human_minutes"] is None for r in records)
    local = report_of(pilot, records)["conditions"]["local_context"]
    assert local["human_active_correction_minutes"] == {
        "total": None,
        "timed_cells": 0,
        "unknown_cells": 5,
    }


def test_timed_minutes_including_zero_are_kept(pilot: dict[str, Any], tmp_path: Path) -> None:
    minutes = {
        ("local_context", "T1-seed", 0): 0.0,
        ("local_context", "T2-correction-source", 0): 4.5,
    }
    records, _ = runs(pilot, tmp_path, cli.scripted_runner(pilot), minutes=minutes)
    block = report_of(pilot, records)["conditions"]["local_context"][
        "human_active_correction_minutes"
    ]
    assert block == {"total": 4.5, "timed_cells": 2, "unknown_cells": 3}


def test_cost_split_marks_unmeasured_components(pilot: dict[str, Any], tmp_path: Path) -> None:
    records, _ = runs(pilot, tmp_path, cli.scripted_runner(pilot))
    cost = report_of(pilot, records)["conditions"]["local_context"]["cost"]
    assert set(lp.COST_COMPONENTS) <= set(cost)
    assert cost["total_usd"] is None and "retrieval_usd" in cost["unknown_components"]


def test_cost_split_sums_when_measured(pilot: dict[str, Any], tmp_path: Path) -> None:
    def runner(
        condition: str, task: dict[str, Any], prompt: str, root: Path, model: str
    ) -> dict[str, Any]:
        out = cli.scripted_runner(pilot)(condition, task, prompt, root, model)
        return {**out, "cost_usd": 0.01, "wall_s": 2.0}

    records, _ = runs(pilot, tmp_path, runner)
    report = rep.build_report(pilot, records, {}, {"elapsed_s": 40.0}, None, 0.05, "test")
    local = report["conditions"]["local_context"]
    assert local["cost"]["bootstrap_usd"] == 0.05
    assert local["cost"]["execution_usd"] == pytest.approx(0.04)
    assert local["cost"]["rework_usd"] == pytest.approx(0.01)
    assert local["cost"]["total_usd"] is None  # retrieval is still unknown
    assert report["time_split"] == {"elapsed_s": 40.0, "active_s": 20.0, "waiting_s": 20.0}


def test_published_records_hold_no_transcript(pilot: dict[str, Any], tmp_path: Path) -> None:
    def runner(
        condition: str, task: dict[str, Any], prompt: str, root: Path, model: str
    ) -> dict[str, Any]:
        out = cli.scripted_runner(pilot)(condition, task, prompt, root, model)
        return {**out, "result": f"{SENTINEL}\n{out['result']}"}

    records, _ = runs(pilot, tmp_path / "c", runner)
    cli._write(tmp_path / "out", records, report_of(pilot, records))
    published = (tmp_path / "out" / "records.jsonl").read_text() + (
        tmp_path / "out" / "report.json"
    ).read_text()
    assert SENTINEL not in published and "scripts/eval/_outcome_record.py" not in published
    assert all("result" not in r for r in records)


def test_error_cell_makes_run_incomplete(pilot: dict[str, Any], tmp_path: Path) -> None:
    def runner(
        condition: str, task: dict[str, Any], prompt: str, root: Path, model: str
    ) -> dict[str, Any]:
        out = cli.scripted_runner(pilot)(condition, task, prompt, root, model)
        return (
            {**out, "is_error": True, "error_kind": "timeout"}
            if task["id"] == "T3-related"
            else out
        )

    records, _ = runs(pilot, tmp_path, runner)
    report = report_of(pilot, records)
    assert report["complete"] is False and report["verdict"] == "inconclusive_incomplete"

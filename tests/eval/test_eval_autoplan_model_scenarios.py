"""Tests for the model-driven autoplan route scenarios (issue #6290, part 2).

Nothing here calls a model. The tests load and validate the scenario file,
feed synthetic run results through the scorer, and drive the unchanged
`eval-rule-activation.py` in `--dry-run`, which makes no API call.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "eval_autoplan_routes", _ROOT / "scripts" / "eval" / "eval_autoplan_routes.py"
)
assert _spec is not None and _spec.loader is not None
ev = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = ev
_spec.loader.exec_module(ev)

SCENARIO_FILE = ev.DEFAULT_MODEL_SCENARIOS
RUNNER = _ROOT / "scripts" / "eval" / "eval-rule-activation.py"


def _raw() -> dict[str, Any]:
    return json.loads(SCENARIO_FILE.read_text(encoding="utf-8"))


def _write(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "autoplan.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _result(sid: str, score: float | None, **cell: Any) -> dict[str, Any]:
    scores: dict[str, Any] = {} if score is None else {"cell_score": score}
    scores.update(cell.pop("scores", {}))
    return {"id": sid, "mechanisms": {"full": {"scores": scores, **cell}}}


def _results_file(tmp_path: Path, items: list[dict[str, Any]]) -> Path:
    path = tmp_path / "run.json"
    path.write_text(json.dumps({"rules": {"autoplan": {"scenarios": items}}}), encoding="utf-8")
    return path


def test_shipped_file_loads_and_covers_every_family() -> None:
    scenarios = ev.load_model_scenarios(SCENARIO_FILE)
    assert {s.family for s in scenarios} == set(ev.MODEL_FAMILIES)


def test_every_scenario_has_a_route_and_a_negative_constraint() -> None:
    for s in ev.load_model_scenarios(SCENARIO_FILE):
        assert s.expected_route, s.id
        assert s.forbidden_routes, s.id


def test_every_named_route_is_installed() -> None:
    model = ev.evaluate_model(ev.load_model_scenarios(SCENARIO_FILE), None)
    assert model["unreachable"] == []
    for counts in model["families"].values():
        assert counts["reachable"] == counts["scenarios"]


def test_forbidden_routes_are_named_in_the_rationale() -> None:
    raw = _raw()["scenarios"]
    for item in raw:
        text = (item["rationale"] + item["desc"]).lower()
        for route in item["forbidden_routes"]:
            assert route.lower() in text, f"{item['id']}: rationale omits {route}"


def test_expected_routes_are_signals_the_judge_looks_for() -> None:
    for item in _raw()["scenarios"]:
        if item["expected_gate"] == "skip-rule-not-applicable":
            continue
        signals = " ".join(item["expected_signals"]).lower()
        assert any(r.lower() in signals for r in item["expected_route"]), item["id"]


def test_composition_scenarios_carry_the_issue_orders() -> None:
    orders = {s.id: s.expected_order for s in ev.load_model_scenarios(SCENARIO_FILE)}
    assert orders["R7"] == ("analysis-provenance", "validation-authority")
    assert orders["R8"] == ("context-gather", "ai-agents-external-claims", "incorporation")


def test_issue_named_skills_appear_in_scenarios() -> None:
    named = {r for s in ev.load_model_scenarios(SCENARIO_FILE) for r in s.expected_route}
    assert {
        "ai-agents-external-claims",
        "analysis-provenance",
        "validation-authority",
        "dx-review",
        "programming-advisor",
        "buy-vs-build-framework",
    } <= named


def test_dx_family_has_a_positive_and_a_negative_case() -> None:
    gates = {i["expected_gate"] for i in _raw()["scenarios"] if i["family"] == "dx-activation"}
    assert "skip-rule-not-applicable" in gates
    assert len(gates) == 2


def _mutated(mutate: Any) -> dict[str, Any]:
    data = copy.deepcopy(_raw())
    mutate(data["scenarios"])
    return data


BAD_FILES = {
    "unknown family": lambda s: s[0].update(family="nope"),
    "empty expected_route": lambda s: s[0].update(expected_route=[]),
    "missing forbidden_routes": lambda s: s[0].pop("forbidden_routes"),
    "empty forbidden_routes": lambda s: s[0].update(forbidden_routes=[]),
    "blank route entry": lambda s: s[0].update(forbidden_routes=[" "]),
    "route wrong type": lambda s: s[0].update(expected_route="merge-resolver"),
    "missing order for composition": lambda s: s[6].pop("expected_order"),
    "order outside route": lambda s: s[6].update(expected_order=["analyze"]),
    "missing rationale": lambda s: s[0].update(rationale=" "),
    "missing input": lambda s: s[0].pop("input"),
    "duplicate id": lambda s: s[1].update(id=s[0]["id"]),
    "not an object": lambda s: s.__setitem__(0, "x"),
    "family dropped": lambda s: [
        x.update(family="lifecycle") for x in s if x["family"] == "dx-activation"
    ],
}


@pytest.mark.parametrize("name", sorted(BAD_FILES))
def test_bad_scenario_files_are_refused(name: str, tmp_path: Path) -> None:
    data = _mutated(BAD_FILES[name])
    with pytest.raises(ev.EvalConfigError):
        ev.load_model_scenarios(_write(tmp_path, data))


@pytest.mark.parametrize("payload", [[], {"scenarios": []}, {"scenarios": "x"}])
def test_scenario_file_shape_is_refused(payload: object, tmp_path: Path) -> None:
    with pytest.raises(ev.EvalConfigError):
        ev.load_model_scenarios(_write(tmp_path, payload))


def test_unreadable_scenario_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ev.EvalConfigError):
        ev.load_model_scenarios(tmp_path / "missing.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    with pytest.raises(ev.EvalConfigError):
        ev.load_model_scenarios(bad)


def test_no_results_means_not_scored_never_zero() -> None:
    model = ev.evaluate_model(ev.load_model_scenarios(SCENARIO_FILE), None)
    assert model["run_supplied"] is False
    for counts in model["families"].values():
        assert counts["accuracy"] is None
        assert counts["exercised"] == counts["scored"] == counts["passed"] == 0


def test_layers_are_counted_apart() -> None:
    scenarios = ev.load_model_scenarios(SCENARIO_FILE)
    results = {
        "R1": _result("R1", 5),
        "R2": _result("R2", 2),
        "R3": _result("R3", None, error="api"),
        "R4": _result("R4", None, scores={"graded": False}),
    }
    model = ev.evaluate_model(scenarios, results)
    htd = model["families"]["high-traffic-direct"]
    assert (htd["scenarios"], htd["exercised"], htd["scored"], htd["passed"]) == (2, 2, 2, 1)
    assert htd["accuracy"] == 0.5
    adj = model["families"]["conditional-adjunct"]
    assert (adj["exercised"], adj["scored"], adj["passed"]) == (2, 0, 0)
    assert adj["accuracy"] is None
    assert [m["id"] for m in model["misses"]] == ["R2"]


def test_scenario_missing_from_the_run_is_not_exercised() -> None:
    model = ev.evaluate_model(ev.load_model_scenarios(SCENARIO_FILE), {"R1": _result("R1", 5)})
    htd = model["families"]["high-traffic-direct"]
    assert (htd["exercised"], htd["scored"]) == (1, 1)


@pytest.mark.parametrize("score", [ev.MODEL_PASS_SCORE, 5])
def test_pass_boundary_is_inclusive(score: float) -> None:
    model = ev.evaluate_model(ev.load_model_scenarios(SCENARIO_FILE), {"R1": _result("R1", score)})
    assert model["families"]["high-traffic-direct"]["passed"] == 1


def test_just_below_the_bar_misses() -> None:
    low = ev.MODEL_PASS_SCORE - 0.01
    model = ev.evaluate_model(ev.load_model_scenarios(SCENARIO_FILE), {"R1": _result("R1", low)})
    assert model["families"]["high-traffic-direct"]["passed"] == 0


@pytest.mark.parametrize("bad", [True, "5", 0, 6, float("inf"), float("nan"), None])
def test_off_rubric_cell_is_unmeasured(bad: Any) -> None:
    item = {"id": "R1", "mechanisms": {"full": {"scores": {"cell_score": bad}}}}
    assert ev._cell_score(item) is None


@pytest.mark.parametrize(
    "item",
    [
        {"id": "R1"},
        {"id": "R1", "mechanisms": []},
        {"id": "R1", "mechanisms": {"full": "x"}},
        {"id": "R1", "mechanisms": {"full": {"scores": "x"}}},
        {"id": "R1", "mechanisms": {"full": {"scores": {"cell_score": 5, "judge_failed": True}}}},
        {"id": "R1", "mechanisms": {"description": {"scores": {"cell_score": 5}}}},
    ],
)
def test_damaged_cell_is_unmeasured(item: dict[str, Any]) -> None:
    assert ev._cell_score(item) is None


def test_unreachable_route_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ev, "route_exists", lambda name: name != "github")
    model = ev.evaluate_model(ev.load_model_scenarios(SCENARIO_FILE), None)
    assert model["unreachable"] == [
        {"id": "R1", "routes": ["github"]},
        {"id": "R2", "routes": ["github"]},
    ]
    assert model["families"]["high-traffic-direct"]["reachable"] == 0


def test_route_exists_covers_skills_and_agents() -> None:
    assert ev.route_exists("dx-review")
    assert ev.route_exists("merge-resolver")
    assert not ev.route_exists("no-such-route")


def test_results_loader_reads_the_runner_shape(tmp_path: Path) -> None:
    loaded = ev.load_model_results(_results_file(tmp_path, [_result("R1", 5)]))
    assert set(loaded) == {"R1"}


@pytest.mark.parametrize("payload", [[], {"rules": []}, {"rules": {}}, {"rules": {"autoplan": {}}}])
def test_results_loader_refuses_other_shapes(payload: object, tmp_path: Path) -> None:
    path = tmp_path / "run.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ev.EvalConfigError):
        ev.load_model_results(path)


def test_results_loader_refuses_missing_or_invalid_file(tmp_path: Path) -> None:
    with pytest.raises(ev.EvalConfigError):
        ev.load_model_results(tmp_path / "nope.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    with pytest.raises(ev.EvalConfigError):
        ev.load_model_results(bad)


def test_model_miss_is_advisory_and_exit_stays_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run = _results_file(tmp_path, [_result("R1", 5), _result("R2", 1)])
    code = ev.main(["--model-results", str(run)])
    out = capsys.readouterr().out
    assert code == ev.EXIT_OK
    line = "model family high-traffic-direct: scenarios=2 reachable=2 exercised=2 scored=2"
    assert f"{line} passed=1 accuracy=50%" in out
    assert "MODEL-MISS R2 [high-traffic-direct] score=1.00 (advisory)" in out
    assert "not scored: pass --model-results" not in out


def test_bad_results_file_is_exit_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert ev.main(["--model-results", str(tmp_path / "none.json")]) == ev.EXIT_CONFIG
    assert "ERROR" in capsys.readouterr().err


def test_bad_scenario_file_is_exit_2(tmp_path: Path) -> None:
    bad = _write(tmp_path, {"scenarios": []})
    assert ev.main(["--model-scenarios", str(bad)]) == ev.EXIT_CONFIG


def test_json_report_carries_the_model_section(tmp_path: Path) -> None:
    out = tmp_path / "r.json"
    ev.main(["--output", str(out)])
    model = json.loads(out.read_text(encoding="utf-8"))["model_driven"]
    assert set(model["families"]) == set(ev.MODEL_FAMILIES)
    assert "not_executed" not in json.loads(out.read_text(encoding="utf-8"))


def test_render_model_none_is_empty() -> None:
    assert ev.render_model(None) == []


def test_render_lists_unreachable_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ev, "route_exists", lambda name: False)
    model = ev.evaluate_model(ev.load_model_scenarios(SCENARIO_FILE), None)
    assert any(line.startswith("unreachable R1:") for line in ev.render_model(model))


def test_runner_accepts_the_scenario_file_without_a_model() -> None:
    """The unchanged runner validates the file; --dry-run makes no API call."""
    proc = subprocess.run(
        [sys.executable, str(RUNNER), "--scenarios", str(SCENARIO_FILE), "--dry-run"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert "autoplan: 12 scenarios" in proc.stdout


def _runner() -> Any:
    name = "eval_rule_activation_runner"
    if name in sys.modules:
        return sys.modules[name]
    sys.path.insert(0, str(RUNNER.parent))
    try:
        spec = importlib.util.spec_from_file_location(name, RUNNER)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(RUNNER.parent))
    return module


@pytest.mark.parametrize(
    "scores",
    [
        {"cell_score": 4.5},
        {"cell_score": 1},
        {"cell_score": 6},
        {"cell_score": True},
        {"cell_score": None},
        {"cell_score": 5, "judge_failed": True},
        {"cell_score": 5, "graded": False},
        {},
    ],
)
def test_cell_score_agrees_with_the_runner(scores: dict[str, Any]) -> None:
    """The runner owns the score semantics; the report must read the same cell.

    Stricter than the runner in two places: a judge-failed cell and a legacy
    triple-only cell are unmeasured here, where the runner still returns a score.
    """
    result = {"id": "R1", "mechanisms": {"full": {"scores": scores}}}
    runner_score, failed, legacy = _runner()._scenario_score_triple(result, "full")
    if legacy or failed:
        assert ev._cell_score(result) is None
    else:
        assert ev._cell_score(result) == runner_score


def test_cell_score_agrees_with_the_runner_on_an_errored_cell() -> None:
    result = {"id": "R1", "mechanisms": {"full": {"error": "x", "scores": {"cell_score": 5}}}}
    assert _runner()._scenario_score_triple(result, "full")[0] is None
    assert ev._cell_score(result) is None


def test_pass_bar_and_mechanism_name_are_runner_vocabulary() -> None:
    runner = _runner()
    assert ev.MODEL_MECHANISM in runner.MECHANISMS
    assert (ev.MODEL_MIN_SCORE, ev.MODEL_MAX_SCORE) == (
        runner.MIN_RUBRIC_SCORE,
        runner.MAX_RUBRIC_SCORE,
    )

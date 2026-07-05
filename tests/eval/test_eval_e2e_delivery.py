"""Unit tests for the end-to-end delivery eval (issue #2859).

Covers the pure core (fixture validation, judge-response parsing, score
aggregation) and the CLI dry-run path. No live API calls: the one test that
touches the runner monkeypatches call_api to prove dry-run never reaches it.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO_ROOT / "scripts" / "eval"
FIXTURES = EVAL_DIR / "examples" / "e2e-delivery-fixtures.json"


def _load(filename: str, module_name: str):
    path_added = str(EVAL_DIR) not in sys.path
    if path_added:
        sys.path.insert(0, str(EVAL_DIR))
    try:
        spec = importlib.util.spec_from_file_location(module_name, EVAL_DIR / filename)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        if path_added and str(EVAL_DIR) in sys.path:
            sys.path.remove(str(EVAL_DIR))


core = _load("_e2e_delivery_core.py", "_e2e_delivery_core")
runner = _load("eval-e2e-delivery.py", "eval_e2e_delivery")


def _valid_fixture(**overrides):
    base = {
        "id": "T1",
        "prompt": "vague thing",
        "kind": "feature",
        "hidden_criteria": {
            "behavior": "b",
            "required_tests": ["t"],
            "required_docs": [],
            "required_gates": ["g"],
            "ambiguous_stop_expected": False,
        },
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------
# Fixture validation
# --------------------------------------------------------------------------

def test_valid_fixture_passes():
    core.validate_fixture(_valid_fixture())


def test_missing_top_level_key_raises():
    fx = _valid_fixture()
    del fx["prompt"]
    with pytest.raises(core.FixtureError, match="missing keys"):
        core.validate_fixture(fx)


def test_invalid_kind_raises():
    with pytest.raises(core.FixtureError, match="invalid kind"):
        core.validate_fixture(_valid_fixture(kind="chore"))


def test_missing_criteria_subkey_raises():
    fx = _valid_fixture()
    del fx["hidden_criteria"]["required_gates"]
    with pytest.raises(core.FixtureError, match="hidden_criteria missing"):
        core.validate_fixture(fx)


def test_ambiguous_flag_must_be_bool():
    fx = _valid_fixture()
    fx["hidden_criteria"]["ambiguous_stop_expected"] = "yes"
    with pytest.raises(core.FixtureError, match="must be bool"):
        core.validate_fixture(fx)


def test_kind_and_stop_flag_must_agree():
    # ambiguous kind with stop=False is a self-contradiction.
    fx = _valid_fixture(kind="ambiguous")
    fx["hidden_criteria"]["ambiguous_stop_expected"] = False
    with pytest.raises(core.FixtureError, match="disagrees"):
        core.validate_fixture(fx)


def test_load_fixtures_rejects_duplicate_ids():
    doc = json.dumps({"fixtures": [_valid_fixture(), _valid_fixture()]})
    with pytest.raises(core.FixtureError, match="duplicate fixture id"):
        core.load_fixtures(doc)


def test_load_fixtures_rejects_empty():
    with pytest.raises(core.FixtureError, match="non-empty"):
        core.load_fixtures(json.dumps({"fixtures": []}))


def test_load_fixtures_rejects_bad_schema_version():
    doc = json.dumps({"schemaVersion": 99, "fixtures": [_valid_fixture()]})
    with pytest.raises(core.FixtureError, match="schemaVersion"):
        core.load_fixtures(doc)


def test_load_fixtures_accepts_bare_list():
    out = core.load_fixtures(json.dumps([_valid_fixture()]))
    assert out[0]["id"] == "T1"


def test_shipped_fixture_file_is_valid():
    # The in-tree starter set must always pass its own validator.
    out = core.load_fixtures(FIXTURES.read_text(encoding="utf-8"))
    assert len(out) >= 5
    kinds = {f["kind"] for f in out}
    assert {"feature", "bug", "ambiguous", "multi-domain"} <= kinds


# --------------------------------------------------------------------------
# Judge-response parsing
# --------------------------------------------------------------------------

def test_parse_clean_json():
    raw = json.dumps(
        {
            "scope": 3,
            "completeness": 2,
            "process_gates": 1,
            "decomposition": 2,
            "correct_stop": 1,
            "rationale": "ok",
        }
    )
    out = core.parse_judge_response(raw)
    assert out["verdict"] == "SCORED"
    assert out["total"] == 9
    assert out["axes"]["scope"] == 3
    assert out["rationale"] == "ok"


def test_parse_json_embedded_in_prose_and_fences():
    raw = "Here is my score:\n```json\n" + json.dumps(
        {
            "scope": 1,
            "completeness": 1,
            "process_gates": 0,
            "decomposition": 0,
            "correct_stop": 0,
        }
    ) + "\n```\nDone."
    out = core.parse_judge_response(raw)
    assert out["total"] == 2


def test_parse_clamps_out_of_range_axes():
    raw = json.dumps(
        {
            "scope": 99,          # clamps to 3
            "completeness": -5,   # clamps to 0
            "process_gates": 2,
            "decomposition": 2,
            "correct_stop": 7,    # clamps to 1
        }
    )
    out = core.parse_judge_response(raw)
    assert out["axes"]["scope"] == 3
    assert out["axes"]["completeness"] == 0
    assert out["axes"]["correct_stop"] == 1
    assert out["total"] == 3 + 0 + 2 + 2 + 1


def test_parse_non_numeric_axis_becomes_zero():
    raw = json.dumps(
        {
            "scope": "three",
            "completeness": 2,
            "process_gates": 1,
            "decomposition": 1,
            "correct_stop": 1,
        }
    )
    out = core.parse_judge_response(raw)
    assert out["axes"]["scope"] == 0
    assert out["total"] == 5


def test_parse_garbage_returns_parse_error():
    out = core.parse_judge_response("no json here at all")
    assert out["verdict"] == core.PARSE_ERROR
    assert out["total"] is None


def test_max_score_constant():
    assert core.MAX_SCORE == 11


# --------------------------------------------------------------------------
# Aggregation
# --------------------------------------------------------------------------

def _rec(fx, agent, total):
    return {"fixture_id": fx, "agent": agent, "total": total}


def test_aggregate_means_and_delta():
    records = [
        _rec("F1", "orchestrator", 6),
        _rec("F1", "orchestrator", 8),
        _rec("F1", "autoplan", 9),
        _rec("F1", "autoplan", 9),
    ]
    report = core.aggregate(records)
    assert report["per_fixture"]["F1"]["orchestrator"] == 7.0
    assert report["per_fixture"]["F1"]["autoplan"] == 9.0
    # agents sort alphabetically -> delta is (orchestrator - autoplan).
    assert report["per_fixture"]["F1"]["delta"] == -2.0
    assert report["per_fixture"]["F1"]["delta_of"] == "orchestrator - autoplan"
    assert report["per_agent_mean"]["orchestrator"] == 7.0
    assert report["per_agent_mean"]["autoplan"] == 9.0


def test_aggregate_excludes_parse_errors_from_means():
    records = [
        _rec("F1", "orchestrator", 6),
        _rec("F1", "orchestrator", None),
        _rec("F1", "autoplan", 9),
    ]
    report = core.aggregate(records)
    assert report["per_fixture"]["F1"]["orchestrator"] == 6.0
    assert report["parse_errors"] == 1
    assert report["n_records"] == 3


def test_aggregate_no_delta_with_single_agent():
    report = core.aggregate([_rec("F1", "orchestrator", 5)])
    assert "delta" not in report["per_fixture"]["F1"]


# --------------------------------------------------------------------------
# Prompt assembly
# --------------------------------------------------------------------------

def test_agent_message_includes_germ_and_plan_request():
    msg = core.build_agent_user_message("remember my last flags")
    assert "remember my last flags" in msg
    assert "clarifying question" in msg


def test_judge_message_includes_criteria_and_plan():
    fx = _valid_fixture()
    msg = core.build_judge_user_message(fx, "my plan text")
    assert "my plan text" in msg
    assert "ambiguous_stop_expected" in msg
    assert fx["hidden_criteria"]["behavior"] in msg


def test_judge_system_lists_all_axes():
    system = core.build_judge_system()
    for axis in core.RUBRIC_AXES:
        assert axis in system


# --------------------------------------------------------------------------
# CLI dry-run (no API)
# --------------------------------------------------------------------------

def test_dry_run_makes_no_api_call(monkeypatch, capsys):
    def _boom(*a, **k):  # pragma: no cover - must never be called
        raise AssertionError("call_api must not run during --dry-run")

    monkeypatch.setattr(runner, "call_api", _boom)
    monkeypatch.setattr(runner, "load_api_key", _boom)
    rc = runner.main(["--fixtures", str(FIXTURES), "--dry-run", "--runs", "2"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["dry_run"] is True
    # 7 fixtures x 2 agents x 2 runs x 2 calls (generate + judge).
    assert out["planned_api_calls"] == len(out["fixtures"]) * 2 * 2 * 2
    assert "orchestrator" in out["agents"]


def test_unknown_agent_raises(monkeypatch):
    with pytest.raises(RuntimeError, match="unknown agent"):
        runner._resolve_agents(["nope"], None)


def test_registry_prompts_exist_in_tree():
    for rel in runner.AGENT_REGISTRY.values():
        assert (REPO_ROOT / rel).exists(), rel

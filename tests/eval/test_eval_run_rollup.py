"""Tests for scripts/eval/eval_run_rollup.py (issue #2787).

Covers cost derivation, agent-name parsing, lenient JSONL parsing, per-agent
aggregation, N-sigma drift flagging, the end-to-end rollup, both renderers, and
the CLI exit-code contract.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

import eval_run_rollup as rollup_mod  # noqa: E402

MODEL = "claude-sonnet-4-6"


@pytest.fixture(autouse=True)
def _repo_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Keep CLI path-containment tests inside each test's temp repo root."""
    monkeypatch.setattr(rollup_mod, "_REPO_ROOT", tmp_path)


def _record(
    *,
    fixture_id: str = "F1",
    variant: str = "agent",
    run_index: int = 0,
    model_id: str = MODEL,
    latency_ms: float = 100.0,
    tokens_in: int = 1000,
    tokens_out: int = 100,
    outcome: str = "success",
    **overrides: object,
) -> dict:
    payload = {
        "fixture_id": fixture_id,
        "variant": variant,
        "run_index": run_index,
        "model_id": model_id,
        "latency_ms": latency_ms,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "outcome": outcome,
        "schemaVersion": 1,
    }
    payload.update(overrides)
    return payload


def _write_runs(root: Path, agent_spike_dir: str, run_id: str, records: list[dict]) -> Path:
    """Create <root>/<agent_spike_dir>/runs/<run_id>/runs.jsonl with records."""
    run_dir = root / agent_spike_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "runs.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")
    return path


# --- cost_usd ---------------------------------------------------------------


def test_cost_usd_priced_model_computes_from_rates():
    # (1000 * 0.003 + 100 * 0.015) / 1000 = (3.0 + 1.5) / 1000 = 0.0045
    assert rollup_mod.cost_usd(MODEL, 1000, 100) == pytest.approx(0.0045)


def test_cost_usd_unpriced_model_returns_none():
    assert rollup_mod.cost_usd("no-such-model-xyz", 1000, 100) is None


def test_cost_usd_zero_tokens_is_zero():
    assert rollup_mod.cost_usd(MODEL, 0, 0) == 0.0


# --- agent_from_path --------------------------------------------------------


def test_agent_from_path_strips_spike_suffix(tmp_path: Path):
    path = tmp_path / "devops-spike" / "runs" / "R1" / "runs.jsonl"
    assert rollup_mod.agent_from_path(path, tmp_path) == "devops"


def test_agent_from_path_keeps_name_without_spike_suffix(tmp_path: Path):
    path = tmp_path / "custom-agent" / "runs" / "R1" / "runs.jsonl"
    assert rollup_mod.agent_from_path(path, tmp_path) == "custom-agent"


def test_agent_from_path_off_layout_falls_back_to_parent(tmp_path: Path):
    # Path not under root: fall back to the parent directory name.
    outside = Path("/elsewhere/weird/runs.jsonl")
    assert rollup_mod.agent_from_path(outside, tmp_path) == "weird"


# --- iter_tallies (lenient parsing) -----------------------------------------


def test_iter_tallies_parses_valid_records(tmp_path: Path):
    path = _write_runs(tmp_path, "qa-spike", "R1", [_record(), _record(run_index=1)])
    tallies, skipped = rollup_mod.iter_tallies(path, tmp_path)
    assert skipped == 0
    assert len(tallies) == 2
    assert tallies[0].agent == "qa"
    assert tallies[0].run_id == "R1"
    assert tallies[0].cost == pytest.approx(0.0045)
    assert tallies[0].tokens == 1100


def test_iter_tallies_skips_blank_and_malformed_lines(tmp_path: Path):
    run_dir = tmp_path / "qa-spike" / "runs" / "R1"
    run_dir.mkdir(parents=True)
    path = run_dir / "runs.jsonl"
    path.write_text(
        "\n"  # blank line: ignored, not counted as skip
        + json.dumps(_record()) + "\n"
        + "{not valid json\n"  # malformed: skipped
        + json.dumps([1, 2, 3]) + "\n"  # non-dict: skipped
        + json.dumps(_record(latency_ms=None)) + "\n",  # missing field: skipped
        encoding="utf-8",
    )
    tallies, skipped = rollup_mod.iter_tallies(path, tmp_path)
    assert len(tallies) == 1
    assert skipped == 3


def test_iter_tallies_skips_record_with_non_numeric_tokens(tmp_path: Path):
    path = _write_runs(tmp_path, "qa-spike", "R1", [_record(tokens_in="lots")])
    tallies, skipped = rollup_mod.iter_tallies(path, tmp_path)
    assert tallies == []
    assert skipped == 1


def test_iter_tallies_skips_bool_and_non_finite_metering(tmp_path: Path):
    path = _write_runs(
        tmp_path,
        "qa-spike",
        "R1",
        [
            _record(tokens_in=True),
            _record(tokens_out=True),
            _record(latency_ms=True),
            _record(latency_ms=float("nan")),
            _record(latency_ms=-1),
            _record(tokens_in=-1),
            _record(tokens_out=-1),
        ],
    )
    tallies, skipped = rollup_mod.iter_tallies(path, tmp_path)
    assert tallies == []
    assert skipped == 7


def test_iter_tallies_unpriced_model_keeps_run_with_none_cost(tmp_path: Path):
    path = _write_runs(tmp_path, "qa-spike", "R1", [_record(model_id="mystery")])
    tallies, skipped = rollup_mod.iter_tallies(path, tmp_path)
    assert skipped == 0
    assert tallies[0].cost is None


# --- aggregation ------------------------------------------------------------


def test_build_agent_rollups_sums_tokens_and_counts_errors(tmp_path: Path):
    path = _write_runs(
        tmp_path,
        "qa-spike",
        "R1",
        [_record(), _record(outcome="error", run_index=1)],
    )
    tallies, _ = rollup_mod.iter_tallies(path, tmp_path)
    rollups = rollup_mod._build_agent_rollups(tallies)
    qa = rollups["qa"]
    assert qa.runs == 2
    assert qa.errors == 1
    assert qa.tokens_in == 2000
    assert qa.tokens == 2200
    assert qa.cost == pytest.approx(0.009)


def test_unpriced_run_excluded_from_cost_aggregate(tmp_path: Path):
    path = _write_runs(
        tmp_path,
        "qa-spike",
        "R1",
        [_record(), _record(model_id="mystery", run_index=1)],
    )
    tallies, _ = rollup_mod.iter_tallies(path, tmp_path)
    qa = rollup_mod._build_agent_rollups(tallies)["qa"]
    assert qa.runs == 2
    assert qa.cost_priced_runs == 1
    assert qa.cost == pytest.approx(0.0045)


# --- drift ------------------------------------------------------------------


def test_latency_outlier_is_flagged(tmp_path: Path):
    records = [
        _record(fixture_id="A", latency_ms=10.0),
        _record(fixture_id="B", latency_ms=10.0, run_index=1),
        _record(fixture_id="C", latency_ms=10.0, run_index=2),
        _record(fixture_id="D", latency_ms=10000.0, run_index=3),
    ]
    path = _write_runs(tmp_path, "qa-spike", "R1", records)
    tallies, _ = rollup_mod.iter_tallies(path, tmp_path)
    rollups = rollup_mod._build_agent_rollups(tallies)
    flags = rollup_mod._drift_flags(tallies, rollups, sigma=1.0)
    latency_flags = [f for f in flags if f.metric == "latency_ms"]
    assert len(latency_flags) == 1
    assert latency_flags[0].fixture_id == "D"


def test_single_sample_group_never_drifts(tmp_path: Path):
    path = _write_runs(tmp_path, "qa-spike", "R1", [_record(latency_ms=99999.0)])
    tallies, _ = rollup_mod.iter_tallies(path, tmp_path)
    rollups = rollup_mod._build_agent_rollups(tallies)
    assert rollup_mod._drift_flags(tallies, rollups, sigma=0.0) == []


def test_zero_variance_group_never_drifts(tmp_path: Path):
    records = [_record(latency_ms=50.0, run_index=i, fixture_id=f"F{i}") for i in range(3)]
    path = _write_runs(tmp_path, "qa-spike", "R1", records)
    tallies, _ = rollup_mod.iter_tallies(path, tmp_path)
    rollups = rollup_mod._build_agent_rollups(tallies)
    assert rollup_mod._drift_flags(tallies, rollups, sigma=0.0) == []


def test_cost_outlier_is_flagged(tmp_path: Path):
    records = [
        _record(fixture_id="A", tokens_out=10),
        _record(fixture_id="B", tokens_out=10, run_index=1),
        _record(fixture_id="C", tokens_out=10, run_index=2),
        _record(fixture_id="D", tokens_out=1_000_000, run_index=3),
    ]
    path = _write_runs(tmp_path, "qa-spike", "R1", records)
    tallies, _ = rollup_mod.iter_tallies(path, tmp_path)
    rollups = rollup_mod._build_agent_rollups(tallies)
    flags = rollup_mod._drift_flags(tallies, rollups, sigma=1.0)
    cost_flags = [f for f in flags if f.metric == "cost"]
    assert len(cost_flags) == 1
    assert cost_flags[0].fixture_id == "D"


# --- rollup() end-to-end ----------------------------------------------------


def test_rollup_groups_two_agents(tmp_path: Path):
    _write_runs(tmp_path, "qa-spike", "R1", [_record(), _record(run_index=1)])
    _write_runs(tmp_path, "devops-spike", "R1", [_record()])
    result = rollup_mod.rollup(tmp_path, sigma=3.0)
    assert result.runs_counted == 3
    assert [a.agent for a in result.agents] == ["devops", "qa"]
    assert result.files_scanned == 2


def test_rollup_agent_filter_keeps_one(tmp_path: Path):
    _write_runs(tmp_path, "qa-spike", "R1", [_record()])
    _write_runs(tmp_path, "devops-spike", "R1", [_record()])
    result = rollup_mod.rollup(tmp_path, agent_filter="qa")
    assert [a.agent for a in result.agents] == ["qa"]
    assert result.runs_counted == 1


def test_rollup_counts_unpriced_runs(tmp_path: Path):
    _write_runs(tmp_path, "qa-spike", "R1", [_record(model_id="mystery")])
    result = rollup_mod.rollup(tmp_path)
    assert result.unpriced_runs == 1


def test_rollup_empty_root_is_clean(tmp_path: Path):
    result = rollup_mod.rollup(tmp_path)
    assert result.runs_counted == 0
    assert result.agents == []
    assert result.total_cost == 0.0


def test_rollup_negative_sigma_raises(tmp_path: Path):
    with pytest.raises(ValueError):
        rollup_mod.rollup(tmp_path, sigma=-1.0)


# --- renderers --------------------------------------------------------------


def test_to_json_shape(tmp_path: Path):
    _write_runs(tmp_path, "qa-spike", "R1", [_record(), _record(run_index=1)])
    payload = rollup_mod.to_json(rollup_mod.rollup(tmp_path))
    assert payload["runs_counted"] == 2
    assert payload["agents"][0]["agent"] == "qa"
    assert payload["total_cost_usd"] == pytest.approx(0.009)
    assert "drift" in payload


def test_to_human_contains_table_and_total(tmp_path: Path):
    _write_runs(tmp_path, "qa-spike", "R1", [_record()])
    text = rollup_mod.to_human(rollup_mod.rollup(tmp_path))
    assert "qa" in text
    assert "TOTAL" in text
    assert "Drift flags: none" in text


def test_to_human_empty_says_no_runs(tmp_path: Path):
    text = rollup_mod.to_human(rollup_mod.rollup(tmp_path))
    assert "no runs found" in text


def _drifting_records() -> list[dict]:
    # Three tight runs plus one latency-and-cost outlier, so both drift metrics fire.
    return [
        _record(fixture_id="A", latency_ms=10.0, tokens_out=10),
        _record(fixture_id="B", latency_ms=10.0, tokens_out=10, run_index=1),
        _record(fixture_id="C", latency_ms=10.0, tokens_out=10, run_index=2),
        _record(fixture_id="D", latency_ms=10000.0, tokens_out=1_000_000, run_index=3),
    ]


def test_to_human_renders_drift_flags(tmp_path: Path):
    _write_runs(tmp_path, "qa-spike", "R1", _drifting_records())
    text = rollup_mod.to_human(rollup_mod.rollup(tmp_path, sigma=1.0))
    assert "Drift flags" in text
    assert "latency_ms" in text
    assert "ms >" in text  # latency rendered with ms unit
    assert "usd >" in text  # cost rendered with usd unit


def test_to_json_renders_drift_entries(tmp_path: Path):
    _write_runs(tmp_path, "qa-spike", "R1", _drifting_records())
    payload = rollup_mod.to_json(rollup_mod.rollup(tmp_path, sigma=1.0))
    metrics = {d["metric"] for d in payload["drift"]}
    assert "latency_ms" in metrics
    assert "cost" in metrics
    assert all(d["agent"] == "qa" for d in payload["drift"])


# --- CLI --------------------------------------------------------------------


def test_main_bad_root_exits_config(tmp_path: Path, capsys):
    code = rollup_mod.main(["--root", str(tmp_path / "missing")])
    assert code == rollup_mod.EXIT_CONFIG
    assert "not a directory" in capsys.readouterr().err


def test_main_root_outside_repo_exits_config(tmp_path: Path, capsys):
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    code = rollup_mod.main(["--root", str(outside)])
    assert code == rollup_mod.EXIT_CONFIG
    assert "outside repository root" in capsys.readouterr().err


def test_main_negative_sigma_exits_config(tmp_path: Path, capsys):
    code = rollup_mod.main(["--root", str(tmp_path), "--sigma", "-2"])
    assert code == rollup_mod.EXIT_CONFIG
    assert "sigma" in capsys.readouterr().err


def test_main_nan_sigma_exits_config(tmp_path: Path, capsys):
    # float('nan') < 0 is False, so the NaN guard is the only thing rejecting it.
    code = rollup_mod.main(["--root", str(tmp_path), "--sigma", "nan"])
    assert code == rollup_mod.EXIT_CONFIG
    assert "sigma" in capsys.readouterr().err


def test_main_json_output_ok(tmp_path: Path, capsys):
    _write_runs(tmp_path, "qa-spike", "R1", [_record()])
    code = rollup_mod.main(["--root", str(tmp_path), "--output-format", "json"])
    assert code == rollup_mod.EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["runs_counted"] == 1


def test_main_human_output_ok(tmp_path: Path, capsys):
    _write_runs(tmp_path, "qa-spike", "R1", [_record()])
    code = rollup_mod.main(["--root", str(tmp_path)])
    assert code == rollup_mod.EXIT_OK
    assert "Eval run rollup" in capsys.readouterr().out

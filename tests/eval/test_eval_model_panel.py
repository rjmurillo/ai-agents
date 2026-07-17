"""Tests for scripts/eval/eval-model-panel.py CLI (issue #3042).

The hyphenated CLI module is loaded via importlib. The harness runner seam is
injected so the sweep is exercised with zero API spend.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))


def _load_cli():
    spec = importlib.util.spec_from_file_location(
        "eval_model_panel", EVAL_DIR / "eval-model-panel.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


cli = _load_cli()


def _fake_runner(deltas):
    """Runner that returns a report.json with recall_delta from deltas[(unit,tier)]."""
    def run(unit, tier, n_runs, fixtures):
        key = (unit, tier.label)
        if key not in deltas:
            raise RuntimeError(f"no fake result for {key}")
        return {"recall_delta": deltas[key], "bootstrap_ci_95": [0.0, 1.0]}
    return run


def test_dry_run_zero_spend(capsys):
    code = cli.main(["--agents", "qa", "--dry-run"])
    out = capsys.readouterr().out
    assert code == cli.EXIT_OK
    assert "DRY RUN" in out
    assert "ZERO spend" in out
    assert "qa @ opus" in out


def test_bad_n_runs_exits_config(capsys):
    code = cli.main(["--agents", "qa", "--n-runs", "0", "--dry-run"])
    assert code == cli.EXIT_CONFIG
    assert "n-runs" in capsys.readouterr().err


def test_bad_panel_config_exits_config(tmp_path, capsys):
    cfg = tmp_path / "panel.json"
    cfg.write_text('{"tiers": []}', encoding="utf-8")
    code = cli.main(["--agents", "qa", "--panel-config", str(cfg), "--dry-run"])
    assert code == cli.EXIT_CONFIG


def test_live_sweep_reports_degradation(capsys):
    deltas = {
        ("qa", "opus"): 0.5, ("qa", "sol"): 0.5,
        ("qa", "sonnet"): 0.2, ("qa", "terra"): 0.45,
    }
    code = cli.main(
        ["--agents", "qa", "--output-format", "json"],
        runner=_fake_runner(deltas),
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == cli.EXIT_OK
    unit = payload["units"][0]
    assert unit["unit"] == "qa"
    assert "sonnet" in unit["degraded_tiers"]
    assert unit["robust"] is False


def test_live_sweep_robust_unit(capsys):
    deltas = {
        ("qa", "opus"): 0.5, ("qa", "sol"): 0.5,
        ("qa", "sonnet"): 0.48, ("qa", "terra"): 0.47,
    }
    code = cli.main(
        ["--agents", "qa", "--output-format", "json"],
        runner=_fake_runner(deltas),
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == cli.EXIT_OK
    assert payload["units"][0]["robust"] is True


def test_runner_error_records_cell_and_exits_external(capsys):
    # Missing terra result -> that cell errors -> exit 3, but others still scored.
    deltas = {
        ("qa", "opus"): 0.5, ("qa", "sol"): 0.5, ("qa", "sonnet"): 0.5,
    }
    code = cli.main(
        ["--agents", "qa", "--output-format", "json"],
        runner=_fake_runner(deltas),
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == cli.EXIT_EXTERNAL
    # terra missing -> unit incomplete
    assert payload["units"][0]["incomplete"] is True


def test_report_written(tmp_path):
    deltas = {
        ("qa", "opus"): 0.5, ("qa", "sol"): 0.5,
        ("qa", "sonnet"): 0.5, ("qa", "terra"): 0.5,
    }
    report = tmp_path / "reports" / "panel.json"
    code = cli.main(
        ["--agents", "qa", "--report", str(report)],
        runner=_fake_runner(deltas),
    )
    assert code == cli.EXIT_OK
    assert json.loads(report.read_text())["units"][0]["robust"] is True

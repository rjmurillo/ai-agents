"""Shared builders for the eval_model_routing tests.

Loads scripts/eval/eval_model_routing.py once and builds a synthetic
``evals/<agent>-spike/{fixtures,reports,runs}`` tree under ``tmp_path``.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO_ROOT / "scripts" / "eval"
ROUTING_SCRIPT = EVAL_DIR / "eval_model_routing.py"

# eval_model_routing imports sibling modules via plain `from X import Y` at
# import time, and its own run() re-loads eval-model-sweep.py the same way at
# call time (see _load_sweep_module). EVAL_DIR must stay on sys.path for the
# life of this test module, not just for the initial load.
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

_spec = importlib.util.spec_from_file_location("eval_model_routing", ROUTING_SCRIPT)
assert _spec and _spec.loader
routing = importlib.util.module_from_spec(_spec)
# Register before exec: the module defines dataclasses at top level, and
# dataclass() resolves forward-referenced type hints via
# sys.modules[cls.__module__], which is None until this is set.
sys.modules["eval_model_routing"] = routing
_spec.loader.exec_module(routing)

FIXTURE_IDS = tuple(f"f{i}" for i in range(6))


# --- fixture/report builders -----------------------------------------------


def write_fixtures(root: Path, agent: str, ids: tuple[str, ...] = FIXTURE_IDS) -> Path:
    fixtures_dir = root / "evals" / f"{agent}-spike" / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    for fid in ids:
        (fixtures_dir / f"{fid}.json").write_text(
            json.dumps({"id": fid, "prompt": f"prompt for {fid}"}), encoding="utf-8"
        )
    return fixtures_dir


def make_reports_dir(root: Path, agent: str) -> Path:
    reports_dir = root / "evals" / f"{agent}-spike" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    return reports_dir


def report_dict(
    model_id: str,
    sha: str,
    rate: float,
    *,
    ids: tuple[str, ...] = FIXTURE_IDS,
    error_count: int = 0,
    skill_rate: float | None = None,
    skill_agent_rate: float | None = None,
) -> dict:
    """Synthetic report.json dict with every field parse_report requires."""
    agent_rate = rate if skill_agent_rate is None else skill_agent_rate
    per_fixture: dict[str, dict] = {}
    for fid in ids:
        per_fixture[fid] = {"agent": [agent_rate], "baseline": [0.4]}
    report: dict = {
        "fixture_set_sha": sha,
        "agent_recall": agent_rate,
        "per_fixture_pass_rates": per_fixture,
        "error_count": error_count,
        "model_id": model_id,
        "flaky_fixtures_excluded": [],
        "total_tokens_in": 1200,
        "total_tokens_out": 600,
        "cost_estimate_usd": 0.02,
        "cost_basis": "usd",
        "baseline_recall": 0.4,
    }
    if skill_rate is not None:
        report["form_factor"] = {"skill_recall": skill_rate}
        # Real reports omit per-fixture skill rates; the rollup rebuilds them
        # from runs.jsonl, so the builder hands them to _write_report there.
        report["_skill_records"] = [
            {
                "fixture_id": fid,
                "variant": "skill",
                "run_index": 0,
                "outcome": "success",
                "assertions": [{"passed": True}] * round(skill_rate * 4)
                + [{"passed": False}] * (4 - round(skill_rate * 4)),
            }
            for fid in ids
        ]
    return report


def write_report(reports_dir: Path, run_id: str, report: dict) -> None:
    report = dict(report)
    skill_records = report.pop("_skill_records", [])
    run_dir = reports_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")
    runs_dir = reports_dir.parent / "runs" / run_id
    runs_dir.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r) for r in skill_records]
    (runs_dir / "runs.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_ladder(name: str, *models: str) -> Any:  # routing is loaded at runtime
    return routing.Ladder(name=name, models=tuple(models))

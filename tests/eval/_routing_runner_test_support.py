"""Shared builders for routing benchmark runner tests (issue #5424)."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import _harness_capability as cap  # noqa: E402
import _routing_backend as backend_mod  # noqa: E402
import _routing_config as config_mod  # noqa: E402
import _routing_dag as dag_mod  # noqa: E402
import _routing_live as live_mod  # noqa: E402
import _routing_plan as plan_mod  # noqa: E402
import _routing_result as result_mod  # noqa: E402
import _routing_run as run_mod  # noqa: E402
import _routing_scenario as scenario_mod  # noqa: E402
import eval_routing_benchmark as cli  # noqa: E402

EXAMPLE_CONFIG = cli.DEFAULT_CONFIG
REAL_MATRIX = cli.DEFAULT_MATRIX
CORPUS = cli.DEFAULT_CORPUS

BOUNDED = "RB-01-bounded-implementation"
MULTI_FILE = "RB-02-multi-file-invariants"
CODEX_VERSION = "codex-cli 0.160.0"
COPILOT_VERSION = "GitHub Copilot CLI 1.0.89-1."
MODELS = ("gpt-5.6-luna", "gpt-5.6-sol", "gpt-5.6-terra")
EFFORTS = ("high", "low", "medium")

__all__ = [
    "BOUNDED",
    "CODEX_VERSION",
    "COPILOT_VERSION",
    "CORPUS",
    "EXAMPLE_CONFIG",
    "MULTI_FILE",
    "REAL_MATRIX",
    "backend_mod",
    "cap",
    "cli",
    "config_dict",
    "config_mod",
    "dag_mod",
    "live_mod",
    "make_record",
    "matched_records",
    "parse",
    "plan_mod",
    "result_mod",
    "run_mod",
    "scenario_mod",
    "scenarios",
    "strategy",
    "write_matrix",
]


def make_record(
    harness: str = "codex",
    *,
    version: str | None = None,
    models: tuple[str, ...] = MODELS,
    efforts: tuple[str, ...] = EFFORTS,
    concurrency: int = 3,
    statuses: dict[str, cap.CapabilityStatus] | None = None,
) -> cap.HarnessCapabilityRecord:
    """A record whose every capability is backend-VERIFIED unless `statuses` says otherwise."""
    statuses = statuses or {}
    capabilities: dict[str, cap.Capability] = {}
    for key in cap.CAPABILITY_KEYS:
        capabilities[key] = cap.Capability(
            status=statuses.get(key, cap.CapabilityStatus.VERIFIED),
            evidence=cap.EvidenceKind.BACKEND,
            detail="exact Sol Ultra control observed" if key == "sol_ultra" else "",
            value=concurrency if key == "concurrency_limit" else None,
        )
    return cap.HarnessCapabilityRecord(
        harness=harness,
        version=version or (CODEX_VERSION if harness == "codex" else COPILOT_VERSION),
        version_evidence=cap.EvidenceKind.BACKEND,
        supported_models=models,
        supported_efforts=efforts,
        capabilities=capabilities,
        tool_sandbox_constraints="",
        telemetry_fields=("tokens",),
        failure_retry_behavior="retry once",
        probe_command="probe",
        date="2026-09-29",
    )


def matched_records() -> list[cap.HarnessCapabilityRecord]:
    return [make_record("codex"), make_record("copilot")]


def write_matrix(path: Path, records: list[cap.HarnessCapabilityRecord]) -> Path:
    document = {
        "schema_version": cap.SCHEMA_VERSION,
        "harnesses": [cap._record_dict(record) for record in records],
    }
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def config_dict() -> dict[str, Any]:
    """A fresh copy of the checked-in example config."""
    return copy.deepcopy(json.loads(EXAMPLE_CONFIG.read_text(encoding="utf-8")))


def parse(document: dict[str, Any]) -> config_mod.BenchmarkConfig:
    return config_mod.parse_config(document)


def strategy(arm: str, harness: str = "codex") -> config_mod.Strategy:
    return parse(config_dict()).strategy_for(arm, harness)


def scenarios() -> list[scenario_mod.Scenario]:
    return scenario_mod.load_corpus(CORPUS)

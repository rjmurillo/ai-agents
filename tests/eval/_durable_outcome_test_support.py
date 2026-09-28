"""Shared record builders for durable outcome tests (issue #5768)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import _durable_outcome as durable  # noqa: E402
import _outcome_record as outcome  # noqa: E402
import eval_durable_outcome as cli  # noqa: E402

__all__ = ["EVAL_DIR", "cli", "durable", "make_config", "make_record", "outcome"]

def make_config(**overrides: object) -> dict[str, Any]:
    base: dict[str, Any] = {
        "model": "claude-sonnet-5",
        "harness": "claude",
        "harness_version": "2.3.1",
        "context_bytes": 1000,
        "retry_budget": 1,
        "reviewer": "critic",
        "control": "full",
    }
    base.update(overrides)
    return base


def make_record(**overrides: object) -> dict[str, Any]:
    """A minimal, fully-clean OutcomeRecord dict (classifies ACCEPTED_DURABLE)."""
    base: dict[str, Any] = {
        "task_id": "t1",
        "repeat": 0,
        "config": make_config(),
        "capability": {"attempted": True, "produced_artifact": True},
        "execution": {
            "deterministic_acceptance": "PASS",
            "first_pass": "PASS",
            "tool_failures": 0,
            "retries": 0,
            "scope_violations": 0,
            "judge": "PASS",
        },
        "durable": {
            "followup_validation": "PASS",
            "objective_satisfied": "PASS",
            "residual_defects": 0,
            "review_findings": 0,
            "rollback_events": 0,
            "rework_minutes": 0,
        },
        "economics": {
            "model_cost_usd": 0.5,
            "tool_cost_usd": 0.0,
            "wall_seconds": 100,
            "human_correction_minutes": 0,
        },
        "risk": {
            "security_findings": 0,
            "unapproved_external_actions": 0,
            "unsupported_claims": 0,
            "unresolved_uncertainty": 0,
        },
    }
    base.update(overrides)
    return base

"""Shared builders for the routing verdict scorer tests (issue #5426).

Rows mirror `result_to_dict` in `_routing_result.py`; `NOT_RUN` rows mirror
`eval_routing_benchmark._not_run`.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import _routing_verdicts as v  # noqa: E402
import eval_routing_verdicts as cli  # noqa: E402, F401

REPO = Path(__file__).resolve().parents[2]
REAL_RESULTS = REPO / "evals" / "routing-benchmark" / "results-2026-10-03"

ORDINARY = (
    "RB-01-bounded-implementation",
    "RB-04-scope-expansion",
    "RB-05-plausible-but-wrong",
    "RB-06-architecture-resolved",
)
FALLBACK = ("RB-02-multi-file-invariants", "RB-03-investigate-before-edit")
CLASSES = {**dict.fromkeys(ORDINARY, v.CLASS_ORDINARY), **dict.fromkeys(FALLBACK, v.CLASS_FALLBACK)}
ALL_IDS = ORDINARY + FALLBACK

Policy = Callable[[str, int], str]


def accept_all(_sid: str, _rep: int) -> str:
    return "ACCEPTED"


def fail_all(_sid: str, _rep: int) -> str:
    return "TASK_FAILED"


def row(
    sid: str,
    arm: str,
    rep: int,
    status: str = "ACCEPTED",
    *,
    seconds: float = 100.0,
    tokens: int = 1000,
    scope: int = 0,
    harness: str = "codex",
) -> dict[str, Any]:
    if status == "NOT_RUN":
        return {
            "status": status,
            "scenario_id": sid,
            "arm": arm,
            "harness": harness,
            "repetition": rep,
            "reason": "invocation budget spent",
        }
    verdict = "PASS" if status == "ACCEPTED" else "FAIL"
    return {
        "scenario_id": sid,
        "arm": arm,
        "harness": {"name": harness, "version": "codex-cli 0.160.0"},
        "status": status,
        "repetition": rep,
        "invocations": [
            {
                "window": {"start": 0.0, "end": seconds},
                "input_tokens": tokens - 100,
                "output_tokens": 100,
            }
        ],
        "validation": {
            "verdict": verdict,
            "scope_violations": [f"x{i}" for i in range(scope)],
            "missing_expected": [],
        },
    }


def arm_rows(
    arm: str,
    ids: tuple[str, ...],
    policy: Policy = accept_all,
    *,
    seconds: float = 100.0,
    tokens: int = 1000,
    scope: int = 0,
) -> list[dict[str, Any]]:
    return [
        row(sid, arm, rep, policy(sid, rep), seconds=seconds, tokens=tokens, scope=scope)
        for sid in ids
        for rep in (1, 2, 3)
    ]


def accept_first(count: int) -> Policy:
    """Accept the first `count` (scenario, rep) cells in iteration order."""
    order: dict[tuple[str, int], int] = {}

    def policy(sid: str, rep: int) -> str:
        index = order.setdefault((sid, rep), len(order))
        return "ACCEPTED" if index < count else "TASK_FAILED"

    return policy


def runs_of(*groups: list[dict[str, Any]]) -> list[v.Run]:
    return v.parse_runs([r for g in groups for r in g], CLASSES)


def status_of(runs: list[v.Run], name: str) -> str:
    report = v.score(runs, CLASSES)
    return str(report["hypotheses"][name]["status"])


def full_dataset(**overrides: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every arm accepts everything on every scenario unless `overrides[arm]` replaces it."""
    rows: list[dict[str, Any]] = []
    for arm in "ABCDEF":
        rows += overrides.get(arm) or arm_rows(arm, ALL_IDS)
    return rows
